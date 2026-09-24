"""Apply only the rehearsed deployed migration, with an exact rollback snapshot."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

os.environ['ANTIEK_WRITE_KEEPALIVE_S']='0'
sys.path.insert(0,'/opt/antiek')
import duckdb
from runtime.db_lock import connect_write
from substrate.graph.migrate_v10_account_memory import migrate, _nodes_have_memory, _edges_have_owner, _owner_index_exists

ROOT=Path('/var/lib/antiek-ops-v10-20260924')
DB=Path('/home/antiek/.antiek/antiek.duckdb')
PIN='874345539e9e2f75d9f85f7f2da54a2bf08e9877'
report={'started_at':datetime.now(timezone.utc).isoformat(),'build_sha':PIN}
def save():
    (ROOT/'production-result.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
def q(name):return '"'+name.replace('"','""')+'"'
def compare(con, baseline, allow_audit=False):
    tables=[r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name").fetchall()]
    con.execute("ATTACH '"+str(baseline)+"' AS baseline (READ_ONLY)")
    compared=[]
    try:
        prior_tables=[r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_catalog='baseline' AND table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name").fetchall()]
        assert tables==prior_tables, 'table set changed'
        for table in tables:
            columns=[r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_catalog='baseline' AND table_name=? ORDER BY ordinal_position",[table]).fetchall()]
            selected=','.join(map(q,columns))
            current=f'SELECT {selected} FROM main.{q(table)}'
            prior=f'SELECT {selected} FROM baseline.main.{q(table)}'
            assert not con.execute(f'SELECT EXISTS ({prior} EXCEPT ALL {current})').fetchone()[0], f'original row changed: {table}'
            if allow_audit and table=='write_log':
                extra=con.execute(f'SELECT purpose,success,error FROM ({current} EXCEPT ALL {prior})').fetchall()
                assert len(extra)==1 and extra[0]==('migrate_v10_account_memory',True,None), extra
            else:
                assert not con.execute(f'SELECT EXISTS ({current} EXCEPT ALL {prior})').fetchone()[0], f'unexpected row: {table}'
            compared.append(table)
    finally:
        con.execute('DETACH baseline')
    return compared

assert subprocess.check_output(['git','-C','/opt/antiek','rev-parse','HEAD'],text=True).strip()==PIN
rehearsal=json.loads((ROOT/'rehearsal-result.json').read_text())
assert rehearsal['every_original_row_and_column_equal'] and rehearsal['second_run_noop']
for unit in ['antiek.service','antiek-arxiv-oai-sync.service','antiek-continuous-research.service','antiek-backup.service']:
    assert subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip()=='0', unit+' still executing'
baseline=ROOT/'production-before.duckdb'
clone=ROOT/'production-exact-rehearsal.duckdb'
assert not baseline.exists() and not clone.exists(), 'existing maintenance receipt requires inspection'
live_started=False
try:
    with connect_write(str(DB),purpose='operator_v10_20260924') as con:
        report['before_ready']=[_nodes_have_memory(con),_edges_have_owner(con),_owner_index_exists(con)]
        con.execute('CHECKPOINT')
        shutil.copy2(DB,baseline)
        shutil.copy2(baseline,clone)
        subprocess.run(['/opt/antiek/.venv/bin/python','-m','substrate.graph.migrate_v10_account_memory','--db-path',str(clone)],cwd='/opt/antiek',check=True,env=dict(os.environ,ANTIEK_WRITE_KEEPALIVE_S='0'))
        with duckdb.connect(str(clone)) as candidate:
            report['exact_clone_compared_tables']=compare(candidate,baseline,allow_audit=True)
        report['exact_clone_verified']=True
        save()
        live_started=True
        report['changed']=migrate(con)
        report['after_ready']=[_nodes_have_memory(con),_edges_have_owner(con),_owner_index_exists(con)]
        assert report['after_ready']==[True,True,True]
        report['production_compared_tables']=compare(con,baseline)
        report['second_run_changed']=migrate(con)
        assert report['second_run_changed'] is False
        con.execute('CHECKPOINT')
    report['completed_at']=datetime.now(timezone.utc).isoformat()
    report['status']='applied_and_verified'
    save()
except Exception as exc:
    report['error']=f'{type(exc).__name__}: {exc}'
    if live_started:
        with open(str(DB)+'.write.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            failed=ROOT/'failed-production.duckdb'
            shutil.copy2(DB,failed)
            wal=Path(str(DB)+'.wal')
            if wal.exists():shutil.move(wal,ROOT/'failed-production.duckdb.wal')
            restored=DB.with_suffix('.v10-restore.tmp')
            shutil.copy2(baseline,restored)
            os.replace(restored,DB)
        report['status']='restored_exact_before_snapshot'
    else:report['status']='refused_before_live_migration'
    save()
    raise
print(json.dumps(report,indent=2,default=str))
