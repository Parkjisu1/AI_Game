"""Install a successfully built overlay with backups; call only after build and route checks."""
from pathlib import Path
import shutil
from datetime import datetime, timezone
import subprocess

root=Path('/home/aimed/projecthub-web')
stage=Path('/home/aimed/projecthub-3d/web-stage')
stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
backup=Path('/home/aimed/projecthub-3d/backups')/stamp
if not (stage/'.next/BUILD_ID').is_file(): raise RuntimeError('Successful build missing')
backup.mkdir(parents=True)
paths=['src/lib/asset-studio.ts','src/app/assets-3d','src/app/api/assets-3d','public/asset-studio',
       'src/components/paper/Rail.tsx','src/components/TopNav.tsx','src/components/InstrumentNav.tsx',
       'src/app/layout.tsx','src/app/api/agents/roles/route.ts','next.config.ts']
for rel in paths:
    source,target=stage/rel,root/rel
    old=backup/rel
    if target.exists():
        old.parent.mkdir(parents=True,exist_ok=True)
        if target.is_dir(): shutil.copytree(target,old)
        else: shutil.copy2(target,old)
    target.parent.mkdir(parents=True,exist_ok=True)
    if source.is_dir(): shutil.copytree(source,target,dirs_exist_ok=True)
    else: shutil.copy2(source,target)
# Retain prior hashed browser bundles during rolling client navigation.
for source in (root/'.next/static').rglob('*'):
    if source.is_file():
        target=stage/'.next/static'/source.relative_to(root/'.next/static')
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
subprocess.run(['systemctl','--user','stop','projecthub-web'],check=True)
try:
    (root/'.next').rename(backup/'.next')
    (stage/'.next').rename(root/'.next')
finally:
    subprocess.run(['systemctl','--user','start','projecthub-web'],check=True)
print('Deployed. Backup:',backup)
