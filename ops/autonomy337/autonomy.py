#!/usr/bin/env python3
"""CT337 unattended operations. Errors intentionally exclude command diagnostics."""
import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import time


def protected_json(path, owner_uid=None):
    if owner_uid is None:
        owner_uid = os.geteuid()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError('unsafe config') from None
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('unsafe config')
        return json.load(stream)


def atomic_json(path, data):
    path = pathlib.Path(path)
    fd, temp = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, sort_keys=True)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        pathlib.Path(temp).unlink(missing_ok=True)


@contextlib.contextmanager
def locked(state, owner_uid=None, *, renewal_role=None):
    if renewal_role is not None and renewal_role not in ROLES:
        raise ValueError('invalid renewal role')
    if owner_uid is None:
        owner_uid = os.geteuid()
    state = pathlib.Path(state)
    info = state.lstat()
    if state.is_symlink() or info.st_uid != owner_uid or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('unsafe state directory')
    # Renewal hooks and receipts are role-specific even when their state is shared.
    # Preserve the existing common lock for backup/retention callers.
    name = '.lock' if renewal_role is None else '.lock-renew-' + renewal_role
    fd = os.open(state / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != owner_uid:
            raise ValueError('unsafe lock')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield state


def restic(cfg, args):
    # Never inherit arbitrary RESTIC_* or cloud credentials from the service manager.
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(pathlib.Path.home()), **cfg['restic_env']}
    return subprocess.run([cfg['restic'], *args], env=env, capture_output=True,
                          check=True, timeout=cfg['timeout']).stdout


