"""Download the official archive in independent ranges and verify before installing."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import re
import urllib.request
import subprocess

root=Path('D:/ProjectHub3D/downloads')
base='https://download.blender.org/release/Blender4.5/'
def fetch(url):
    return subprocess.check_output(['curl.exe','-fsSL','--retry','2','--max-time','60',url])
index=fetch(base).decode()
version=max(set(re.findall(r'blender-(4\.5\.\d+)-windows-x64.zip',index)),key=lambda v:tuple(map(int,v.split('.'))))
name=f'blender-{version}-windows-x64.zip'
url=base+name
total=int(re.search(re.escape(name)+r'</a>\s+\S+\s+\S+\s+(\d+)',index).group(1))
checksum=fetch(base+f'blender-{version}.sha256').decode()
expected=next(line.split()[0] for line in checksum.splitlines() if name in line)
def part(i):
    start=i*total//8
    end=(i+1)*total//8-1
    target=root/(name+f'.chunk{i}')
    if target.exists() and target.stat().st_size==end-start+1: return target
    headers=root/(name+f'.headers{i}')
    subprocess.run(['curl.exe','-fsSL','--retry','3','--connect-timeout','20','--max-time','900',
                    '-r',f'{start}-{end}','-D',str(headers),'-o',str(target),url],check=True)
    if '206' not in headers.read_text(): raise RuntimeError('Server did not honor range request')
    if target.stat().st_size!=end-start+1: raise RuntimeError('Incomplete range')
    print('downloaded chunk',i,flush=True)
    return target
with ThreadPoolExecutor(max_workers=8) as pool:
    files=list(pool.map(part,range(8)))
target=root/name
with target.open('wb') as out:
    for p in files:
        with p.open('rb') as f:
            while block:=f.read(1024*1024): out.write(block)
actual=hashlib.sha256(target.read_bytes()).hexdigest()
if actual!=expected: raise RuntimeError('Checksum mismatch')
print('VERIFIED',name,actual,flush=True)
