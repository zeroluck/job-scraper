# Dedicated FreeHire source reader — review candidate

No live grants have been applied. This directory adds SQL and disposable tests,
not an importer adapter or an issuance/activation mechanism. Base revision:
`f50d50c9bdbef40ed97f00766feae52ff6ce6850`.

## Contract

- New `freehire_source_reader`: NOLOGIN, NOINHERIT, no elevated flags, ownership,
  role memberships, writer grants or publication RPC grants.
- `USAGE` on `public` and `auth`; only custom function EXECUTE is the existing
  invoker `auth.require_jwt_claims()`.
- Column SELECT on `public.jobs`: the original importer's 14 full columns plus
  `provider` required by its filter. No table-wide SELECT. The provider column is
  readable as well as filterable; PostgreSQL has no filter-only SELECT privilege.
- SELECT-only RLS is exactly `provider = 'linkedin'`. No compatibility-status,
  category, freshness, publication-generation or eligibility predicate. Failed and
  unclassified LinkedIn rows remain visible. Other providers and NULL are hidden,
  even if a caller omits or changes the provider filter.
- `jobs_gateway` membership: ADMIN FALSE, INHERIT FALSE, SET TRUE. The new role
  cannot SET ROLE to any other runtime role. Existing publication-reader grants,
  JWT issuer/audience settings and app code are untouched.
- Ordinary PostgreSQL builtins/catalog visibility and ambient database privileges
  are not a SQL sandbox. The restriction is on application data/RPCs/mutations;
  this migration does not revoke shared PUBLIC database privileges.

## Installation and rollback guards

`install.sql` is one transaction with timeouts and a dedicated advisory lock.
It pins database `jobs`, OID `299919`, cluster `7701229561420400865`, PostgreSQL17
and administrator `postgres`. It rejects connected/enabled original OID `16388`,
existing reader/policy, shared-gateway flag/settings/membership drift, missing
RLS/wrong owner/PUBLIC jobs policies, exact JWT hook definition drift, PUBLIC
custom-object capabilities, PUBLIC CREATE and unsafe explicit default ACLs.
Every actual role with effective CREATE on a persistent application schema or
the database (including owners, superusers and inherited CREATE) must already
have its own safe global function defaults. Missing defaults mean implicit
PUBLIC EXECUTE and are rejected, even for NOLOGIN roles; schema-local revokes
and another role's hardened defaults do not suffice. The non-assumable
`pg_database_owner` pseudo-role is excluded; its actual database owner is checked. The installer
never repairs shared objects/defaults. Second execution rejects rather than
silently reconciling state. Run with `psql -X -v ON_ERROR_STOP=1`, in a coordinated
maintenance window without concurrent authorization/schema changes.

`rollback.sql` has the same authority pin and revokes exactly the membership,
policy, 15 column grants, hook EXECUTE and schema USAGE, then drops only the new
role. It checks role marker/flags/memberships and exact policy identity. No
`DROP OWNED`, `CASCADE`, data changes, publication or issuer changes. Unexpected
remaining dependencies abort DROP ROLE and roll back the whole transaction;
they must be reviewed, not automatically removed. Quiesce any future consumer
before rollback. Neither file changes or reconnects original database OID16388.

## Run the isolated gate

Requires Docker, preloaded `postgres:17.11`, `postgrest/postgrest:v16.5`, Python3.9+
and a separately supplied copy of the deployed `workers/linkedin_in.py` with SHA256:

`51b7dc71421d088e70cb7742376aa614ceb9189ecc377e2489b609440195b000`

```sh
python3 ops/source_reader337/qualify.py \
  --importer /protected/deployed-linkedin_in.py \
  --receipt /protected/source-reader-qualification.json
```

RED can be reproduced with `--baseline`: it builds the fixture but skips install,
then fails `AssertionError: dedicated role installed`. This failure was observed
before creating the migration.

The gate creates uniquely named disposable Docker resources, never connects to
production, publishes only the API on a random loopback port and exposes no
PostgreSQL host port. Database files use tmpfs, checked to exclude persistent
volume mounts. Fixture-only JWT material is generated in memory, never
printed or persisted, and removed with its container. Its isolated bridge is not
an egress firewall. Resources are removed and their absence verified before a
PASS receipt is written. The receipt records image IDs and artifact hashes.

The fixture copies the actual jobs column names/types and exact captured live
JWT hook. It is **not** a full production-schema/data restore. It contains 1,203
synthetic LinkedIn rows (12 failed/unclassified), three non-LinkedIn/NULL rows,
an unrelated data table, a forbidden SECURITY DEFINER RPC and a separate existing
publication-reader capability. Values cover NULLs, booleans, empty strings,
Unicode, multiline descriptions, decimal salaries and microsecond timestamps.
Variable-length numeric IDs distinguish text from numeric ordering.

The driver hash-verifies and AST-loads the original unchanged `SupabaseClient`,
column constants and `row_signature`. It does not import/run worker orchestration,
`pull`, upsert, state saving, destination connections or deletion code. The only
transport seam strips the existing `/rest/v1/` proxy prefix for direct local
PostgREST; original request parameters, headers, decoding and read methods run
unchanged against real HTTP and PostgreSQL. This is not production proxy/TLS or
consumer activation qualification.

It compares every selected metadata/full-row value with an administrative SQL
reference, checks signatures, `[500,500,203]` metadata pages, six 200-row batches
plus a three-row final batch, terminal empty pages, sorted/missing IDs, rejected
invalid cursors and the server's 500-row cap. It checks HTTP and SQL denials for
other rows, every ungranted jobs column, other tables, RPCs, INSERT/UPDATE/DELETE,
TRUNCATE, schema CREATE and privilege escalation. It tests future table/sequence/
function denial, including CREATE followed by ALTER OWNER and actual non-superuser
creator-role CREATE of a SECURITY DEFINER that can read private data as its owner
but cannot execute as the reader; valid JWTs and missing,
malformed, expired, wrong-audience/issuer and invalid-signature controls.

All qualification safety checks raise explicitly and remain active under
`python3 -O`; `python3 -m unittest discover -s ops/source_reader337 -p 'test_*.py'`
checks optimized false-check and importer-hash rejection. The full gate also runs
under `python3 -O` without skipping authorization or snapshot checks.

The literal production identity guard must reject the disposable cluster.
For positive qualification only that exact identity expression is replaced with
an isolated jobs/PG17 guard; no ACL/RLS/JWT guard is disabled. Guard-drift tests
strip BOTH installer transaction delimiters, run injected drift plus candidate
inside one rollback transaction and compare catalog/data state. Rollback is
exercised including unexpected-dependency failure and comparison of the entire
installed snapshot captured after the injected grant, not just membership.
Final catalog, role, membership, policy, default ACL and full-row hashes must
match baseline. Relation NULL ACLs are expanded to their PostgreSQL default
owner ACL solely to compare logically identical ACL representations after the
intentional dependency-grant/revoke test; no owner or grant is omitted.

## Review boundary

The guard-only prefix also passed against the pinned live authority inside
`BEGIN READ ONLY` / `ROLLBACK`; no CREATE/GRANT/policy statement was sent. Live
inspection confirmed original OID16388 disconnected with zero sessions, reader
absent, jobs RLS enabled and the recorded importer hash. Source/issuer keys and
production tokens were not read by this work.

This proves the isolated original-read authorization contract, not equality of a
frozen 24,525-row production snapshot or authorization to delete absent rows.
Independent review, approved live application, constrained credential lifecycle,
real authenticated read-only source parity and a separately approved importer
activation remain outside this candidate. No freshness or publication policy was
weakened; no data was imported and no writer activated.
