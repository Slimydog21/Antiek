"""Restore the authenticated fresh backup and rehearse the deployed v10 code."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import duckdb

sys.path.insert(0, '/opt/antiek')
from substrate.graph.migrate_v10_account_memory import migrate_at_path

os.umask(0o077)
root = Path('/var/lib/antiek-ops-v10-20260924')
root.mkdir(mode=0o700, exist_ok=True)
marker = json.loads(Path('/home/antiek/.antiek/backup_freshness.json').read_text())
assert marker['archive'] == 'antiek-20260924T085301Z.tar.gz', 'fresh job not certified'
archive = root / marker['archive']
if not archive.exists():
    subprocess.run(['rclone','copyto',marker['remote'],str(archive),'--config','/etc/rclone/rclone.conf'],check=True)
assert hashlib.file_digest(archive.open('rb'),'sha256').hexdigest() == marker['sha256']
(root / 'backup-marker.json').write_text(json.dumps(marker,indent=2)+'\n')
expanded = root / 'restored-export'
expanded.mkdir(exist_ok=True)
with tarfile.open(archive) as tar:
    tar.extractall(expanded, filter='data')
export = next(expanded.glob('*/duckdb'))
manifest = json.loads((export.parent / 'source_manifest.json').read_text())
restored = root / 'restored.duckdb'
needs_import = not restored.exists()
with duckdb.connect(str(restored)) as con:
    if needs_import:
        con.execute("IMPORT DATABASE '" + str(export).replace("'","''") + "'")
    names=[r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name").fetchall()]
    counts={name:con.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in names}
    assert counts == manifest['counts'] == marker['counts']
rehearsal = root / 'rehearsal-v2.duckdb'
assert not rehearsal.exists(), 'do not overwrite prior rehearsal'
shutil.copy2(restored,rehearsal)
report={'build_sha':subprocess.check_output(['git','-C','/opt/antiek','rev-parse','HEAD'],text=True).strip(),'archive_sha256':marker['sha256'],'restored_table_count':len(counts),'restored_counts_match':True}
try:
    report['migration_changed']=migrate_at_path(str(rehearsal))
    report['second_run_changed']=migrate_at_path(str(rehearsal))
except Exception as exc:
    report['migration_error']=f'{type(exc).__name__}: {exc}'
    (root/'rehearsal-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    raise
with duckdb.connect(str(rehearsal)) as con:
    con.execute("ATTACH '" + str(restored) + "' AS baseline (READ_ONLY)")
    different=[]
    for table in names:
        columns=[r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_catalog='baseline' AND table_schema='main' AND table_name=? ORDER BY ordinal_position",[table]).fetchall()]
        selected=','.join('"'+c.replace('"','""')+'"' for c in columns)
        quoted='"'+table.replace('"','""')+'"'
        current=f'SELECT {selected} FROM main.{quoted}'
        prior=f'SELECT {selected} FROM baseline.main.{quoted}'
        removed=con.execute(f'SELECT EXISTS ({prior} EXCEPT ALL {current})').fetchone()[0]
        if table == 'write_log':
            added=con.execute(f'SELECT purpose,success,error FROM ({current} EXCEPT ALL {prior})').fetchall()
            assert len(added)==2 and all(r == ('migrate_v10_account_memory',True,None) for r in added), added
            report['expected_new_write_audit_rows']=len(added)
            if removed:different.append(table)
        elif removed or con.execute(f'SELECT EXISTS ({current} EXCEPT ALL {prior})').fetchone()[0]:
            different.append(table)
    assert not different, different
    assert con.execute('SELECT count(*) FROM edges WHERE owner_user_id IS NOT NULL').fetchone()[0]==0
report['every_original_row_and_column_equal']=True
report['second_run_noop']=not report['second_run_changed']
(root/'rehearsal-result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
