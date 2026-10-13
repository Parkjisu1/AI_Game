"""Independent archive/GLB check and fresh Blender roundtrip for a generated pack."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile
import bpy

root=Path(sys.argv[sys.argv.index('--')+1])
report=json.loads((root/'report.json').read_text(encoding='utf8'))
manifest=json.loads((root/'manifest.json').read_text(encoding='utf8'))
with zipfile.ZipFile(root/'model-pack.zip') as archive:
    assert archive.testzip() is None
    for item in manifest['files']:
        data=archive.read(item['path'])
        assert len(data)==item['bytes'],item['path']
        assert hashlib.sha256(data).hexdigest()==item['sha256'],item['path']
checks=[]
for lod in report['lods']:
    data=(root/lod['file']).read_bytes()
    magic,version,size=struct.unpack_from('<4sII',data)
    assert magic==b'glTF' and version==2 and size==len(data)
    length,kind=struct.unpack_from('<II',data,12)
    assert kind==0x4E4F534A
    document=json.loads(data[20:20+length])
    triangles=sum(document['accessors'][p['indices']]['count']//3 for m in document['meshes'] for p in m['primitives'])
    assert triangles==lod['triangles'],(triangles,lod['triangles'])
    assert document.get('skins'),'No exported skin'
    assert all('bufferView' in image for image in document.get('images',[])),'External image dependency'
    if report.get('painted_unlit'):
        assert len(list((root/'textures').glob('*.png')))>=len(document.get('images',[])),'Standalone textures missing'
        assert document.get('materials'),'Missing materials'
        for material in document['materials']:
            assert 'KHR_materials_unlit' in material.get('extensions',{}),material['name']
            assert 'baseColorTexture' in material.get('pbrMetallicRoughness',{}),material['name']
    animations=[a['name'] for a in document.get('animations',[])]
    if report['mode'] in ('demo','image'):
        assert {'Idle','Walk','JointTest'}<=set(animations),animations
        assert len(document.get('images',[]))>=(3 if report['mode']=='demo' else 2)
    checks.append({'file':lod['file'],'triangles':triangles,'skins':len(document['skins']),'animations':animations,'images':len(document.get('images',[]))})
for lod in report['lods']:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(root/lod['file']))
    skinned=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)]
    assert skinned
    for obj in skinned:
        for vertex in obj.data.vertices:
            weights=[g.weight for g in vertex.groups if g.weight>1e-6]
            assert weights and len(weights)<=4 and abs(sum(weights)-1)<.01,(lod['file'],vertex.index,weights)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(root/'character_LOD0.glb'))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)]
rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
assert meshes and rigs
unweighted=0
for obj in meshes:
    assert obj.data.uv_layers
    assert any(m.type=='ARMATURE' and m.object for m in obj.modifiers)
    for v in obj.data.vertices:
        weights=[g.weight for g in v.groups if g.weight>1e-6]
        unweighted+=not weights
        assert abs(sum(weights)-1)<.01
        assert len(weights)<=4
assert unweighted==0
glb_bones=sum(len(o.data.bones) for o in rigs)
# Sample the actually imported animation to prove it changes skin coordinates.
rig=rigs[0]
if any('Walk' in a.name for a in bpy.data.actions):
    action=next(a for a in bpy.data.actions if 'Walk' in a.name)
    rig.animation_data_create();rig.animation_data.action=action
    if action.slots: rig.animation_data.action_slot=action.slots[0]
    for track in rig.animation_data.nla_tracks: track.mute=True
    obj=max(meshes,key=lambda item:len(item.data.vertices))
    bpy.context.scene.frame_set(1)
    mesh=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    first=[v.co.copy() for v in mesh.vertices]
    obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    bpy.context.scene.frame_set(7)
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=evaluated.to_mesh()
    movement=max((v.co-first[i]).length for i,v in enumerate(mesh.vertices))
    evaluated.to_mesh_clear()
    assert movement>.01,('Animation does not deform mesh',movement)
else: movement=None
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(root/'character.fbx'))
assert any(o.type=='ARMATURE' for o in bpy.context.scene.objects)
assert any(o.type=='MESH' for o in bpy.context.scene.objects)
fbx_textured_materials=0
if report.get('painted_unlit'):
    for mat in {m for o in bpy.context.scene.objects if o.type=='MESH' for m in o.data.materials if m}:
        bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        assert bsdf.inputs['Base Color'].is_linked,('FBX lost base color',mat.name)
        texture=bsdf.inputs['Base Color'].links[0].from_node
        assert texture.type=='TEX_IMAGE' and texture.image and texture.image.has_data,mat.name
        fbx_textured_materials+=1
result={'passed':True,'archive_hashes_verified':len(manifest['files']),'glb_files':checks,
        'glb_roundtrip_bones':glb_bones,'animated_vertex_motion_m':movement,'fbx_roundtrip':True,
        'painted_unlit_verified':report.get('painted_unlit',False),'fbx_textured_materials':fbx_textured_materials,
        'engine_verified':False,'art_approved':False}
(root/'roundtrip-check.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print('ROUNDTRIP_PASS '+json.dumps(result))