def backup(cfg):
    import threading
    artifact = cfg.get('artifact', 'jobs')
    scopes = {'jobs': ('jobs.dump', 'autonomy337', 'postgres-custom-dump-only'),
              'globals': ('roles.sql', 'autonomy337-globals', 'password-free-cluster-role-definitions')}
    if artifact not in scopes:
        raise ValueError('invalid backup artifact')
    filename, tag, scope = scopes[artifact]
    with locked(cfg['state']) as state:
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(pathlib.Path.home()), **cfg['restic_env']}
        # Restic encrypts/authenticates on the off-host collector; no decryption key on CT337.
        source = subprocess.Popen(cfg['source'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        assert source.stdout is not None
        try:
            sink = subprocess.Popen([cfg['restic'], 'backup', '--stdin', '--stdin-filename', filename,
                                     '--tag', tag, '--host', 'ct337', '--json'],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, env=env)
        except BaseException:
            source.kill()
            source.wait()
            source.stdout.close()
            raise
        assert source.stdout is not None and sink.stdin is not None and sink.stdout is not None
        digest = hashlib.sha256()
        totals = [0]
        errors = []
        def pump():
            try:
                for chunk in iter(lambda: source.stdout.read(1024 * 1024), b''):
                    sink.stdin.write(chunk)
                    digest.update(chunk)
                    totals[0] += len(chunk)
            except Exception:
                errors.append(True)
            finally:
                sink.stdin.close()
                source.stdout.close()
        worker = threading.Thread(target=pump, daemon=True)
        worker.start()
        output_chunks = []
        reader = threading.Thread(target=lambda: output_chunks.append(sink.stdout.read()), daemon=True)
        reader.start()
        try:
            sink.wait(timeout=cfg['timeout'])
            source.wait(timeout=cfg['timeout'])
            worker.join(timeout=2)
            reader.join(timeout=2)
            output = b''.join(output_chunks)
            if worker.is_alive() or errors or source.returncode or sink.returncode or not totals[0]:
                raise ValueError('backup stream failed')
        finally:
            for process in (sink, source):
                if process.poll() is None: process.kill()
                process.wait()
            worker.join(timeout=2)
            sink.stdout.close()
        summaries = [json.loads(line) for line in output.splitlines()]
        snapshot = next(x['snapshot_id'] for x in summaries if x.get('message_type') == 'summary')
        # Authenticated full readback; never buffer a database dump in RAM or on disk.
        readback = subprocess.Popen([cfg['restic'], 'dump', snapshot, '/' + filename],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        verified_hash = hashlib.sha256()
        timer = threading.Timer(cfg['timeout'], readback.kill)
        timer.start()
        try:
            for chunk in iter(lambda: readback.stdout.read(1024 * 1024), b''):
                verified_hash.update(chunk)
            if readback.wait() or verified_hash.digest() != digest.digest():
                raise ValueError('backup readback failed')
        finally:
            timer.cancel()
            readback.stdout.close()
            if readback.poll() is None: readback.kill()
            readback.wait()
        receipt = dict(kind='backup', verified=True, snapshot=snapshot, at=int(time.time()),
                       sha256=digest.hexdigest(), bytes=totals[0], scope=scope)
        atomic_json(state / ('backup-' + snapshot + '.json'), receipt)
        atomic_json(state / 'latest-backup.json', receipt)
        atomic_json(state / 'status-backup.json', dict(ok=True, at=receipt['at']))
        return receipt


def validate_identity(cfg, fields):
    expected = [cfg['system_identifier'], cfg['database'], str(cfg['database_oid'])]
    if fields[:3] != expected or len(fields) != 4 or int(fields[3]) != 170011:
        raise ValueError('database identity mismatch')


def guest_dump(cfg):
    # This entry point must run as the dedicated peer-authenticated backup OS user.
    # No TCP, password, caller-selected SQL, role or database is accepted on stdin.
    database = cfg['database']
    if cfg.get('resolve_database_oid'):
        if not cfg.get('existing_owner_dump') or os.geteuid() != 0 or type(cfg['database_oid']) is not int:
            raise ValueError('invalid OID resolution boundary')
        resolved = subprocess.run(
            ['/usr/sbin/runuser', '-u', 'postgres', '--', '/usr/lib/postgresql/17/bin/psql',
             '-h', '/var/run/postgresql', '-d', 'postgres', '-XAtw', '-c',
             'select datname from pg_database where oid=' + str(cfg['database_oid'])],
            capture_output=True, check=True, timeout=30).stdout.decode().strip()
        cfg = {**cfg, 'database': resolved}
        database = resolved
    if not database.replace('_', '').isalnum():
        raise ValueError('invalid database')
    # Root-owned opt-in permits constrained dumps with the existing postgres
    # identity while catalog/global-role changes are fenced by migration review.
    existing_owner = cfg.get('existing_owner_dump', False)
    if type(existing_owner) is not bool or (existing_owner and os.geteuid() != 0):
        raise ValueError('invalid existing-owner dump boundary')
    prefix = ['/usr/sbin/runuser', '-u', 'postgres', '--'] if existing_owner else []
    role = 'postgres' if existing_owner else 'job_backup'
    args = ['-h', '/var/run/postgresql', '-U', role, '-d', database, '-w']
    env = {'PATH': '/usr/bin:/bin', 'PGOPTIONS': '-c default_transaction_read_only=on -c statement_timeout=300000'}
    sql = ("select (select system_identifier::text from pg_control_system()), current_database(), "
           "(select oid::text from pg_database where datname=current_database()), "
           "current_setting('server_version_num')")
    raw = subprocess.run([*prefix, '/usr/lib/postgresql/17/bin/psql', *args, '-XAt', '-F', '|', '-c', sql],
                         env=env, capture_output=True, check=True, timeout=30).stdout
    validate_identity(cfg, raw.decode().strip().split('|'))
    result = subprocess.run([*prefix, '/usr/lib/postgresql/17/bin/pg_dump', *args, '--format=custom',
                             '--lock-wait-timeout=30000'], env=env, stderr=subprocess.DEVNULL,
                            timeout=cfg['timeout'])
    if result.returncode:
        raise ValueError('database dump failed')
    # A concurrent rename/name reuse between preflight and pg_dump must not
    # publish a successful stream. pg_dump sessions prevent rename while open.
    after = subprocess.run([*prefix, '/usr/lib/postgresql/17/bin/psql', *args, '-XAt', '-F', '|', '-c', sql],
                           env=env, capture_output=True, check=True, timeout=30).stdout
    validate_identity(cfg, after.decode().strip().split('|'))


def guest_roles(cfg):
    if os.geteuid() != 0:
        raise ValueError('existing-owner role dump requires root boundary')
    prefix = ['/usr/sbin/runuser', '-u', 'postgres', '--']
    binary = '/usr/lib/postgresql/17/bin/'
    row = subprocess.run([*prefix, binary+'psql', '-h', '/var/run/postgresql', '-d', 'postgres',
                          '-XAtw', '-c', "select system_identifier::text||'|'||current_setting('server_version_num') from pg_control_system()"],
                         capture_output=True, check=True, timeout=30).stdout.decode().strip()
    if row != cfg['system_identifier'] + '|170011':
        raise ValueError('cluster identity mismatch')
    result = subprocess.run([*prefix, binary+'pg_dumpall', '-h', '/var/run/postgresql',
                             '-w', '--roles-only', '--no-role-passwords'],
                            stderr=subprocess.DEVNULL, timeout=cfg['timeout'])
    if result.returncode:
        raise ValueError('role dump failed')


ROLES = {'job_runner', 'job_web', 'freehire_publication_reader'}


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=')


def issue(cfg):
    # Forced-command config pins exactly one role. No arbitrary message signing API.
    if cfg['role'] not in ROLES:
        raise ValueError('invalid issuer role')
    key = pathlib.Path(cfg['private_key'])
    info = key.lstat()
    if (key.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise ValueError('unsafe signer')
    now = int(time.time())
    claims = dict(role=cfg['role'], aud='job-http-qualification', iss='job-qualification',
                  iat=now, nbf=now-30, exp=now+86400)
    header = dict(alg='RS256', typ='JWT', kid='prepared-signing')
    message = b64(json.dumps(header, separators=(',', ':')).encode()) + b'.' + b64(json.dumps(claims, separators=(',', ':')).encode())
    signature = subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(key)],
                               input=message, capture_output=True, check=True, timeout=20).stdout
    return (message + b'.' + b64(signature)).decode()


def verify_token(cfg, token):
    pieces = token.split('.')
    if len(pieces) != 3:
        raise ValueError('invalid credential')
    decode = lambda value: base64.urlsafe_b64decode(value + '===')
    header, claims = json.loads(decode(pieces[0])), json.loads(decode(pieces[1]))
    now = int(time.time())
    if (header != dict(alg='RS256', typ='JWT', kid='prepared-signing')
            or claims.get('role') != cfg['role'] or cfg['role'] not in ROLES
            or claims.get('iss') != 'job-qualification' or claims.get('aud') != 'job-http-qualification'
            or type(claims.get('exp')) is not int or type(claims.get('iat')) is not int
            or type(claims.get('nbf')) is not int or claims['nbf'] != claims['iat']-30
            or not 82800 <= claims['exp']-now <= 86460
            or claims['exp']-claims['iat'] != 86400 or abs(claims['iat']-now) > 60):
        raise ValueError('invalid credential claims')
    with tempfile.NamedTemporaryFile() as signature:
        signature.write(decode(pieces[2])); signature.flush()
        subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-verify', cfg['public_key'],
                        '-signature', signature.name], input=(pieces[0]+'.'+pieces[1]).encode(),
                       capture_output=True, check=True, timeout=20)
    return claims


