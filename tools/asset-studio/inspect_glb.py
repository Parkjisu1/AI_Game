from pathlib import Path
import json,struct
root=Path(__file__).resolve().parents[2]/'output/asset-studio'
data=(root/'Wind-Ronin-style-v26.glb').read_bytes();length=struct.unpack_from('<I',data,12)[0]
doc=json.loads(data[20:20+length]);print(json.dumps({k:doc.get(k) for k in ['materials','textures','images','extensionsUsed']},indent=2))
offset=20+length+8
for i,image in enumerate(doc['images']):
    view=doc['bufferViews'][image['bufferView']];start=offset+view.get('byteOffset',0)
    (root/f'v26-embedded-{i}.png').write_bytes(data[start:start+view['byteLength']])
