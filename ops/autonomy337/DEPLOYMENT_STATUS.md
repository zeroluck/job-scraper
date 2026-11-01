# Verified Linux deployment and remaining boundaries

## Deployed, not templates

On the always-on ETL Linux guest:

- `autonomy337-repository.service`: authenticated loopback-only rest-server,
  append-only, dedicated `a337repo` UID. Repository is on the existing approved
  off-host NAS backup export, bind-mounted at `/mnt/autonomy337-backups`.
- `autonomy337-backup.service` + `.timer`: daily 03:00 UTC, persistent; streams
  OID-pinned PG17.11 custom dumps and password-free cluster role definitions from
  CT337, encrypts with restic, then authenticates and hashes complete readback.
  Both source exit and full readback must pass before success receipts publish.
- `autonomy337-retention.service` + `.timer`: weekly Sunday 05:00 UTC, persistent;
  root-only maintenance config and direct repository access, not collector
  credentials. Independent jobs/globals floors: newest14 +30 daily +12 weekly.
  Exercised on the live repository, retaining all current snapshots. Real deletion
  and prune are exercised in the disposable PostgreSQL integration test; no live
  production snapshot was deleted to demonstrate retention.
- `autonomy337-monitor.service` + `.timer`: five-minute checks of dump/globals
  freshness, last-operation failures, restore age, credential-stage expiry and
  scheduler liveness. Channel-scoped Discord webhook with POST + exact GET message
  readback. Repeats unchanged alerts hourly and healthy reports daily. Real
  failure, expiry and stale-receipt monitor drills delivered and read back.
- `autonomy337-restore.service` + `.timer`: persistent monthly isolated recovery.
  Uses digest-pinned PG17.11, no container network or published ports, exact source
  UTF8/C.UTF-8 locale, password-free global roles, full owner/ACL-preserving
  restore and all-table hashes/catalog scan. Removes only the container it created;
  rejects an occupied proof container rather than deleting it. Exercised twice
  against real encrypted NAS dumps, with cleanup readback.
- `autonomy337-renew-stage-job_runner.{service,timer}`,
  `autonomy337-renew-stage-job_web.{service,timer}`,
  `autonomy337-renew-stage-freehire_publication_reader.{service,timer}`:
  six-hour real constrained issuance, signature/claim verification and protected
  isolated config installation/readback. Receipts explicitly say
  `staged-only-not-production`. These are NOT production consumer renewals.

On Proxmox:

- `autonomy337-ingress.service`: one narrow source-guest/source-address SSH rule
  ahead of the existing workload host guard. No blanket host-service exception.
- `autonomy337-watchdog.service` + `.timer`: independent five-minute scheduler
  watches ETL monitor heartbeats using fixed `pct exec 335` readback and independently
  delivers verified Discord alerts. It detects collector/timer/guest loss, but
  cannot detect loss of its own physical Proxmox host.
- Five dedicated SSH principals: `a337backup`, `a337globals`, `a337runner`,
  `a337web`, `a337freehire`. Different keys, `restrict` forced commands, exact
  zero-argument sudo wrappers, fixed CT337 actions/configs, pinned host keys.
  No consumer possesses a general Proxmox root key or signing key.

The initial globals-proof oneshot is an exercised static qualification unit, not
an additional scheduler. `deployed-systemd/` records actual ETL definitions and
mandatory drop-ins. The root-owned configs, credentials, host pin and private
artifact receipts remain outside Git.

## Independently exercised recovery

Initial source-versus-restored acceptance compared all12 catalog sections, every
full-row hash/count for47 public tables plus `auth.users`, all7 sequence
structures/values/`is_called`, owners, ACLs, RLS,277 constraints, functions,
policies, triggers, views, default ACLs and sequence dependencies. All matched;
public row total was1,400,308. Only existing logical ACL/physical trigger/toast
normalization and order-only locale-independent sorting were permitted.

Periodic restore receipts are intentionally narrower: authenticated backup
recovery, complete restore and catalog/hash collection, **not** a new claim of
repeatable-read parity with a concurrently changing live source. The original
source-parity receipt is retained separately.

## Security findings corrected