def renew(cfg):
    if cfg['role'] not in ROLES:
        raise ValueError('invalid renewal role')
    with locked(cfg['state'], renewal_role=cfg['role']) as state:
        token = subprocess.run(cfg['issue'], capture_output=True, check=True,
                               timeout=cfg['timeout']).stdout.decode().strip()
        claims = verify_token(cfg, token)
        for command in (cfg['install'], cfg['verify']):
            subprocess.run(command, input=token.encode(), capture_output=True, check=True,
                           timeout=cfg['timeout'])
        receipt = dict(kind='renew', role=cfg['role'], at=int(time.time()),
                       expires_at=claims['exp'], verified=True,
                       scope=cfg.get('scope', 'configured-installer-and-verifier-hooks'))
        atomic_json(state / ('renew-' + cfg['role'] + '.json'), receipt)
        atomic_json(state / ('status-renew-' + cfg['role'] + '.json'), dict(ok=True, at=receipt['at']))
        return receipt


def retention_plan(cfg, rows, now):
    rows = sorted(rows, key=lambda row: row['at'], reverse=True)
    if (cfg['keep_last'] < 2 or not rows or any(r.get('verified') is not True for r in rows)
            or not 0 <= now-rows[0]['at'] <= cfg['max_backup_age']):
        raise ValueError('retention safety gate failed')
    keep = {row['snapshot'] for row in rows[:cfg['keep_last']]}
    for width, count in ((86400, cfg['keep_daily']), (604800, cfg['keep_weekly'])):
        buckets = set()
        for row in rows:
            # UTC calendar daily buckets; weekly buckets anchored to Unix epoch.
            bucket = row['at'] // width
            if bucket not in buckets and len(buckets) < count:
                keep.add(row['snapshot']); buckets.add(bucket)
    return [row['snapshot'] for row in rows if row['snapshot'] not in keep]


