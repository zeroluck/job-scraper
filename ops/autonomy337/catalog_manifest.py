"""Catalog SQL template extracted verbatim from recovery337/guest_drill.py.

Only the manifest function is vendored: no recovery actions, operational identity,
credentials or runtime data. build_catalog_helper.py supplies sql/jsql wrappers.
This file is parsed as source, not imported or executed by the renderer.
"""

def manifest(db, snapshot=None):
    out = {}
    tables = jsql(db,"SELECT n.nspname AS schema,c.relname AS name,pg_get_userbyid(c.relowner) AS owner,c.relacl::text AS acl,c.relrowsecurity AS rls,c.relforcerowsecurity AS force_rls FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2",snapshot)
    for t in tables:
        name = '"'+t['schema'].replace('"','""')+'"."'+t['name'].replace('"','""')+'"'
        t.update(jsql(db,"SELECT count(*) AS rows,md5(coalesce(string_agg(h,'' ORDER BY h),'')) AS sorted_row_md5 FROM (SELECT md5(row_to_json(t)::text) h FROM "+name+" t) s",snapshot)[0])
    out['tables'] = tables
    queries = {
      'schemas': "SELECT nspname,pg_get_userbyid(nspowner) AS owner,nspacl::text AS acl FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema' ORDER BY 1",
      'columns': "SELECT n.nspname,c.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull,a.attidentity,a.attgenerated,a.attacl::text AS acl,pg_get_expr(d.adbin,d.adrelid) AS default_expr FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE c.relkind IN ('r','v','m') AND a.attnum>0 AND NOT a.attisdropped AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3",
      'constraints': "SELECT n.nspname,c.conname,c.conrelid::regclass::text AS relation,c.contype,c.convalidated,pg_get_constraintdef(c.oid,true) AS definition FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,3,2",
      'policies': "SELECT * FROM pg_policies ORDER BY schemaname,tablename,policyname",
      'functions': "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid) AS args,pg_get_userbyid(p.proowner) AS owner,p.proacl::text AS acl,p.prosecdef,p.proconfig,pg_get_functiondef(p.oid) AS definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND p.prokind IN ('f','p') ORDER BY 1,2,3",
      'indexes': "SELECT n.nspname,c.relname,i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) AS definition FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2",
      'triggers': "SELECT n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid,true) AS definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3",
      'sequences': "SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner) AS owner,c.relacl::text AS acl,s.seqstart,s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace ORDER BY 1,2",
      'sequence_dependencies': "SELECT s.oid::regclass::text AS sequence,t.oid::regclass::text AS relation,a.attname,d.deptype FROM pg_depend d JOIN pg_class s ON s.oid=d.objid AND s.relkind='S' JOIN pg_class t ON t.oid=d.refobjid JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid WHERE d.classid='pg_class'::regclass AND d.refclassid='pg_class'::regclass ORDER BY 1,2,3",
      'default_acl': "SELECT pg_get_userbyid(d.defaclrole) AS owner,n.nspname,d.defaclobjtype,d.defaclacl::text FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace ORDER BY 1,2,3",
      'views': "SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner) AS owner,c.relacl::text AS acl,pg_get_viewdef(c.oid,true) AS definition FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind IN ('v','m') AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2"
    }
    for k,q in queries.items(): out[k]=jsql(db,q,snapshot)
    for s in out['sequences']:
        name='"'+s['nspname']+'"."'+s['relname']+'"'
        s.update(jsql(db,'SELECT last_value,is_called FROM '+name)[0])
    return out
