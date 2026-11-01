# CT337 unattended operations — Linux services live; consumer activation blocked

Read [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) for the verified deployment,
security boundaries, exercised receipts and remaining gates. Linux encrypted NAS
backups, separate retention, restore drills, verified Discord alerts and isolated
renewal-stage timers are deployed. Production consumer renewal is **not** deployed.
No DB/API promotion, global PostgreSQL role mutation, writer activation, web
runtime edit or production consumer restart was performed by this workstream.

The inventory and original installation checklist below are retained as design
history, not an assertion that the newly deployed services are still templates.
The old `systemd/` directory remains illustrative; `deployed-systemd/` contains the
actual reviewed ETL service definitions, including mandatory isolation drop-ins.

## Inventory verified read-only

- `migration/cutover337/tokens.py` signs RS256 messages by SSH to Proxmox and
  `pct exec 337 -- openssl dgst -sha256 -sign ...`. Its allowlist is `job_runner`,
  `job_web`, `freehire_publication_reader`; TTL is at most 30 days.
- The signing file is `/etc/jobs-postgrest/prepared-signing.pem`; a live metadata-only
  check found it present, mode0600. No private-key bytes were retrieved. Prepared
  public JWKS and `kid=prepared-signing` are referenced by existing qualification
  code. Claims currently use audience `job-http-qualification` and issuer
  `job-qualification`; this implementation deliberately preserves that contract.
- Existing runner installation uses `gh secret set JOB_DATA_API_TOKEN`, stdin,
  repository `zeroluck/job-scraper`. Its local receipt records expiry
  `2026-12-01T01:10:39+00:00`. Existing web installation atomically replaces a
  mode0600 runtime JSON environment; it does not itself prove supervisor reload.
- Those scripts use administrator SSH rather than a role-constrained renewal
  principal. They are not unattended least-privileged renewal infrastructure.
- `migration/recovery337/backup_only.py` only encrypts a staged bundle locally.
  `monitor.py` only monitors historical receipts and proposes retention. Neither
  collects live PostgreSQL on a deployed durable timer.
- CT337 has systemd and `/usr/lib/postgresql/17/bin/pg_dump`. Read-only candidate
  namespace inventory returned `auth`, `extensions`, `public`.
- Parent context identifies PG17.11, cluster system identifier
  `7701229561420400865`, candidate `jobs_sync_20261101` OID299919, and original
  `jobs` still serving rollback-only PostgREST. **The backup database example is
  deliberately unset**, not silently pointed at the candidate or original.

## Working components

`autonomy.py` uses Python standard library plus OpenSSL, PostgreSQL17 clients and
restic. All CLI operations require owner-matching regular mode0600 config files,
reject symlinks/hardlinks, suppress subprocess diagnostics, and emit only sanitized
receipts. State directory is owner-matching mode0700. Backups, retention and renewals
share a nonblocking lock. Receipts are fsynced, atomic mode0600 replacements.

### Live collection and encrypted off-host storage

1. Guest `guest-dump` accepts no caller database, SQL or credentials over stdin.
   Its fixed protected config pins cluster ID, database name, database OID and
   PG17.11 exactly. The role is fixed to `job_backup`, socket fixed to
   `/var/run/postgresql`; passwords/TCP are not used.
2. Dedicated guest peer-authenticated OS account executes the helper through a
   forced SSH command or an equivalently constrained Proxmox `pct exec` wrapper.
   SQL grants are schema-scoped in `config/backup-role.sql.example`. `BYPASSRLS`
   permits completeness but is not a write grant. No superuser, global read-all,
   CREATE ROLE, replication or password capability is needed. Verify inherited
   grants and negative writes, including attempts to turn read-only off.
3. Off-host `backup` streams the helper stdout directly into `restic backup
   --stdin`. The guest holds **neither** restic repository credentials nor its
   encryption password. The collector never stages plaintext dumps on disk.
4. Collector checks both pipeline exit statuses and hashes every source byte.
   It then streams `restic dump` through SHA256: restic authenticates/decrypts all
   content and the collector requires exact source/readback hash equality before
   publishing `backup-<snapshot>.json` and `latest-backup.json`.
5. Failed/hung source, restic error or authenticated readback failure yields no
   successful receipt. CLI records a sanitized failure status. Timeouts kill
   direct child processes; configure `source` as a direct executable, not a shell
   background tree. Systemd's default control-group kill bounds the service tree.

Restic encrypts and authenticates content and metadata. Production repository must
be genuinely off-host, not another directory in CT337/Proxmox storage. Initialize
it once with an audited, separately escrowed password. Use a dedicated repository,
TLS/SSH certificate checking, pinned host keys and a restricted remote account.
An append-only rest-server/object-lock policy is recommended against compromised
collectors; qualify the exact backend (including restic locks) before enabling.
The full readback requires read+append access, not a blind write-only credential.
Restic password and repository credentials live only in protected off-host config
or referenced mode0600 password files, never in unit command lines or Git.

