from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_manager_is_registered_only_with_opt_in_bounded_dispatch():
    from scripts.run_workflow_qualification import WORKERS
    assert 'job_manager' in WORKERS
    wf = yaml.safe_load((ROOT / '.github/workflows/job_manager.yml').read_text())
    inputs = wf[True]['workflow_dispatch']['inputs']
    assert inputs['qualification']['default'] is False
    assert 'qualification_expiry_job_id' in inputs
    assert 'qualification_activity_job_id' in inputs


def test_restored_private_ca_workflow_is_manual_only_and_portable():
    p = ROOT / '.github/workflows/jobs_private_ca_qualification.yml'
    assert p.exists()
    text = p.read_text()
    wf = yaml.safe_load(text)
    assert set(wf[True]) == {'workflow_dispatch'}
    assert wf['permissions'] == {'contents': 'read'}
    assert 'migration/precutover337' not in text
    assert wf['jobs']['tls']['env']['JOB_DATA_API_URL'] == '${{ vars.JOB_DATA_API_URL }}'
    assert 'NODE_EXTRA_CA_CERTS' in text
    assert 'hostname mismatch' in text
    assert 'untrusted CA' in text


def test_scrape_qualification_suppresses_only_notifications_not_publication():
    wf = yaml.safe_load((ROOT / '.github/workflows/scrape_jobs.yml').read_text())
    assert "!inputs.suppress_notifications" in wf['jobs']['gate_watchdog']['if']
    assert "!inputs.suppress_notifications" not in wf['jobs']['publication_gate']['if']
    assert "!inputs.suppress_notifications" not in wf['jobs']['freehire_compat']['if']
