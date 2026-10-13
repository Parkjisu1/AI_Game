import bpy,json,struct
from pathlib import Path
p=Path('D:/ProjectHub3D/jobs/00000000000001a08526dee4/output/character_LOD0.glb')
data=p.read_bytes();n=struct.unpack_from('<I',data,12)[0];g=json.loads(data[20:20+n])
print('SKIN_NODES',[(n.get('name'),n.get('mesh'),n.get('skin')) for n in g['nodes'] if 'mesh' in n])
print('PRIMITIVES',[(m.get('name'),[p['attributes'] for p in m['primitives']]) for m in g['meshes']])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(p))
for o in bpy.context.scene.objects:
    print('OBJECT',o.name,o.type,'PARENT',o.parent.name if o.parent else None,'GROUPS',len(o.vertex_groups),'MODIFIERS',[(m.name,m.type,getattr(m,'object',None)) for m in o.modifiers])
