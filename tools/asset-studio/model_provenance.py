from pathlib import Path
import json,subprocess,importlib.metadata
root=Path('/home/aimed/projecthub-3d')
repo=root/'TripoSG'
packages={name:importlib.metadata.version(name) for name in ['torch','diffusers','transformers','trimesh','accelerate']}
result={'repository':'https://github.com/VAST-AI-Research/TripoSG',
        'commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        'license':'MIT','weights':'VAST-AI/TripoSG','packages':packages,
        'local_changes':['Optional DISO import for non-flash decoder path','Cast occupancy tensor writes for PyTorch 2.11'],
        'reference_generation':'OpenAI built-in image generation; original Yasuo-inspired Wind Ronin design',
        'art_approved':False}
(root/'MODEL_PROVENANCE.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
