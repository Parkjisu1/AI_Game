"""Separate TripoSG experiment environment; never modifies Hermes/QLoRA dependencies."""
from pathlib import Path
import subprocess
import sys
import venv
root=Path('/home/aimed/projecthub-3d')
target=root/'ai3d-venv'
venv.create(target,with_pip=True)
site=next((target/'lib').glob('python*/site-packages'))
(site/'existing-torch.pth').write_text('/home/aimed/.venvs/qlora/lib/python3.11/site-packages\n')
subprocess.run([str(target/'bin/python'),'-m','pip','install','trimesh','omegaconf','scikit-image','pymeshlab','jaxtyping','typeguard','opencv-python-headless','einops'],check=True)
print('AI3D environment prepared')
