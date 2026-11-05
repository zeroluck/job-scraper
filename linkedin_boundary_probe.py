"""Opt-in source evidence only. Never invokes the discovery scheduler.

AST-load original pure parser/policy definitions without initializing Storage,
LLMs, dotenv or scheduler clients. Gate RPC wrappers are the original functions.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import time
import types
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
ANCHOR = datetime.fromisoformat('2026-08-07T20:49:36.259178+00:00')
# Reviewed fixed 100-day evidence-only horizon; not the scheduler's 2160-hour
# historical recovery envelope. Never move the original anchor to fit this cap.
REVIEWED_DIAGNOSTIC_HORIZON_HOURS = 2400
AUTHORIZATION = 'evidence-only-gate-writes-approved'
GUEST = '/jobs-guest/jobs/api/seeMoreJobPostings/search'
RPCS = {'get_scraper_configuration', 'acquire_linkedin_request_grant',
        'consume_linkedin_request_grant', 'finish_linkedin_request_grant',
        'open_linkedin_source_circuit'}
INTERVALS = [
    ('2026-09-15T21:32:36.890075+00:00', '2026-09-17T23:18:37.539668+00:00'),
    ('2026-09-30T10:35:52.865851+00:00', '2026-10-02T06:21:19.632152+00:00'),
    ('2026-10-09T06:21:19.632152+00:00', '2026-10-27T20:53:06.886095+00:00')]


def require_authorization(value):
    if value != AUTHORIZATION:
        raise RuntimeError('explicit gate-write authorization required')


def selected(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text())
    nodes = [n for n in tree.body if getattr(n, 'name', None) in names]
    if {n.name for n in nodes} != set(names):
        raise RuntimeError('original definitions missing')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / path), 'exec'), namespace)


def originals():
    """Execute exact original definitions, not copies or replacement classifiers."""
    from dataclasses import dataclass
    ns = dict(globals(), dataclass=dataclass)
    from collections.abc import Mapping, Sequence
    helpers = dict(globals(), Mapping=Mapping, Sequence=Sequence)
    names = ['_single_rpc_record', 'acquire_linkedin_request_grant',
             'consume_linkedin_request_grant', 'finish_linkedin_request_grant',
             'open_linkedin_source_circuit']
    selected('supabase_utils.py', names, helpers)
    ns['supabase_utils'] = types.SimpleNamespace(**{n: helpers[n] for n in names})
    selected('linkedin_source_policy.py', ['LinkedInCircuitOpen', 'LinkedInGrantRejected',
             'LinkedInRequestDeadlineExceeded', 'linkedin_challenge_evidence',
             'is_linkedin_challenge', 'ConsumedGrant', 'DurableLinkedInRequestGate'], ns)
    # Read the original classifier constants without executing module imports.
    tree = ast.parse((ROOT / 'linkedin_discovery.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') in {
                'NO_RESULTS_SELECTORS', 'NO_RESULTS_RESPONSE_BODIES', 'SCOPE_VERSION'} for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<original-constants>', 'exec'), ns)
    selected('linkedin_discovery.py', ['DiscoveryError', 'classify_search_response',
             '_normalized_text', 'scope_definition', 'scope_key'], ns)
    selected('scraper.py', ['_extract_linkedin_search_cards'], ns)
    # Pure pinned constants; no dotenv or credential initialization.
    config_tree = ast.parse((ROOT / 'config.py').read_text())
    for node in config_tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(getattr(t, 'id', '') in {'REQUEST_TIMEOUT', 'LINKEDIN_JOB_TYPE', 'LINKEDIN_F_WT'} for t in targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<original-source-constants>', 'exec'), ns)
    return types.SimpleNamespace(**ns)


class Boundary:
    """Fail closed at both actual HTTP send boundaries; no ambient clients allowed."""
    def __init__(self, endpoint, seconds=120, limit=20):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != 'https' or not parsed.netloc or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ('', '/', '/rest/v1', '/rest/v1/')):
            raise RuntimeError('invalid expected HTTPS data endpoint')
        if not 0 < seconds <= 120 or not 0 <= limit <= 20:
            raise RuntimeError('invalid physical execution envelope')
        self.origin = (parsed.scheme, parsed.netloc)
        self.deadline = time.monotonic() + seconds
        self.limit, self.attempts = limit, 0
        self.permit = None
        self.last_send = None

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('probe deadline exhausted')
        return remaining

    def pace(self):
        if self.last_send is not None:
            delay = max(0, self.last_send + 2.5 - time.monotonic())
            if delay >= self.remaining():
                raise RuntimeError('probe deadline exhausted during spacing')
            time.sleep(delay)
        self.remaining()

    def __enter__(self):
        import httpx
        self.old_data = httpx.Client.send
        self.old_source = requests.Session.send
        boundary = self
        def data_send(client, request, **kw):
            u = urlsplit(str(request.url))
            if ((u.scheme, u.netloc) != boundary.origin or request.method != 'POST'
                    or u.path not in {'/rest/v1/rpc/' + n for n in RPCS}
                    or u.query or u.fragment):
                raise RuntimeError('unauthorized data HTTP call')
            kw['follow_redirects'] = False
            request.extensions['timeout'] = dict.fromkeys(('connect', 'read', 'write', 'pool'), min(20, boundary.remaining()))
            response = boundary.old_data(client, request, **kw)
            if 300 <= response.status_code < 400:
                raise RuntimeError('data redirect forbidden')
            return response
        def source_send(session, request, **kw):
            u = urlsplit(request.url)
            if (request.method != 'GET' or u.scheme != 'https' or u.netloc != 'www.linkedin.com'
                    or u.path not in {GUEST, '/jobs/search'} or u.fragment
                    or boundary.permit != request.url):
                raise RuntimeError('unauthorized source HTTP call')
            if boundary.attempts >= boundary.limit:
                raise RuntimeError('physical GET budget exhausted')
            boundary.remaining()
            if boundary.last_send is not None and time.monotonic() < boundary.last_send + 2.5:
                raise RuntimeError('physical spacing violated')
            if session.get_adapter(request.url).max_retries.total != 0:
                raise RuntimeError('source nested retries forbidden')
            kw['allow_redirects'] = False
            kw['timeout'] = min(float(kw.get('timeout') or 20), boundary.remaining())
            boundary.permit = None  # Single send per consumed grant, even if transport fails.
            boundary.attempts += 1
            boundary.last_send = time.monotonic()
            return boundary.old_source(session, request, **kw)
        httpx.Client.send = data_send
        requests.Session.send = source_send
        return self

    def __exit__(self, *args):
        import httpx
        httpx.Client.send = self.old_data
        requests.Session.send = self.old_source


def private_write(path, data):
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(data)


def capture(target, view, offset, gate, boundary, original, output, user_agent):
    if view not in {'baseline', 'DD', 'interactive'} or offset not in {0, 240, 250, 260, 300}:
        raise RuntimeError('unreviewed diagnostic unit')
    if boundary.attempts >= boundary.limit:
        raise RuntimeError('physical GET budget exhausted')
    boundary.pace()
    definition = target['definition']
    unit = f"{target['scope_key']}:{view}:{offset}:{boundary.attempts}"
    grant = gate.acquire('search', unit, deadline=boundary.deadline)
    status, kind = None, 'probe_error'
    opened = False
    receipt = {'unit': unit, 'grant_id': grant.grant_id,
               'grant_started_at': grant.started_at.isoformat(), 'view': view, 'offset': offset,
               'scope_parent_hash': target['scope_key'].rsplit(':', 1)[1],
               'bound_contract': 'lower_only', 'inventory_complete': False,
               'variant_support': 'unverified_diagnostic' if view != 'baseline' else 'original_baseline'}
    index = boundary.attempts
    try:
        seconds = math.ceil((grant.started_at - ANCHOR).total_seconds())
        # Frozen anchor is never shifted to fit a later invocation.
        if not 1 <= seconds <= REVIEWED_DIAGNOSTIC_HORIZON_HOURS * 3600:
            kind = 'window_expired'
            raise RuntimeError('frozen original anchor exceeds reviewed 2400-hour diagnostic horizon')
        if any(ANCHOR > datetime.fromisoformat(a) or grant.started_at < datetime.fromisoformat(b) for a, b in INTERVALS):
            raise RuntimeError('source window does not contain all original intervals')
        params = dict(target['query_params'], start=offset, f_TPR=f'r{seconds}')
        if view == 'DD':
            params['sortBy'] = 'DD'
        path = '/jobs/search' if view == 'interactive' else GUEST
        url = 'https://www.linkedin.com' + path + '?' + urlencode(params)
        receipt.update(query_params=params, requested_url=url, source_anchor=ANCHOR.isoformat(), user_agent=user_agent)
        boundary.permit = url
        response = requests.get(url, headers={'User-Agent': user_agent},
                                timeout=min(original.REQUEST_TIMEOUT, boundary.remaining()), allow_redirects=False)
        status = response.status_code
        receipt.update(status=status, final_url=response.url,
                       response_received_at=datetime.now(timezone.utc).isoformat(),
                       headers={k: v for k, v in response.headers.items() if k.lower() in {
                           'content-type', 'content-length', 'date', 'retry-after', 'cf-mitigated', 'content-encoding'}})
        body = response.content
        body_path = f'{index:02d}-{view}-{offset}.body'
        private_write(output / body_path, body)
        receipt.update(body_path=body_path, body_sha256=hashlib.sha256(body).hexdigest(),
                       body_bytes=len(body), body_representation='requests.content (decoded HTTP entity)')
        # Independent regex inventory is not conditioned on the original classifier.
        text = body.decode(response.encoding or 'utf-8', errors='replace')
        receipt['raw_urn_ids'] = sorted(set(re.findall(r'urn:li:jobPosting:(\d+)', text)))
        receipt['raw_link_ids'] = sorted(set(re.findall(r'/jobs/view/(?:[^\s"<>/?]*-)?(\d+)(?=[/?\s"<>]|$)', text)))
        soup = BeautifulSoup(text, 'html.parser')
        receipt['dates'] = [{'datetime': t.get('datetime'), 'text': t.get_text(' ', strip=True)} for t in soup.find_all('time')]
        try:
            kind, _, elements = original.classify_search_response(response)
            receipt['parsed_cards'] = original._extract_linkedin_search_cards(elements)
            receipt['parsed_ids'] = [c['job_id'] for c in receipt['parsed_cards']]
            receipt['element_count'] = len(elements)
        except original.DiscoveryError:
            kind = 'unrecognized_html'
            receipt['parsed_ids'] = []
        receipt['classifier'] = kind
        if kind == 'challenge':
            gate.open_circuit(grant, 'evidence-only source challenge', status)
            opened = True
            raise RuntimeError('source challenge; circuit opened; stop')
        if (status != 200 or response.url != url or response.history
                or kind not in {'cards', 'no_results'}
                or (kind == 'no_results' and (receipt['raw_urn_ids'] or receipt['raw_link_ids']))
                or (kind == 'cards' and not receipt['parsed_ids'] and view != 'interactive')):
            raise RuntimeError('source interrupted; no retry or completeness claim')
        return receipt
    except requests.RequestException:
        kind = 'transport_error'
        raise RuntimeError('source transport interrupted; no retry') from None
    finally:
        receipt['classifier'] = kind
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        try:
            private_write(output / f'{index:02d}-{view}-{offset}.json', (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode())
        finally:
            if not opened:
                gate.finish(grant, kind if kind in {'cards', 'no_results', 'http_error', 'transport_error', 'window_expired'} else 'parser_error', status)


def verify_targets(targets, definitions):
    original = originals()
    if len(targets) != 13 or len(definitions) != 13:
        raise RuntimeError('exactly all 13 original parents required')
    expected = {original.scope_key(d): d for d in definitions}
    if len(expected) != 13 or {t['scope_key'] for t in targets} != set(expected):
        raise RuntimeError('full actual configuration scope set mismatch')
    for target in targets:
        d = target['definition']
        if d != expected[target['scope_key']] or original.scope_key(d) != target['scope_key']:
            raise RuntimeError('original parent definition changed')
        gaps = target['original_gap_intervals']
        if [(g['earliest_at'],g['latest_at']) for g in gaps] != INTERVALS:
            raise RuntimeError('all 39 original intervals required')
        expected_params = {'keywords': d['query'], 'location': d['location'],
                           'geoId': d['geo_id'], 'f_JT': d['job_type'],
                           'f_WT': ','.join(d['work_types']), 'start': 0}
        if target['query_params'] != expected_params or d['partition_filters']:
            raise RuntimeError('original wire query/geography/filter mismatch')


def plan():
    return ([('baseline', n) for n in (240,250,260,300,240)]
            + [('DD', n) for n in (0,240,250,260,300)]
            + [('baseline',0), ('interactive',0)])


def config_digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def run(args):
    require_authorization(args.authorization)
    # This endpoint guard is independent of parent DB-admin identity checks.
    # The probe does not possess an administrative credential or impersonate one.
    if os.environ.get('JOB_DATA_API_URL') != args.expected_endpoint:
        raise RuntimeError('configured data endpoint differs from expected endpoint')
    if not re.fullmatch('[a-f0-9]{64}', args.expected_config_sha256):
        raise RuntimeError('full actual configuration hash required')
    targets_bytes = (ROOT / 'recovery_parameters.json').read_bytes()
    if hashlib.sha256(targets_bytes).hexdigest() != 'ad9d74317a656e42b6a17120890bd1ecd20921060c98225c3cb6a63fe09e2b0c':
        raise RuntimeError('pinned full target manifest changed')
    targets = json.loads(targets_bytes)
    original = originals()
    from data_client import create_data_client
    from scrape_configuration import parse_scrape_configuration, build_search_executions
    import user_agents
    # Default production source UA; parent must independently compare pinned cycle UA.
    user_agent = user_agents.USER_AGENTS[0]
    if args.expected_user_agent_sha256 != hashlib.sha256(user_agent.encode()).hexdigest():
        raise RuntimeError('original source user-agent mismatch')
    output = Path(args.output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    with Boundary(args.expected_endpoint) as boundary:
        db = create_data_client()
        raw = db.rpc('get_scraper_configuration').execute().data
        if isinstance(raw,list) and len(raw) == 1:
            raw = raw[0]
        if config_digest(raw) != args.expected_config_sha256:
            raise RuntimeError('full actual configuration hash mismatch')
        configuration = parse_scrape_configuration(raw)
        definitions = [original.scope_definition(e, original.LINKEDIN_JOB_TYPE, original.LINKEDIN_F_WT)
                       for e in build_search_executions(configuration)]
        verify_targets(targets, definitions)
        # Native spacing belongs to the durable gate RPC policy, not config options.
        # Boundary independently enforces the reviewed local 2500ms send floor.
        # Keep the complete actual configuration, never synthesize a smaller file config.
        private_write(output / 'actual-configuration.json', (json.dumps(raw, indent=2)+'\n').encode())
        private_write(output / 'full-targets.json', targets_bytes)
        sentinel = next(t for t in targets if t['definition']['query'] == 'industrial controls engineer PLC SCADA commissioning')
        gate = original.DurableLinkedInRequestGate('source-boundary-evidence', db=db)
        receipts = []
        try:
            for view, offset in plan():
                receipts.append(capture(sentinel, view, offset, gate, boundary, original, output, user_agent))
        finally:
            private_write(output / 'summary.json', (json.dumps({
                'physical_gets': boundary.attempts, 'all_parent_count': len(targets),
                'original_interval_count': sum(len(t['original_gap_intervals']) for t in targets),
                'configuration_sha256': config_digest(raw), 'inventory_complete': False,
                'purpose': 'sentinel evidence only; not production discovery or backlog drainage',
                'remaining_parents': [t['scope_key'] for t in targets if t != sentinel],
                'successful_units': [r['unit'] for r in receipts],
                'gate_effects': 'acquire/consume/finish and challenge circuit only; may expire unrelated grants, advance policy timing and invalidate other producer grants/unfinished attempts; no reset',
                'database_identity': 'endpoint/config guard only; independent parent administrative identity check required'
            }, indent=2)+'\n').encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization', required=True)
    parser.add_argument('--expected-endpoint', required=True)
    parser.add_argument('--expected-config-sha256', required=True)
    parser.add_argument('--expected-user-agent-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    import signal
    def deadline(signum, frame):
        raise RuntimeError('120-second process deadline elapsed')
    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, 120)
    try:
        run(args)
    except Exception:
        # No SDK/transport exception strings or credential-bearing URLs in logs.
        print('Probe stopped; inspect protected evidence. No completeness claim.')
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
