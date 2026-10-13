import importlib.util,json,shutil,sys
from pathlib import Path
print('python',sys.version)
for name in ['torch','transformers','diffusers','trimesh','numpy','PIL','omegaconf','accelerate']:
    spec=importlib.util.find_spec(name)
    print(name,spec.origin if spec else 'missing')
try:
    import torch
    print('CUDA',torch.__version__,torch.cuda.is_available())
except Exception as e:print('CUDA_ERROR',str(e))
print('DISK',shutil.disk_usage('/home/aimed'))
