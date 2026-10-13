import os,json,concurrent.futures
from pathlib import Path
os.environ['HF_HOME']='C:/ProjectHub3D/cache/trellis2/models/hub'
from huggingface_hub import hf_hub_download
base=Path('C:/ProjectHub3D/cache/trellis2/models/ProjectHub-512');root=base.with_name('ProjectHub-1024');root.mkdir(exist_ok=True)
config=json.loads((base/'pipeline.json').read_text());provenance=json.loads((base/'provenance.json').read_text())
repo='microsoft/TRELLIS.2-4B';revision=provenance['revisions'][repo];jobs=[]
for name,value in list(config['args']['models'].items()):
    if name.endswith('512'):
        del config['args']['models'][name]
        filename=value.replace('512','1024');config['args']['models'][name.replace('512','1024')]=filename
        jobs.extend(filename+extension for extension in ['.json','.safetensors'])
    else:config['args']['models'][name]='../ProjectHub-512/'+value
def download(file):
    hf_hub_download(repo,file,revision=revision,local_dir=str(root));print('READY',file,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(download,jobs))
config['args']['default_pipeline_type']='1024'
(root/'pipeline.json').write_text(json.dumps(config,indent=2));(root/'provenance.json').write_text(json.dumps(provenance,indent=2))
print('STYLE_1024_READY',flush=True)
