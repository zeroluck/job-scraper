#!/usr/bin/env python3
"""Disposable PG17/PostgREST gate. Never connects to production."""
from __future__ import annotations
from typing import Any
import argparse, ast, base64, hashlib, hmac, json, os, pathlib, secrets, subprocess, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

HERE = pathlib.Path(__file__).resolve().parent
IMPORTER_SHA = '51b7dc71421d088e70cb7742376aa614ceb9189ecc377e2489b609440195b000'
ROLE = 'freehire_source_reader'

def run(*args, data=None, ok=True):
    p = subprocess.run(args, input=data, text=True, capture_output=True)
    if ok and p.returncode:
        raise RuntimeError(p.stderr)
    return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--importer', type=pathlib.Path, required=True)
    ap.add_argument('--baseline', action='store_true')
    ap.add_argument('--receipt', type=pathlib.Path, required=True)
    a = ap.parse_args()
    raw = a.importer.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == IMPORTER_SHA, 'deployed importer hash mismatch'
    # Compile only the unchanged read class/constants/signature. No worker imports,
    # pull orchestration, upsert, destination connection or delete code can execute.
    tree = ast.parse(raw)
    names = {'FULL_COLUMNS','SIGNATURE_COLUMNS','SELECT_COLUMNS','SIGNATURE_SELECT_COLUMNS'}
    nodes: list[ast.stmt] = [n for n in tree.body if
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)
             or isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in ('SupabaseClient','row_signature')]
    import gzip
    ns: dict[str, Any] = dict(Any=object, Callable=__import__('typing').Callable, urlopen=urlopen,
              Request=Request, urlencode=urlencode, gzip=gzip, hashlib=hashlib, json=json)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(a.importer), 'exec', flags=__import__('__future__').annotations.compiler_flag), ns)
    suffix = secrets.token_hex(5)
    net, pg, rest = ('fsr-net-'+suffix, 'fsr-pg-'+suffix, 'fsr-api-'+suffix)
    made = []
    checks = []
    def sql(text, ok=True):
        return run('docker','exec','-i',pg,'psql','-XAtq','-v','ON_ERROR_STOP=1','-U','postgres','-d','jobs', data=text,ok=ok)
    def check(name, value):
        assert value, name
        checks.append(name)
    def install_text():
        text = (HERE/'install.sql').read_text()
        # The ONLY transformed clause is the exact production identity expression.
        # All ACL, shared-role, hook, default and RLS guards execute unchanged.
        identity = "current_database() <> 'jobs' OR (SELECT oid FROM pg_database WHERE datname=current_database()) <> 299919 OR (SELECT system_identifier::text FROM pg_control_system()) <> '7701229561420400865'"
        assert text.count(identity) == 1
        return text.replace(identity, "current_database() <> 'jobs' OR current_setting('server_version_num')::int / 10000 <> 17")
    try:
        run('docker','network','create',net); made.append(('network',net))
        run('docker','run','-d','--name',pg,'--network',net,'--tmpfs','/var/lib/postgresql/data:rw','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=jobs','postgres:17.11'); made.append(('container',pg))
        for _ in range(100):
            if run('docker','exec',pg,'pg_isready','-h','127.0.0.1','-U','postgres',ok=False).returncode == 0: break
            time.sleep(.1)
        instance=json.loads(run('docker','inspect',pg).stdout)[0]
        mounts=instance['Mounts']
        check('fixture database is tmpfs without persistent volume','/var/lib/postgresql/data' in instance['HostConfig'].get('Tmpfs',{}) and not any(m['Type']=='volume' for m in mounts))
        sql((HERE/'fixture.sql').read_text())
        snapshot_query = """SELECT json_build_object(
          'relations',(SELECT json_agg(x ORDER BY oid) FROM (SELECT c.oid,relname,relowner,coalesce(relacl,acldefault(CASE WHEN relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END,relowner)) AS relacl,relrowsecurity,relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','auth'))x),
          'columns',(SELECT json_agg(x ORDER BY attrelid,attnum) FROM (SELECT attrelid,attnum,attname,attacl FROM pg_attribute WHERE attrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace))x),
          'policies',(SELECT json_agg(x ORDER BY oid) FROM pg_policy x),
          'functions',(SELECT json_agg(x ORDER BY oid) FROM (SELECT oid,proname,proowner,proacl,prosrc FROM pg_proc WHERE pronamespace IN ('public'::regnamespace,'auth'::regnamespace))x),
          'schemas',(SELECT json_agg(x ORDER BY oid) FROM (SELECT oid,nspname,nspowner,nspacl FROM pg_namespace WHERE nspname IN ('public','auth'))x),
          'defaults',(SELECT json_agg(x ORDER BY oid) FROM pg_default_acl x),
          'roles',(SELECT json_agg(x ORDER BY oid) FROM pg_roles x),
          'memberships',(SELECT json_agg(x ORDER BY oid) FROM pg_auth_members x),
          'rows',(SELECT md5(json_agg(x ORDER BY job_id)::text) FROM public.jobs x),
          'other',(SELECT md5(json_agg(x)::text) FROM public.other_data x))"""
        before = json.loads(sql(snapshot_query).stdout)
        if not a.baseline:
            literal = sql((HERE/'install.sql').read_text(),ok=False)
            check('literal production identity rejects disposable authority','source reader authority mismatch' in literal.stderr)
            check('identity rejection leaves catalog unchanged',json.loads(sql(snapshot_query).stdout)==before)
            # Drift and candidate execute in the same transaction; remove BOTH
            # transaction delimiters, so no failed assertion can commit a fixture.
            body = install_text().replace('BEGIN;\n','',1).rsplit('COMMIT;',1)[0]
            drift_cases = [
                ('existing role', 'CREATE ROLE freehire_source_reader;', 'source reader already exists'),
                ('existing policy', 'CREATE POLICY freehire_source_reader_linkedin ON jobs USING (true);', 'source reader already exists'),
                ('disabled RLS', 'ALTER TABLE jobs DISABLE ROW LEVEL SECURITY;', 'jobs RLS/owner drift'),
                ('PUBLIC policy', 'CREATE POLICY unsafe ON jobs TO PUBLIC USING (true);', 'jobs RLS/owner drift'),
                ('PUBLIC table', 'GRANT SELECT ON jobs TO PUBLIC;', 'PUBLIC/default ACL drift'),
                ('PUBLIC column', 'GRANT SELECT(notes) ON jobs TO PUBLIC;', 'PUBLIC/default ACL drift'),
                ('PUBLIC function', 'GRANT EXECUTE ON FUNCTION public.forbidden_rpc() TO PUBLIC;', 'PUBLIC/default ACL drift'),
                ('PUBLIC schema CREATE', 'GRANT CREATE ON SCHEMA public TO PUBLIC;', 'PUBLIC/default ACL drift'),
                ('future PUBLIC function', 'ALTER DEFAULT PRIVILEGES FOR ROLE postgres GRANT EXECUTE ON FUNCTIONS TO PUBLIC; CREATE FUNCTION public.future() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$;', 'PUBLIC/default ACL drift'),
                ('gateway inherit', 'ALTER ROLE jobs_gateway INHERIT;', 'gateway authority drift'),
                ('gateway elevated', 'ALTER ROLE jobs_gateway CREATEROLE;', 'gateway authority drift'),
                ('gateway setting', "ALTER ROLE jobs_gateway SET work_mem='8MB';", 'gateway authority drift'),
                ('gateway membership', 'GRANT job_runner TO jobs_gateway WITH ADMIN TRUE;', 'gateway authority drift'),
                ('hook changed', "ALTER FUNCTION auth.require_jwt_claims() SECURITY DEFINER;", 'JWT hook drift'),
            ]
            for name, drift, error in drift_cases:
                result = sql('BEGIN;\n'+drift+'\n'+body+'\nROLLBACK;',ok=False)
                check('guard rejects '+name,result.returncode!=0 and error in result.stderr)
                check('guard rollback '+name,json.loads(sql(snapshot_query).stdout)==before)
            sql(install_text())
        check('dedicated role installed', sql("SELECT count(*) FROM pg_roles WHERE rolname='freehire_source_reader'").stdout.strip() == '1')
        key = secrets.token_urlsafe(48)
        run('docker','run','-d','--name',rest,'--network',net,'-p','127.0.0.1::3000',
            '-e',f'PGRST_DB_URI=postgres://jobs_gateway@{pg}:5432/jobs',
            '-e','PGRST_DB_SCHEMAS=public','-e','PGRST_DB_ANON_ROLE=anon',
            '-e','PGRST_DB_PRE_REQUEST=auth.require_jwt_claims','-e','PGRST_DB_MAX_ROWS=500',
            '-e','PGRST_APP_SETTINGS_JWT_EXPECTED_AUD=source-reader-fixture',
            '-e','PGRST_APP_SETTINGS_JWT_EXPECTED_ISS=https://issuer.invalid',
            '-e',f'PGRST_JWT_SECRET={key}','postgrest/postgrest:v16.5'); made.append(('container',rest))
        port_result = run('docker','port',rest,'3000/tcp',ok=False)
        if port_result.returncode:
            raise RuntimeError(run('docker','logs',rest).stdout + run('docker','logs',rest).stderr)
        port = port_result.stdout.strip().split(':')[-1]
        base = 'http://127.0.0.1:'+port
        def token(claims):
            enc = lambda x: base64.urlsafe_b64encode(json.dumps(x,separators=(',',':')).encode()).rstrip(b'=')
            msg = enc({'alg':'HS256','typ':'JWT'})+b'.'+enc(claims)
            return (msg+b'.'+base64.urlsafe_b64encode(hmac.new(key.encode(),msg,hashlib.sha256).digest()).rstrip(b'=')).decode()
        claims = dict(role=ROLE, exp=int(time.time())+600, aud='source-reader-fixture', iss='https://issuer.invalid')
        bearer = token(claims)
        def http(path, method='GET', body=None, jwt: str | None=bearer):
            headers = {'Authorization':'Bearer '+jwt,'Content-Type':'application/json','Prefer':'return=representation,count=exact'} if jwt else {}
            req = Request(base+path, headers=headers, data=json.dumps(body).encode() if body is not None else None, method=method)
            try:
                with urlopen(req,timeout=10) as r: return r.status, r.read(), dict(r.headers)
            except HTTPError as e: return e.code, e.read(), dict(e.headers)
        for _ in range(100):
            try:
                if http('/jobs?select=job_id&limit=1')[0] == 200: break
            except OSError: pass
            time.sleep(.1)
        client = ns['SupabaseClient'](base,bearer,opener=lambda req: urlopen(Request(req.full_url.replace('/rest/v1/','/'),headers=dict(req.header_items())),timeout=10))
        expected = json.loads(sql('SELECT coalesce(json_agg(x ORDER BY job_id),\'[]\') FROM (SELECT '+ns['SELECT_COLUMNS']+" FROM public.jobs WHERE provider='linkedin')x").stdout)
        metadata, lengths, cursor = [], [], None
        while True:
            page = client.fetch_metadata_after(cursor,500)
            lengths.append(len(page)); metadata.extend(page)
            if len(page)<500: break
            cursor = page[-1]['job_id']
        check('500-row keyset metadata pagination', lengths == [500,500,203])
        check('all 13 metadata values preserved', metadata == [{k:r[k] for k in ns['SIGNATURE_COLUMNS']} for r in expected])
        rows, batch_lengths = [], []
        ids = [r['job_id'] for r in metadata]
        check('text not numeric job_id ordering',ids==sorted(ids) and ids[-3:]==['10','2','9'])
        for cursor in ['abc','١٢','1,2']:
            try:
                client.fetch_metadata_after(cursor,500)
            except ValueError:
                checks.append('invalid cursor rejected '+cursor)
            else:
                raise AssertionError('invalid cursor accepted')
        for start in range(0,len(ids),200):
            page = client.fetch_by_ids(ids[start:start+200]); rows.extend(page);batch_lengths.append(len(page))
        check('200-row full fetch batches',batch_lengths == [200]*6+[3])
        check('all 14 full-row values preserved',rows == expected)
        check('metadata/full signatures equal',[ns['row_signature'](r) for r in rows] == [ns['row_signature'](r) for r in metadata])
        check('failed/unclassified rows retained',sum(r['freehire_category'] is None for r in rows)==12)
        check('terminal empty page',client.fetch_metadata_after(ids[-1],500)==[])
        check('empty ID batch',client.fetch_by_ids([])==[])
        check('ID batches sorted and missing IDs omitted',client.fetch_by_ids([ids[2],ids[0],'9999999999'])==[expected[0],expected[2]])
        check('server row cap',len(json.loads(http('/jobs?select=job_id&limit=900')[1]))==500)
        check('RLS without provider filter',len(json.loads(http('/jobs?select=job_id&job_id=eq.9999999998')[1]))==0)
        check('nonlinkedin and NULL provider excluded',json.loads(http('/jobs?select=job_id&provider=neq.linkedin')[1])==[])
        for path in ('/jobs?select=notes','/jobs?select=*','/other_data?select=*','/rpc/forbidden_rpc','/rpc/get_freehire_publication_state','/jobs?select=job_id&notes=eq.private'):
            check('deny '+path,http(path)[0] in (401,403,404))
        for method, body in [('POST',{'job_id':'777','provider':'linkedin'}),('PATCH',{'company':'changed'}),('DELETE',None)]:
            check('deny '+method,http('/jobs?job_id=eq.'+ids[0],method,body)[0] in (401,403))
        check('deny RPC POST',http('/rpc/forbidden_rpc','POST',{})[0] in (401,403,404))
        for label, mutation in [('missing exp',{'exp':None}),('string exp',{'exp':'Infinity'}),('expired',{'exp':1}),('wrong aud',{'aud':'wrong'}),('wrong iss',{'iss':'https://wrong.invalid'}),('aud array',{'aud':['source-reader-fixture']})]:
            bad = {**claims,**mutation}
            if label=='missing exp': del bad['exp']
            check(label,http('/jobs?select=job_id',jwt=token(bad))[0]==401)
        check('absent token',http('/jobs?select=job_id',jwt=None)[0] in (401,403))
        check('invalid signature',http('/jobs?select=job_id',jwt=bearer[:-3]+'xxx')[0]==401)
        # SQL negatives cannot be hidden by a pre-request failure or API schema cache.
        for statement in ["SELECT notes FROM public.jobs", "SELECT * FROM public.other_data", "SELECT public.forbidden_rpc()", "INSERT INTO public.jobs(job_id) VALUES ('777')", "UPDATE public.jobs SET company='x'", "DELETE FROM public.jobs", "TRUNCATE public.jobs", "CREATE TABLE public.bad(x int)", "SET ROLE job_runner"]:
            result = sql('SET SESSION AUTHORIZATION jobs_gateway; SET ROLE '+ROLE+'; '+statement,ok=False)
            check('SQL deny '+statement,result.returncode!=0 and 'permission denied' in result.stderr)
        check('membership options',sql("SELECT NOT admin_option AND NOT inherit_option AND set_option FROM pg_auth_members WHERE roleid='freehire_source_reader'::regrole AND member='jobs_gateway'::regrole").stdout.strip()=='t')
        allowed = list(ns['FULL_COLUMNS'])+['provider']
        granted = json.loads(sql("SELECT json_agg(attname ORDER BY attname) FROM pg_attribute WHERE attrelid='public.jobs'::regclass AND attnum>0 AND has_column_privilege('freehire_source_reader',attrelid,attnum,'SELECT')").stdout)
        check('exact 15-column SELECT inventory',granted==sorted(allowed))
        check('no table-wide SELECT',sql("SELECT has_table_privilege('freehire_source_reader','public.jobs','SELECT')").stdout.strip()=='f')
        jobs_oid = next(r['oid'] for r in before['relations'] if r['relname']=='jobs')
        for col in before['columns']:
            if col['attrelid']==jobs_oid and col['attname'] not in allowed and col['attnum']>0:
                result=sql('SET SESSION AUTHORIZATION jobs_gateway; SET ROLE '+ROLE+'; SELECT "'+col['attname']+'" FROM public.jobs LIMIT 1',ok=False)
                check('denied column '+col['attname'],result.returncode!=0 and 'permission denied' in result.stderr)
        check('only hook custom function executable',sql("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('public','auth') AND has_function_privilege('freehire_source_reader',p.oid,'EXECUTE') AND p.oid <> 'auth.require_jwt_claims()'::regprocedure").stdout.strip()=='0')
        sql("CREATE TABLE public.future_data(x int); CREATE SEQUENCE public.future_seq; CREATE FUNCTION public.future_rpc() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$; ALTER FUNCTION public.future_rpc() OWNER TO job_runner;")
        for statement in ['SELECT * FROM public.future_data',"SELECT nextval('public.future_seq')",'SELECT public.future_rpc()']:
            result=sql('SET SESSION AUTHORIZATION jobs_gateway; SET ROLE '+ROLE+'; '+statement,ok=False)
            check('future object denied '+statement,result.returncode!=0 and 'permission denied' in result.stderr)
        sql('DROP TABLE public.future_data; DROP SEQUENCE public.future_seq; DROP FUNCTION public.future_rpc();')
        check('publication reader retained capability',sql("SET SESSION AUTHORIZATION jobs_gateway; SET ROLE freehire_publication_reader; SELECT public.get_freehire_publication_state()").stdout.strip()=='123')
        # Reapplication must fail closed, never reconcile or broaden existing state.
        check('second install rejected',sql(install_text(),ok=False).returncode!=0)
        rollback = (HERE/'rollback.sql').read_text()
        identity = "current_database() <> 'jobs' OR (SELECT oid FROM pg_database WHERE datname=current_database()) <> 299919 OR (SELECT system_identifier::text FROM pg_control_system()) <> '7701229561420400865'"
        rollback = rollback.replace(identity,"current_database() <> 'jobs' OR current_setting('server_version_num')::int / 10000 <> 17")
        rollback_before = json.loads(sql(snapshot_query).stdout)
        sql('GRANT SELECT ON public.other_data TO freehire_source_reader')
        check('rollback refuses unexpected dependency',sql(rollback,ok=False).returncode!=0)
        check('failed rollback preserves membership',sql("SELECT count(*) FROM pg_auth_members WHERE roleid='freehire_source_reader'::regrole AND member='jobs_gateway'::regrole").stdout.strip()=='1')
        sql('REVOKE SELECT ON public.other_data FROM freehire_source_reader')
        sql(rollback)
        check('rollback role absent',sql("SELECT count(*) FROM pg_roles WHERE rolname='freehire_source_reader'").stdout.strip()=='0')
        check('rollback preserves rows',sql('SELECT count(*) FROM public.jobs').stdout.strip()=='1206')
        after = json.loads(sql(snapshot_query).stdout)
        changed = [k for k in before if before[k]!=after[k]]
        check('rollback restores catalog and full-row hashes: '+','.join(changed),not changed)
        receipt = dict(result='PASS',checks=checks,postgres=sql('SHOW server_version').stdout.strip(),importer_sha256=IMPORTER_SHA,fixture_rows=1206,linkedin_rows=len(rows),metadata_pages=lengths,full_batches=batch_lengths,production_writes=False,
                       images={image:json.loads(run('docker','image','inspect',image).stdout)[0]['Id'] for image in ['postgres:17.11','postgrest/postgrest:v16.5']},
                       artifact_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir() if p.suffix in ('.py','.sql','.md')})
    finally:
        for kind,name in reversed(made):
            run('docker',kind,'rm',*(['-f'] if kind=='container' else []),name)
            check('cleanup '+kind,run('docker',kind,'inspect',name,ok=False).returncode!=0)
    receipt['check_count']=len(checks)
    a.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__': main()