1. NAS export maps credentials such that UID/mode checks alone did **not** prevent
   collector filesystem writes. Actual collector systemd sandbox now hides the
   entire NAS mount, root maintenance/backend configs and issuer home, removes all
   capabilities, disallows new privileges/namespaces/SUID changes, and runs a
   fail-closed filesystem boundary probe before every backup. Successful live
   backup journal contains `collector boundary verified`.
2. Restic0.18.0 `forget` can return exit0 despite a REST DELETE403. Acceptance used
   the actual HTTP403 and exact surviving snapshot readback, not process success.
   Retention itself verifies post-forget inventory before recording success.
3. PostgreSQL17 explicit `GRANTED BY postgres` cannot be recovered correctly by
   inventing a different bootstrap superuser. Isolated recovery now uses postgres,
   omits exactly its already-existing CREATE statement, retains ALTER/membership
   semantics and rejects password-containing role scripts. Regression tests cover
   the filter; the corrected actual globals/full restore passed.
4. Source database locale was C.UTF-8, not the Docker image default. Actual proof
   was rebuilt with exact source locale and all hashes/catalogs rechecked.
5. Signer hardlinks/nonregular files and malformed `nbf` claims are rejected.
   Existing-owner dump mode is root-only, pins cluster/OID/version, resolves the
   same database OID across an authorized rename, and rechecks identity after dump.

The fixed dump capability uses the **existing** postgres owner behind constrained
root-owned commands. No global PostgreSQL role was added/altered, no runtime grant
was widened, and source secrets/signing key were not exported. A scoped backup DB
role remains a coordinated hardening change, not a hidden catalog mutation.

## Explicit noncompletion / external decisions

- **Web:** no production runtime/controller edit or restart. Architecture/security
  review and an external-shell launchd authorization gate remain. Do not use the
  rejected web controller or activate the staged web renewal timer as a consumer.
- **Runner:** no GitHub secret write or workflow dispatch. A repository-scoped
  GitHub App secret-write installation/refresh credential plus approved functional
  readback is still required; an existing personal gh login is not that identity.
- **FreeHire:** no production restart or endpoint switch. Reader issuance/stage is
  working, but deployment-approved consumer installation and live consumer readback
  remain gated by the parent. Its separate application DB was untouched.
- **Whole-site/host outage:** Discord delivery is real, but a separately hosted
  external absent-heartbeat check/receiver is not configured. Need an approved
  external watchdog/check credential or an independent always-on execution host.
  The Proxmox-side watchdog does not meet that failure-domain requirement.
- Logical jobs + password-free globals only: not PITR/WAL, legacy objects,
  signing/TLS keys, HBA or arbitrary system configuration. The signing key was
  explicitly not exported. Decryption password is protected on the always-on
  collector and separately escrowed with the operator, never in Git/output.
- Reboot/missed-run behavior is encoded in persistent calendar timers and verified
  unit state/syntax; no production host/guest reboot was performed for a drill.
- Version/identity pins deliberately fail closed after an unqualified PG/image
  upgrade. No honest claim of zero future operational ownership is possible.

## Portable catalog renderer

`build_catalog_helper.py` reads the adjacent `catalog_manifest.py`, containing
only the verbatim 12-section `manifest` function from the reviewed recovery
helper. No migration tree, recovery entry point, private deployment configuration
or receipt is required. Rendering emits code without executing SQL or a restore;
installing/executing the rendered helper remains a separate privileged action.
Offline `test_catalog_helper.py` checks standalone rendering for both targets,
malformed templates, section coverage, row hashes and sequence-state collection.
The original sequence/non-MVCC and live-source parity limitations still apply.

## Reproduce code checks

```sh
python3 -m unittest discover -s ops/autonomy337 -p 'test*.py' -v
AUTONOMY_RESTIC=/path/to/restic python3 ops/autonomy337/integration_pg.py -v
python3 ops/autonomy337/build_catalog_helper.py --container
```

Original local suite:15 tests passed; publication suite adds3 offline catalog
renderer regressions (18 tests total). Disposable real PG17.11/restic integration
passed during the original qualification; publication preparation does not rerun
restores or deployment drills. Live Linux source/readback/restore/alert units were
separately exercised during that qualification.
No DB/API promotion or writer activation was performed by this workstream.
