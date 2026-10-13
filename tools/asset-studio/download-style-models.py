import os,json,concurrent.futures
from pathlib import Path
os.environ['HF_HOME']='C:/ProjectHub3D/cache/trellis2/models/hub'
from huggingface_hub import hf_hub_download,HfApi
root=Path('C:/ProjectHub3D/cache/trellis2/models/ProjectHub-512');root.mkdir(parents=True,exist_ok=True)
api=HfApi();repos=['microsoft/TRELLIS.2-4B','microsoft/TRELLIS-image-large','timm/vit_large_patch16_dinov3.lvd1689m']
revisions={repo:api.model_info(repo).sha for repo in repos}
config=json.loads(Path(hf_hub_download(repos[0],'pipeline.json',revision=revisions[repos[0]])).read_text())
jobs=[]
for name,value in list(config['args']['models'].items()):
    if name.endswith('1024'):
        del config['args']['models'][name];continue
    repo=repos[1] if value.startswith(repos[1]+'/') else repos[0]
    filename=value.removeprefix(repo+'/')
    config['args']['models'][name]=filename
    for extension in ['.json','.safetensors']:jobs.append((repo,filename+extension,root))
jobs.append((repos[2],'model.safetensors',root/'dino-timm'))
jobs.append((repos[2],'README.md',root/'dino-timm'))
def download(job):
    repo,file,target=job
    path=hf_hub_download(repo,file,revision=revisions[repo],local_dir=str(target))
    print('MODEL_FILE_READY',file,Path(path).stat().st_size,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(download,jobs))
config['args']['image_cond_model']={'name':'ProjectHubDinoTimm','args':{'checkpoint':str(root/'dino-timm/model.safetensors')}}
config['args']['default_pipeline_type']='512';config['args']['low_vram']=True
(root/'pipeline.json').write_text(json.dumps(config,indent=2))
(root/'provenance.json').write_text(json.dumps({'revisions':revisions,'feature_adapter':'Public timm DINOv3 weights, raw tokens then layer normalization','background_removal':'white-background mask preprocessing; no RMBG model','attribution':'Built with DINOv3'},indent=2))
print('STYLE_MODELS_READY',flush=True)
