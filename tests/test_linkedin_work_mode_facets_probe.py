"""Work-mode diagnostics: offline only; original parents are never partitions."""
import json
from pathlib import Path
import pytest
from test_linkedin_boundary_probe_native_contract import probe, native_config, runner_args

ROOT = Path(__file__).resolve().parents[1]


def test_exact_work_mode_plan_retains_original_default(probe):
    assert probe.plan('work-mode-facets') == ([('baseline', 0)] +
        [('baseline', offset, facet) for facet in ('1', '2', '3') for offset in (0, 240, 250)] +
        [('baseline', 0)])
    assert len(probe.plan()) == 12
    assert probe.plan('interactive-pagination') == [('interactive', n) for n in (0,60,120,180,240,250,260,300)]


@pytest.mark.parametrize('ignored_facets', [False, True])
def test_full_native_facet_runner_binds_wire_grants_and_parent(probe, native_config, monkeypatch, tmp_path, ignored_facets):
    import copy
    import httpx
    import requests
    from urllib.parse import parse_qs, urlsplit
    before = copy.deepcopy(native_config)
    targets_bytes = (ROOT / 'recovery_parameters.json').read_bytes()
    args = runner_args(probe, tmp_path)
    args.mode = 'work-mode-facets'
    events, urls, grants = [], [], []
    clock = [1000.0]
    def data_send(client, request, **kw):
        name = request.url.path.rsplit('/', 1)[-1]
        events.append(name)
        if name == 'acquire_linkedin_request_grant':
            grants.append(json.loads(request.content))
        values = {'get_scraper_configuration': native_config,
                  'acquire_linkedin_request_grant': {'outcome': 'grant', 'grant_id': str(len(events))},
                  'consume_linkedin_request_grant': {'consumed': True, 'started_at': '2026-11-05T22:00:00+00:00'},
                  'finish_linkedin_request_grant': True}
        return httpx.Response(200, json=values[name], request=request)
    def source_send(session, request, **kw):
        assert events[-1] == 'consume_linkedin_request_grant'
        assert kw['allow_redirects'] is False
        urls.append(request.url)
        params = parse_qs(urlsplit(request.url).query)
        source_id = '123' if ignored_facets or params['f_WT'] == ['1,2,3'] else '200' + params['f_WT'][0]
        r = requests.Response(); r.status_code = 200; r.url = request.url
        r._content = ('<li><div class="base-card" data-entity-urn="urn:li:jobPosting:' + source_id + '"></div></li>').encode()
        return r
    monkeypatch.setattr(httpx.Client, 'send', data_send)
    monkeypatch.setattr(requests.Session, 'send', source_send)
    monkeypatch.setattr(probe.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(probe.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    probe.run(args)
    expected = [('1,2,3', 0)] + [(facet, n) for facet in ('1','2','3') for n in (0,240,250)] + [('1,2,3',0)]
    assert [(parse_qs(urlsplit(u).query)['f_WT'][0], int(parse_qs(urlsplit(u).query)['start'][0])) for u in urls] == expected
    assert all(urlsplit(u).path == probe.GUEST for u in urls)
    assert len(urls) == 11 and len(events) == 34 and clock[0] == 1025
    assert native_config == before
    assert (ROOT / 'recovery_parameters.json').read_bytes() == targets_bytes
    output = tmp_path / 'evidence'
    assert (output / 'full-targets.json').read_bytes() == targets_bytes
    receipts = [json.loads(p.read_text()) for p in sorted(output.glob('[0-9]*.json'))]
    assert len(receipts) == 11
    for r, (facet, offset), grant in zip(receipts, expected, grants):
        assert r['query_params']['f_WT'] == facet and r['offset'] == offset
        assert r['source_anchor'] == probe.ANCHOR.isoformat()
        assert r['inventory_complete'] is False
        if facet != '1,2,3':
            assert r['applied_facet'] == {'f_WT': facet}
            assert r['filter_semantics'] == 'unverified'
            assert ':f_WT=' + facet + ':' in r['unit']
            assert r['unit'] in grant.values()
    summary = json.loads((output / 'summary.json').read_text())
    assert (summary['all_parent_count'], summary['original_interval_count'], summary['physical_gets']) == (13,39,11)
    comparison = summary['work_mode_comparison']
    assert comparison['baseline_repeat_same_raw_id_set'] is True
    assert comparison['candidate_ids_not_in_controls'] == ([] if ignored_facets else ['2001','2002','2003'])
    assert comparison['same_offset_all_facets_same_raw_id_set'] is ignored_facets
    assert comparison['filter_semantics'] == 'unverified'
    assert comparison['partition_complete'] is False
    assert comparison['unknown_work_modes_remain_in_original_parent'] is True
    assert comparison['ingestion_authorized'] is False


@pytest.mark.parametrize('facet,view,offset', [('', 'baseline',0), ('4','baseline',0),
    ('1,2','baseline',0), (1,'baseline',0), ({'f_WT':'1'},'baseline',0),
    ('1','DD',0), ('1','interactive',0), ('1','baseline',260)])
def test_unreviewed_facet_rejected_before_grant(probe, tmp_path, facet, view, offset):
    target = json.loads((ROOT / 'recovery_parameters.json').read_text())[0]
    with pytest.raises(RuntimeError, match='work-mode facet'):
        probe.capture(target,view,offset,None,None,None,tmp_path,'ua',work_type=facet)


def test_workflow_and_cli_accept_only_reviewed_mode(probe, monkeypatch):
    import subprocess
    import sys
    import yaml
    mode = yaml.load((ROOT / '.github/workflows/linkedin_boundary_probe_manual.yml').read_text(),Loader=yaml.BaseLoader)['on']['workflow_dispatch']['inputs']['mode']
    assert mode['default'] == 'boundary'
    assert mode['options'] == ['boundary','interactive-pagination','work-mode-facets']
    help_text = subprocess.run([sys.executable, str(ROOT / 'linkedin_boundary_probe.py'), '--help'],capture_output=True,text=True,check=True).stdout
    assert 'work-mode-facets' in help_text

