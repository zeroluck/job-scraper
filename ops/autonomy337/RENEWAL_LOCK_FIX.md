# Staged renewal lock collision: review candidate

This change is not deployed or independently reviewed. It authorizes no issuance,
consumer activation, service mutation, database change or credential change.

## Evidence and diagnosis

Read-only inspection found all three staged renewal configs sharing one state
directory and all three timers sharing the same six-hour calendar, one-minute
accuracy and one-minute randomized delay. At the observed run, runner and web
failed within one millisecond of each other; the publication reader completed
approximately one second later. Their old verified renewals remained intact;
the two latest operation statuses were false. The monitor reported exactly
`failed-operation:1` and `failed-operation:2`. The independent watchdog faithfully
converted that unhealthy monitor result to `verified=false` and `unverified:0`.
Protected state, lock and staged-file ownership/modes matched the issuer UID.
Deployed source SHA256 matched the approved base for both renewal and stage hooks.
No credentials or bearer output were printed.

Ranked hypotheses:

1. Shared nonblocking lock rejects overlapping different-role renewals before
   issuance. Predicts one winner and two immediate failures on the same schedule.
2. Per-role SSH issuer failure. Predicts failure after the issue hook is reached,
   independent of concurrent roles.
3. Staged installer permission or token validation failure. Predicts failure after
   issuance and inconsistent ownership/modes, or an isolated role failure.

The deterministic offline barrier reproduces hypothesis 1 with the published
source: only one of three roles reaches installation; the other two cannot
acquire the shared lock. A direct old-lock probe raises `BlockingIOError` /
`Resource temporarily unavailable`. The production handler deliberately records
only `operation failed`, so there is no retained remote traceback to claim as
observed. The exact underlying exception was reproduced offline, not obtained by
issuing production tokens or rerunning remote services.

## Narrow patch

Give renewal one allowlisted role-specific lock per shared state directory.
Different roles operate on distinct staged files and receipts. Duplicate runs
of the same role remain excluded before issuance. Validate role before choosing
a lock or invoking a hook. Keep the original common lock for backup/retention,
all existing no-follow/owner/hardlink checks, and generic credential-free errors.
Do not change timers, monitoring policy, watchdog code, runtime grants or hooks.

## Verification

```sh
python3 -m unittest discover -s ops/autonomy337 -p 'test*.py' -v
```

The published base has 18 passing tests. This candidate has 22 passing tests.
The added regressions cover forced three-process overlap using disposable local
RSA keys, real signature verification and install/readback hooks; monitor
failure-to-healthy recovery and the actual watchdog process; no token in process
output; same-role exclusion before issuance; invalid roles; symlink/hardlink lock
rejection; and unchanged backup/retention exclusion. The overlap regression was
observed failing against the published base before the lock change. The invalid
`None` role regression was observed failing before the early role check.
No real PostgreSQL restore, production issuance or service execution is included
in these offline claims.

## Safe deployment procedure — only after parent independent review/approval

1. Have an independent reviewer inspect the exact patch and rerun all 22 tests
   from this worktree. Approve a pinned source hash and the deployment separately.
2. Read back deployed hashes, configured staged-only scope and exact unit/hook
   identities. Confirm no production consumer hook is present. Save the old
   `autonomy.py` bytes, ownership/mode and hash outside the release tree.
3. Coordinate a bounded maintenance window for **only the three staged renewal
   timers**. Record whether each was active. Stop those timers, then wait for all
   three renewal services to be inactive. Do not kill an in-flight issuance.
   This drain is mandatory: old and new code use different lock names and must
   never overlap. Do not touch backup, restore, retention, monitor or watchdog
   timers, or any production consumer.
4. Stage only the reviewed `autonomy.py` beside its deployed destination; preserve
   existing root ownership, mode and security labeling. Check hash and parse the
   exact bytes, then replace atomically on the same filesystem. No unit/config
   changes or daemon reload are needed. Keep the old `.lock`; never unlink locks
   to clear contention. New role locks are created by the existing service UID.
5. Once separately authorized to exercise **staged-only** issuance, start the
   three existing staged renewal services concurrently. Require successful exit,
   fresh per-role verified receipts with `staged-only-not-production`, true
   operation statuses, and protected staged-file readback. Never print tokens.
   Restore exactly the timers that were active before the maintenance window.
6. Allow the existing scheduled monitor and independent watchdog to run. Read
   back exact receipts: monitor `ok=true`, empty errors; collector heartbeat
   `verified=true`; watchdog `ok=true`, empty errors. Check delivery verification
   and next scheduled renewal outcomes. Do not clear statuses or weaken health
   checks to force green. Any unrelated staleness remains a separate failure.
7. Rollback: stop only the staged timers and drain the three services again;
   atomically restore the saved source after its hash check; restore prior timer
   activity. Retain failed receipts and all staged credentials; do not edit them
   manually. Reverting reintroduces the original collision, so do not claim it
   restores health. No production consumer or database rollback is involved.

All deployment and recovery steps above remain pending; the present work is
local code/test preparation and read-only evidence collection only.
