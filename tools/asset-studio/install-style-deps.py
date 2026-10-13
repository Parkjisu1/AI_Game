from pathlib import Path
import subprocess,sys
root=Path('C:/ProjectHub3D/cache/trellis2')
def pip(*args):
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check',*args],check=True)
pip('torch==2.8.0','torchvision==0.23.0','--index-url','https://download.pytorch.org/whl/cu128')
pip('imageio','imageio-ffmpeg','tqdm','easydict','opencv-python-headless','ninja','trimesh','transformers==4.57.3',
    'pandas','lpips','zstandard','kornia','timm','huggingface_hub','accelerate','psutil','triton-windows==3.4.0.post21','scipy','pillow')
pip('xformers==0.0.32.post2','--index-url','https://download.pytorch.org/whl/cu128')
for wheel in sorted((root/'whl').glob('*.whl')):
    if wheel.name.lower().startswith('pillow'):continue
    pip(str(wheel))
pip('git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8')
print('STYLE_DEPENDENCIES_INSTALLED',flush=True)