`retention` defaults to newest14 plus30 daily and12 weekly representatives. It
requires a fresh successful backup, keep-last>=2, repository check, and an exact
snapshot match for **every** successful receipt before any deletion. It forgets
only receipt-backed snapshots, reads back their absence and the preserved IDs,
then optionally prunes. Unreceipted/partial snapshots are deliberately not purged.
A crash after forget but before receipt deletion fails closed on the next run;
reconcile receipt/repository IDs manually, never replay unreviewed deletion.
Retention credentials must permit deletion and must not be available to the
append-only backup process. The sample service user is a single-host baseline,
**not OS-level privilege isolation**: if both configs are readable by the same
UID, that UID can steal the maintenance credential. Before production, isolate
maintenance in a separate execution boundary (and securely transfer/reconcile
receipt metadata), or use a qualified root-run sandbox with an explicit credential
visibility policy. Do not advertise append-only protection without this gate.

Scope is a PostgreSQL custom-format logical dump only. It is NOT WAL/PITR,
cluster-global roles, HBA, signing/TLS keys, PostgREST configuration or object
storage backup. Protect and encrypt those separately with keys escrowed off-host;
never put a signer in an application bundle. `pg_dump` has transactional table
consistency but sequence values can advance under active writers. This collector
makes no frozen-sequence/cross-system snapshot claim and does not replace the
parent's fenced migration/recovery acceptance. Prevent concurrent rename/drop of
the pinned database across preflight/dump; qualify restore in an isolated guest.

### Bounded credential issuance and renewal

- `issue` constructs its own complete RS256 header/claims, fixed24-hour TTL and
  one config-selected allowlisted role. It never signs caller-supplied bytes.
  Key remains mode0600 on CT337. Output is a bearer for a pipe, **never invoke this
  entry point in a journaling service or paste its stdout**.
- Configure a different SSH principal/key for each consumer. Each authorized key
  must use `restrict,command="EXACT_FIXED_COMMAND"`, no forwarding/PTY, pinned host
  key, no password login, and no general Proxmox root shell. A sudo/pct wrapper,
  if unavoidable, must fix CT337, executable, action and root-owned config path;
  do not grant `pct exec`, `openssl`, Python or arbitrary config arguments broadly.
  Keep issuer code/config root-owned outside writable import paths; use `python3
  -I` for privileged helpers. No renewal scheduler needs the private signing file.
- `renew` obtains the token through a fixed argv pipe, locally verifies its RSA
  signature against the pinned public PEM, role/audience/issuer/age and24-hour
  TTL, and calls `install` then `verify` with the bearer only on stdin. Receipt
  is written only after both succeed. Role-specific status files prevent another
  consumer's successful renewal from hiding this consumer's failure.
- Timer cadence is6 hours, leaving18 hours nominal outage margin. Verifier must
  exercise the **running consumer**, not just authenticate a fresh token directly.
  Runner needs repository-scoped GitHub App secret-write permission and a real
  workflow readback; long-lived personal admin tokens are not a least-privileged
  installation identity. Web needs atomic protected config plus the actual
  supervisor reload/restart and authenticated dynamic-route readback. FreeHire
  needs its own consumer adapter/verification. Their hooks are intentionally
  explicit missing integration paths in examples, not success stubs.
- Clone the renewal config and template timer for `job_web` and
  `freehire_publication_reader`; add each receipt/status to monitor. Parent must
  choose scheduling location for macOS web runtime (Linux systemd cannot manage
  its launchd service directly without a constrained remote adapter).
- Renewal does not rotate/revoke a stolen signer. Establish dual-public-JWKS
  overlap, new kid/key generation, bounded old-token drain and removal, incident
  revocation and offline escrow. No perpetual/no-maintenance guarantee is made.

### Monitoring, notifications and scheduling

`monitor` checks receipt validity, verification flag, future timestamps, maximum
age, minimum credential lifetime, last-operation failures and scheduler staleness.
It runs fixed timeout-bounded application probes. Missing files/probes/notifier
fail closed. Only safe check indexes/error codes are sent to `notify` on stdin;
no supplied URLs, command stderr or bearer values are logged. It sends healthy
heartbeats too: the external receiver must independently alert if5-minute
heartbeats stop, otherwise a dead host/timer cannot report its own death.

