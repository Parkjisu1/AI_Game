"""Bound build heap; never stop unrelated services to compile ProjectHub."""
from pathlib import Path
import subprocess,os
stage=Path('/home/aimed/projecthub-3d/web-stage')
env=os.environ.copy();env['NODE_OPTIONS']='--max-old-space-size=4096';env['NEXT_TELEMETRY_DISABLED']='1'
node='/home/aimed/.nvm/versions/node/v20.20.2/bin/node'
env['PATH']=str(Path(node).parent)+':'+env['PATH']
subprocess.run([node,str(stage/'node_modules/next/dist/bin/next'),'build','--webpack'],cwd=stage,env=env,check=True)
