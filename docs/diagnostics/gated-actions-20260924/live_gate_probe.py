import json, os, sqlite3, subprocess
from pathlib import Path
pid=subprocess.check_output(['systemctl','show','antiek.service','-p','MainPID','--value'],text=True).strip()
env=dict(item.split(b'=',1) for item in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in item)
keys=['ANTIEK_DUCKDB_PATH','ANTIEK_PERSONAL_GRAPHS_DIR','ANTIEK_SHARED_SUBSTRATE_DB','ANTIEK_REMOTE_EXEC_ENABLED','ANTIEK_SPEAK_PUBLIC_PUBLISHING','ANTIEK_STRIPE_PROVIDER','ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED','ANTIEK_PRIME_AGENT_ENABLED','ANTIEK_RLM_RATIFIED']
report={'runtime_configuration':{k:env.get(k.encode(),b'<unset>').decode() for k in keys}}
root=Path('/home/antiek/.antiek')
personal=Path(env.get(b'ANTIEK_PERSONAL_GRAPHS_DIR',str(root/'personal_graphs').encode()).decode())
report['personal_graph_directory_exists']=personal.exists()
report['personal_graph_file_count']=sum(1 for _ in personal.glob('*.duckdb')) if personal.exists() else 0
report['catalogs']=[]
examined=0
for path in root.rglob('*'):
    if not path.is_file() or path.suffix not in ('.sqlite','.sqlite3','.db'):continue
    try:
        con=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        rows=con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='catalog_entries'").fetchall()
        examined+=1
        if rows:report['catalogs'].append({'path':str(path),'entry_count':con.execute('SELECT count(*) FROM catalog_entries').fetchone()[0]})
        con.close()
    except sqlite3.DatabaseError:pass
report['sqlite_databases_inspected']=examined
report['build_sha']=subprocess.check_output(['git','-C','/opt/antiek','rev-parse','HEAD'],text=True).strip()
print(json.dumps(report,indent=2))
