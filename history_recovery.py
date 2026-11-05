"""Opt-in historical recovery guards; no debt reconciliation or source substitutions."""
import copy
import os
import json
from pathlib import Path


def require_selection(cycle, options, *, partial, scope_keys):
    mode = os.getenv('LINKEDIN_HISTORY_RECOVERY')
    if mode is None:
        return
    if mode == 'new' and cycle is not None:
        raise RuntimeError('new recovery requires no resumable cycle')
    if mode not in {'new', 'resume'}:
        raise RuntimeError('invalid historical recovery mode')
    if mode == 'resume':
        identity = (os.getenv('LINKEDIN_HISTORY_CYCLE_ID', ''), os.getenv('LINKEDIN_HISTORY_SEQUENCE', ''))
        if (not all(v.isascii() and v.isdecimal() and int(v) > 54 for v in identity)
                or not cycle or cycle.get('cycle_id') != int(identity[0])
                or cycle.get('discovery_sequence') != int(identity[1])):
            raise RuntimeError('exact broad recovery resume identity required')
    if (partial or os.getenv('SCRAPE_CONFIG_SOURCE') != 'file'
            or os.getenv('LINKEDIN_RECOVERY_LOOKBACK_HOURS') != '2160'
            or os.getenv('LINKEDIN_DETAIL_ONLY_CYCLE_ID') is not None
            or options.get('recovery_cap') != 2160):
        raise RuntimeError('full file-configured 2160-hour recovery required')
    for name, maximum in [('attempts', 800), ('detail_attempts', 800), ('detail', 300), ('search_runtime', 1620), ('detail_runtime', 300)]:
        value = options.get(name)
        if type(value) is not int or not 0 <= value <= maximum:
            raise RuntimeError('historical recovery budget exceeds reviewed envelope')
    targets = json.loads(Path(os.environ['LINKEDIN_HISTORY_TARGETS']).read_text())
    expected = [t['scope_key'] for t in targets]
    if len(expected) != 13 or len(set(expected)) != 13 or sorted(expected) != sorted(scope_keys):
        raise RuntimeError('historical recovery requires exactly the 13 audited scopes')


def require_drained_queue(db):
    if os.getenv('LINKEDIN_HISTORY_RECOVERY') != 'new':
        return
    response = db.table('linkedin_discovery_tasks').select('id', count='exact', head=True).in_('status', ['pending', 'leased', 'failed_retryable']).execute()
    if type(response.count) is not int or response.count != 0:
        raise RuntimeError('finish guarded cycle54 detail drain before new recovery')


def hydrate_created_cycle(created, selector):
    """Read full persisted scopes independently; never fill them from inputs."""
    persisted = selector(partial=False, scope_keys=None)
    for field in ('cycle_id', 'discovery_sequence'):
        expected = created.get(field)
        actual = persisted.get(field) if isinstance(persisted, dict) else None
        if (type(expected) is not int or expected <= 54
                or type(actual) is not int or actual != expected):
            raise RuntimeError('exact recovery readback identity required')
    original_scopes = created.get('scopes')
    scopes = persisted.get('scopes')
    if (not isinstance(original_scopes, list) or not isinstance(scopes, list)
            or not original_scopes or len(scopes) != len(original_scopes)
            or any(not isinstance(s, dict) or not isinstance(s.get('scope_key'), str)
                   for s in original_scopes + scopes)):
        raise RuntimeError('recovery readback scope set mismatch')
    originals = {s['scope_key']: s for s in original_scopes}
    by_key = {s['scope_key']: s for s in scopes}
    if (len(originals) != len(original_scopes) or len(by_key) != len(scopes)
            or originals.keys() != by_key.keys()):
        raise RuntimeError('recovery readback scope set mismatch')
    window_fields = ('source_window_earliest_at', 'source_window_latest_at',
                     'expired_window_earliest_at', 'expired_window_latest_at',
                     'truncated_window_earliest_at', 'truncated_window_latest_at')
    for key, original in originals.items():
        scope = by_key[key]
        if (not isinstance(scope.get('scope_definition'), dict)
                or any(field not in scope or scope[field] != value
                       for field, value in original.items())
                or any(scope.get(field) != original.get(field) for field in window_fields)):
            raise RuntimeError('recovery readback scope mismatch or missing definition')
    return persisted


def require_manifest(cycle):
    if os.getenv('LINKEDIN_HISTORY_RECOVERY') is None:
        return
    from datetime import datetime
    if not cycle or int(cycle.get('cycle_id', 0)) <= 54 or int(cycle.get('discovery_sequence', 0)) <= 54:
        raise RuntimeError('new broad recovery manifest missing')
    targets = json.loads(Path(os.environ['LINKEDIN_HISTORY_TARGETS']).read_text())
    scopes = cycle.get('scopes') or []
    if len(scopes) != 13 or {s['scope_key'] for s in scopes} != {t['scope_key'] for t in targets}:
        raise RuntimeError('persisted recovery scope set mismatch')
    by_key = {s['scope_key']: s for s in scopes}
    for target in targets:
        scope = by_key[target['scope_key']]
        if 'definition' in target and scope.get('scope_definition') != target['definition']:
            raise RuntimeError('persisted recovery scope definition mismatch')
        earliest = datetime.fromisoformat(scope['source_window_earliest_at'])
        latest = datetime.fromisoformat(scope['source_window_latest_at'])
        if earliest.tzinfo is None or latest.tzinfo is None:
            raise RuntimeError('recovery window must be timezone aware')
        effective = max([earliest] + [datetime.fromisoformat(scope[k]) for k in ('expired_window_latest_at', 'truncated_window_latest_at') if scope.get(k)])
        for gap in target['original_gap_intervals']:
            if effective > datetime.fromisoformat(gap['earliest_at']) or latest < datetime.fromisoformat(gap['latest_at']):
                raise RuntimeError('persisted recovery window does not contain original gap')


def with_recovery_cap(document):
    result = copy.deepcopy(document)
    result['settings']['options']['outage_recovery_cap_hours'] = 2160
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Export full actual scraper configuration with only local recovery cap changed')
    parser.add_argument('--from-file', type=Path, help='Previously exported full actual configuration; omit for read-only live RPC')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.from_file:
        original = json.loads(args.from_file.read_text())
    else:
        import supabase_utils
        original = supabase_utils.supabase.rpc('get_scraper_configuration').execute().data
        if isinstance(original, list) and len(original) == 1:
            original = original[0]
    os.umask(0o077)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(with_recovery_cap(original), stream, indent=2)
        stream.write('\n')
    print('Exported full configuration; only local outage_recovery_cap_hours=2160 changed')
