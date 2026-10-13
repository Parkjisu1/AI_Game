"""Experimental local image-to-shape stage. Geometry output still requires texture/rig/art review.

Uses the MIT-licensed TripoSG model, without Bria background-removal weights.
Input must already have a plain white background; the supplied reference meets that condition.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import functools

root=Path('/home/aimed/projecthub-3d')
repo=root/'TripoSG'
os.environ.setdefault('HF_HOME',str(root/'model-cache'))
os.environ.setdefault('PYTORCH_ALLOC_CONF','expandable_segments:True')
# Project-local compatibility patch: use the upstream scikit-image extraction path on hosts without CUDA Toolkit.
file=repo/'triposg/inference_utils.py'
source=file.read_text()
if '\nfrom diso import DiffDMC\n' in source:
    file.write_text(source.replace('\nfrom diso import DiffDMC\n','\n# ProjectHub: DISO is optional when use_flash_decoder=False.\ntry:\n    from diso import DiffDMC\nexcept ImportError:\n    DiffDMC = None\n'))
source=file.read_text()
source=source.replace('high_res_occupancy[indices[:, 0], indices[:, 1], indices[:, 2]] = values\n',
                      'high_res_occupancy[indices[:, 0], indices[:, 1], indices[:, 2]] = values.to(high_res_occupancy.dtype)\n')
file.write_text(source)
sys.path.insert(0,str(repo))
import torch
import trimesh
from PIL import Image, ImageOps
from huggingface_hub import snapshot_download
from triposg.pipelines.pipeline_triposg import TripoSGPipeline

parser=argparse.ArgumentParser()
parser.add_argument('--image',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--steps',type=int,default=35)
args=parser.parse_args()
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
weights=snapshot_download('VAST-AI/TripoSG',local_dir=str(root/'model-cache/TripoSG'),
                          allow_patterns=['*.json','*.safetensors','*.txt','*.md'])
print('WEIGHTS_READY',flush=True)
pipe=TripoSGPipeline.from_pretrained(weights,torch_dtype=torch.float16)
pipe.model_cpu_offload_seq='image_encoder_dinov2->transformer->vae'
pipe.enable_model_cpu_offload()
pipe.vae.decode=functools.partial(pipe.vae.decode,num_chunks=4096)
start=time.monotonic()
with torch.inference_mode(), torch.autocast('cuda',dtype=torch.float16):
    source_image=Image.open(args.image).convert('RGB')
    # Model preprocessing: preserve portrait proportions in the encoder's square input.
    side=max(source_image.size)
    conditioning=ImageOps.pad(source_image,(side,side),color=(255,255,255))
    result=pipe(image=conditioning,num_inference_steps=args.steps,
                generator=torch.Generator('cuda').manual_seed(42),guidance_scale=7,
                use_flash_decoder=False,dense_octree_depth=6,hierarchical_octree_depth=8)
mesh=result.meshes[0]
if not len(mesh.vertices) or not len(mesh.faces): raise RuntimeError('Empty reconstruction')
mesh.export(out/'shape.glb')
mesh.export(out/'shape.ply')
report={'model':'VAST-AI/TripoSG','stage':'shape_only','art_approved':False,'textured':False,'rigged':False,
        'vertices':len(mesh.vertices),'triangles':len(mesh.faces),'bounds':mesh.bounds.tolist(),
        'steps':args.steps,'seed':42,'seconds':time.monotonic()-start,
        'source':args.image,'surface_extractor':'upstream hierarchical + skimage; no DISO',
        'license_url':'https://github.com/VAST-AI-Research/TripoSG/blob/main/LICENSE'}
(out/'generation.json').write_text(json.dumps(report,indent=2))
print('SHAPE_GENERATED',json.dumps(report),flush=True)