Examples include backup freshness26h, renewal receipt7h/lifetime6h, weekly
retention freshness8d, and externally produced verified restore receipt31d.
The parent must write `restore-drill.json` only after an actual isolated restore,
with `{"verified":true,"at": UNIX_SECONDS}`. Do not fabricate that receipt.
Application probes must test actual publication/scrape freshness (not merely HTTP
200), API valid/invalid authorization and representative web data routes. Parent
owns the concrete freshness SQL/thresholds and safe alert destination/credentials.

`systemd/` contains persistent UTC calendar timers, randomized startup spread,
network-online ordering, unprivileged oneshots, restrictive umask, filesystem
protection, no core dumps and bounded runtimes. Timers catch a missed run once
after reboot; they do not replay every missed backup. Monitoring polls failures
within5 minutes; the external watchdog detects total scheduler/host outage.

## Original integration/deployment gates (historical checklist)

This checklist predates the deployment recorded in `DEPLOYMENT_STATUS.md` and
is not a list of currently unperformed work. In particular, its scoped
`job_backup` role proposal was **not** applied: the deployed dump uses the
existing postgres owner through fixed root-owned commands. Production consumer
activation and independent failure-domain monitoring remain gated as recorded
in that status document.

1. Parent fixes production DB target/OID after cutover decision; original remains
   rollback-only until separately authorized acceptance. Install helper/code only
   after review. Establish schema grants/default privileges for **each** real
   object owner and peer mapping; test read/denied-write and restore completeness.
2. Choose an always-on off-host Linux collector, storage quota, repository,
   password escrow, credential lifecycle/ownership and genuinely isolated
   maintenance execution. No laptop-awake assumption. Pin deployment artifacts
   and platform-specific checksums, provision repository explicitly, prove remote
   restic readback, deletion denial for backup identity and maintenance retention.
3. Install root-owned code `/opt/autonomy337/autonomy.py`; create mode0700 service
   state `/var/lib/autonomy337`, service-readable owner-matching mode0600 configs
   `/etc/autonomy337/*.json` and SSH config/key/known_hosts outside HOME (the units
   protect home directories). Do not enable example placeholders unchanged. A
   remote backend avoids widening `ReadWritePaths` for a local repository.
4. Restrict guest backup/issuer ingress as above; `ssh_config` must set
   `BatchMode yes`, `StrictHostKeyChecking yes`, pinned `UserKnownHostsFile`,
   `IdentitiesOnly yes`, `ConnectTimeout 15`, `ServerAliveInterval 15`,
   `ServerAliveCountMax 2`, and no proxy password/secret in command arguments.
5. Implement parent-owned stdin installer/verifier, concrete application probes
   and authenticated external heartbeat/alert delivery. Missing paths currently
   fail, not pass. Add web/FreeHire renewal schedules/checks, and isolate consumers'
   deployment permissions from backup credentials. Verify GitHub App token
   refresh itself and actual macOS supervisor behavior.
6. Run each oneshot manually, read back exact repository snapshots, running
   consumer credentials and external notifications; then install timers. Inspect
   `systemctl list-timers`/`show` and perform reboot/missed-run, failure, expiry,
   notification outage and isolated full-restore drills. Systemd syntax checks
   are not service deployment evidence.
7. Preserve existing original rollback and parent recovery artifacts. Schedule
   periodic full restore, capacity review, certificate/signer rotation and tests
   after PG/Restic upgrades. `validate_identity` intentionally fails after any
   PG17.11 version change until the upgrade is requalified and pin updated.

## Reproduce local tests

Use a scratch directory, not the repository, for temporary repos/keys/databases.
Set `AUTONOMY_RESTIC` to an audited restic binary; unit tests fall back to the
qualification binary path only for this workspace.

```sh
TMPDIR=/Users/tmaerz/.hermes/cache/scratch \
AUTONOMY_RESTIC=/path/to/restic \
python3 -m unittest discover -s ops/autonomy337 -p 'test_*.py' -v

TMPDIR=/Users/tmaerz/.hermes/cache/scratch \
AUTONOMY_RESTIC=/path/to/restic \
python3 ops/autonomy337/integration_pg.py -v
```

Qualification used restic0.19.1 with its release SHA256SUMS verified, native
OpenSSL, and disposable `postgres:17.11` image digest
`sha256:31ba9c94a03ada9988f2bb493a22a75eef3a185884533e5cdbcd498ea835b08f`.
The integration test creates no published ports/host data volumes and removes
its disposable container/anonymous volumes in `finally`. It creates scoped
read-only backup grants, streams3 real dumps into encrypted restic snapshots,
restores1000 rows into a fresh database, forgets1/prunes with2 snapshots retained,
and runs `restic check --read-data`. This is local Docker recovery evidence,
not CT337 deployment, full production-schema recovery or off-site durability.
Systemd units were checked by real `systemd-analyze verify` in a disposable Linux
container; timer calendar expressions were parsed read-only on CT337.
