#!/usr/bin/env python3
"""Render reviewed full catalog helper without executing migration actions."""
import argparse
import ast
import pathlib


def render(source, container=False):
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'manifest']
    if len(nodes) != 1:
        raise ValueError('unexpected catalog helper source')
    function = ast.get_source_segment(source, nodes[0])
    assert function is not None
    prefix = ['docker', 'exec', 'autonomy337-restore-proof'] if container else ['runuser', '-u', 'postgres', '--']
    header = '''import json,subprocess,pathlib,sys

def sql(db,text,snapshot=None):
    r=subprocess.run(PREFIX+['psql','-U','postgres','-d',db,'-XAtq','-v','ON_ERROR_STOP=1','-c',text],capture_output=True,check=True,timeout=300)
    return r.stdout.decode().strip()
def jsql(db,query,snapshot=None):
    return json.loads(sql(db,"SELECT coalesce(json_agg(x),'[]'::json) FROM ("+query+") x;"))
'''
    footer = "\nprint(json.dumps(manifest('restored'),sort_keys=True))\n" if container else (
        "\ndb=sql('postgres',\"select datname from pg_database where oid=299919\")\n"
        "print(json.dumps(manifest(db),sort_keys=True))\n")
    return 'PREFIX=' + repr(prefix) + '\n' + header + function + footer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', action='store_true')
    args = parser.parse_args()
    source = pathlib.Path(__file__).resolve().with_name('catalog_manifest.py')
    print(render(source.read_text(), args.container), end='')


if __name__ == '__main__':
    main()
