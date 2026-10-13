import os,sys,json,time,gc
from pathlib import Path
root=Path('C:/ProjectHub3D/cache/trellis2');os.chdir(root);sys.path.insert(0,str(root))
os.environ['HF_HOME']=str(root/'models/hub')
os.environ['ATTN_BACKEND']='xformers';os.environ['SPARSE_ATTN_BACKEND']='xformers'
os.environ['TORCHDYNAMO_DISABLE']='1';os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
os.environ['PYTORCH_CUDA_ALLOC_CONF']='garbage_collection_threshold:0.65'
# A plain-background input does not require the unrelated background-removal model.
file=root/'trellis2/pipelines/trellis2_image_to_3d.py';text=file.read_text(encoding='utf8')
needle="new_pipeline.rembg_model = getattr(rembg, args['rembg_model']['name'])(**args['rembg_model']['args'])"
if needle in text:file.write_text(text.replace(needle,'new_pipeline.rembg_model = None  # ProjectHub: preprocessed white-background input'),encoding='utf8')
import torch,numpy as np,timm
import torch.nn.functional as F
from PIL import Image
from scipy.ndimage import binary_fill_holes
from pipeline_worker import _apply_patches
_apply_patches()
from trellis2.modules import image_feature_extractor
class ProjectHubDinoTimm:
    def __init__(self,checkpoint,image_size=512):
        self.model=timm.create_model('vit_large_patch16_dinov3.lvd1689m',pretrained=False,checkpoint_path=checkpoint,dynamic_img_size=True).eval()
        self.model.norm=torch.nn.Identity();self.image_size=image_size
    def to(self,device):self.model.to(device)
    def cpu(self):self.model.cpu()
    def cuda(self):self.model.cuda()
    @torch.no_grad()
    def __call__(self,images):
        tensor=torch.stack([torch.from_numpy(np.asarray(i.convert('RGB').resize((self.image_size,self.image_size),Image.Resampling.LANCZOS)).copy()).permute(2,0,1) for i in images])
        tensor=tensor.to(next(self.model.parameters()).device,dtype=torch.float32)/255
        mean=tensor.new_tensor([.485,.456,.406])[None,:,None,None];std=tensor.new_tensor([.229,.224,.225])[None,:,None,None]
        tokens=self.model.forward_features((tensor-mean)/std)
        return F.layer_norm(tokens,tokens.shape[-1:])
image_feature_extractor.ProjectHubDinoTimm=ProjectHubDinoTimm
from trellis2.pipelines import Trellis2ImageTo3DPipeline
print('GPU',torch.cuda.get_device_name(),flush=True)
if '--check-imports' in sys.argv:
    import cumesh,o_voxel,nvdiffrast.torch,psutil
    print('IMPORTS_READY','RAM_FREE_GB',round(psutil.virtual_memory().available/2**30,1),flush=True)
    raise SystemExit(0)
requested_resolution='1024' if '--1024' in sys.argv else '512'
pipeline=Trellis2ImageTo3DPipeline.from_pretrained(str(root/('models/ProjectHub-'+requested_resolution)))
pipeline.cuda();print('PIPELINE_READY',flush=True)
source=Image.open('D:/ProjectHub3D/references/wind-ronin-front.png').convert('RGB')
array=np.asarray(source);mask=binary_fill_holes(array.min(axis=2)<245)
yy,xx=np.nonzero(mask);cx=(xx.min()+xx.max())/2;cy=(yy.min()+yy.max())/2
size=int(max(xx.max()-xx.min(),yy.max()-yy.min())*1.04)
conditioning=Image.fromarray(np.where(mask[:,:,None],array,0).astype(np.uint8)).crop((int(cx-size/2),int(cy-size/2),int(cx+size/2),int(cy+size/2)))
out=root/('output/wind-ronin-'+requested_resolution);out.mkdir(parents=True,exist_ok=True)
start=time.monotonic()
with torch.inference_mode():
    result,latents=pipeline.run(conditioning,seed=42,preprocess_image=False,pipeline_type=requested_resolution,return_latent=True,
        sparse_structure_sampler_params={'steps':16},shape_slat_sampler_params={'steps':20},tex_slat_sampler_params={'steps':20})
    mesh=result[0];shape,texture,resolution=latents
    torch.save({'shape_feats':shape.feats.cpu(),'tex_feats':texture.feats.cpu(),'coords':shape.coords.cpu(),'resolution':resolution},out/'latents.pt')
    del latents,shape,texture,result
    for model in pipeline.models.values():model.cpu()
    gc.collect();torch.cuda.empty_cache()
    torch.save({'vertices':mesh.vertices.cpu(),'faces':mesh.faces.cpu(),'attrs':mesh.attrs.cpu(),'coords':mesh.coords.cpu(),'layout':pipeline.pbr_attr_layout,'resolution':resolution},out/'mesh.pt')
    print('SHAPE_TEXTURE_READY',len(mesh.vertices),len(mesh.faces),flush=True)
    import o_voxel
    glb=o_voxel.postprocess.to_glb(vertices=mesh.vertices,faces=mesh.faces,attr_volume=mesh.attrs.float(),coords=mesh.coords,
        attr_layout=pipeline.pbr_attr_layout,grid_size=resolution,aabb=[[-.5,-.5,-.5],[.5,.5,.5]],
        decimation_target=100000,texture_size=4096,remesh=True,remesh_band=1,remesh_project=0,use_tqdm=True)
    glb.export(str(out/'character.glb'))
(out/'generation.json').write_text(json.dumps({'model':'TRELLIS.2-4B low-memory fork','seed':42,'resolution':resolution,'seconds':time.monotonic()-start,'art_approved':False,'source':'wind-ronin-front.png','feature_encoder':'Public timm DINOv3; Built with DINOv3'},indent=2))
print('STYLE_MODEL_COMPLETE',str(out),flush=True)
