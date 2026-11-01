#!/usr/bin/env python3
"""Independent scheduler check; does not detect loss of its own physical host."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('autonomy', HERE / 'autonomy.py')
assert spec is not None and spec.loader is not None
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def main():
    cfg = a.protected_json(sys.argv[1])
    try:
        raw = subprocess.run(cfg['collect'], check=True, capture_output=True,
                             timeout=30).stdout
        status = json.loads(raw)
        if type(status.get('at')) is not int or type(status.get('ok')) is not bool:
            raise ValueError('unsafe scheduler receipt')
        receipt = dict(verified=status['ok'], at=status['at'])
    except Exception:
        receipt = dict(verified=False, at=0)
    a.atomic_json(pathlib.Path(cfg['state'])/'collector-heartbeat.json', receipt)
    result = a.monitor(cfg)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
