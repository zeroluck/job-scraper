"""Strict bootstrap handling for password-free global-role recovery."""
import json
import re


def canonical_order(manifest):
    """Ignore locale-dependent row ordering only; preserve every field/entry."""
    return {key: sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
            for key, rows in manifest.items()}


def prepare_globals(sql):
    """Replay as postgres, preserving original GRANTED BY postgres semantics.

    PostgreSQL 17 validates ADMIN OPTION for explicit grantors even when a
    different superuser executes GRANT. Use the source bootstrap grantor, not
    a synthetic superuser. Only its already-existing CREATE is omitted.
    """
    if not isinstance(sql, bytes) or re.search(rb'\bPASSWORD\s+', sql, re.I):
        raise ValueError('expected password-free role definitions')
    line = b'CREATE ROLE postgres;'
    rows = sql.splitlines(keepends=True)
    if sum(row.rstrip(b'\r\n') == line for row in rows) != 1:
        raise ValueError('unexpected bootstrap role definitions')
    return b''.join(row for row in rows if row.rstrip(b'\r\n') != line)