def retention(cfg):
    with locked(cfg['state'], cfg.get('state_owner_uid')) as state:
        rows = [protected_json(p, cfg.get('state_owner_uid')) for p in state.glob('backup-*.json')]
        candidates = retention_plan(cfg, rows, int(time.time()))
        # A separate off-host maintenance identity, never the append-only writer.
        restic(cfg, ['check'])
        tag = {'jobs': 'autonomy337', 'globals': 'autonomy337-globals'}[cfg.get('artifact', 'jobs')]
        snapshots = json.loads(restic(cfg, ['snapshots', '--json', '--tag', tag, '--host', 'ct337']))
        ids = {snapshot['id'] for snapshot in snapshots}
        def resolve(short):
            matches = [value for value in ids if value.startswith(short)]
            if len(matches) != 1: raise ValueError('snapshot inventory mismatch')
            return matches[0]
        # Resolve ALL receipts before deletion; changed repository or missing backup fails closed.
        mapped = {row['snapshot']: resolve(row['snapshot']) for row in rows}
        deleting = [mapped[value] for value in candidates]
        if deleting:
            restic(cfg, ['forget', *deleting])
            after = json.loads(restic(cfg, ['snapshots', '--json']))
            after_ids = {snapshot['id'] for snapshot in after}
            if after_ids.intersection(deleting) or not (ids-set(deleting)).issubset(after_ids):
                raise ValueError('retention readback failed')
            for value in candidates:
                (state / ('backup-' + value + '.json')).unlink()
        if cfg.get('prune', False): restic(cfg, ['prune'])
        result = dict(ok=True, at=int(time.time()), forgotten=len(deleting), retained=len(rows)-len(deleting))
        atomic_json(state / 'status-retention.json', result)
        return result


def monitor(cfg):
    now = int(time.time())
    errors = []
    if not cfg['checks']:
        errors.append('no-checks')
    for index, check in enumerate(cfg['checks']):
        try:
            receipt = protected_json(check['path'], check.get('owner_uid'))
            if receipt.get('verified') is not True: errors.append('unverified:' + str(index))
            if not 0 <= now-receipt['at'] <= check['max_age']: errors.append('stale:' + str(index))
            if check.get('min_remaining') and receipt.get('expires_at', 0)-now < check['min_remaining']:
                errors.append('expiring:' + str(index))
        except Exception:
            errors.append('missing-or-invalid:' + str(index))
    for index, entry in enumerate(cfg['statuses']):
        try:
            path = entry['path'] if isinstance(entry, dict) else entry
            status = protected_json(path, entry.get('owner_uid') if isinstance(entry, dict) else None)
            if status.get('ok') is not True: errors.append('failed-operation:' + str(index))
            if isinstance(entry, dict) and not 0 <= now-status['at'] <= entry['max_age']:
                errors.append('stale-operation:' + str(index))
        except Exception:
            errors.append('missing-status:' + str(index))
    for index, command in enumerate(cfg['probes']):
        try:
            subprocess.run(command, capture_output=True, check=True, timeout=cfg['timeout'])
        except Exception:
            errors.append('probe-failed:' + str(index))
    result = dict(ok=not errors, errors=errors, at=now)
    try:
        # Called on success too: the receiver must independently alert on absent heartbeats.
        subprocess.run(cfg['notify'], input=json.dumps(result).encode(), capture_output=True,
                       check=True, timeout=cfg['timeout'])
    except Exception:
        result['errors'].append('notification-failed'); result['ok'] = False
    atomic_json(pathlib.Path(cfg['state']) / 'status-monitor.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'guest-dump', 'guest-roles', 'issue', 'renew', 'retention', 'monitor'])
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    cfg = None
    try:
        cfg = protected_json(args.config)
        if args.action == 'issue':
            # Bearer output is ONLY for the SSH pipe, never the service journal.
            sys.stdout.write(issue(cfg))
            return 0
        if args.action in {'guest-dump', 'guest-roles'}:
            (guest_dump if args.action == 'guest-dump' else guest_roles)(cfg)
            return 0
        result = globals()[args.action](cfg)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('ok', True) else 1
    except (Exception, KeyboardInterrupt):
        if cfg and args.action in {'backup', 'renew', 'retention'}:
            try:
                suffix = args.action + ('-' + cfg['role'] if args.action == 'renew' and cfg.get('role') in ROLES else '')
                atomic_json(pathlib.Path(cfg['state']) / ('status-' + suffix + '.json'),
                            dict(ok=False, at=int(time.time()), error='operation failed'))
            except Exception:
                pass
        print(json.dumps(dict(ok=False, error='operation failed')), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
