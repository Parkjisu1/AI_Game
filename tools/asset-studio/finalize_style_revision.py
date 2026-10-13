"""Combine the clean v23 atlas with the closed v22 rig and portable unlit materials."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,'D:/ProjectHub3D/pipeline');import blender_pipeline as kit
mip_safe='--mip' in sys.argv
root=Path('C:/ProjectHub3D/cache/style-iteration/'+('v28' if mip_safe else 'v26'));root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v22/prepared.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene;body=bpy.data.objects['WindRonin_LOD0'];rig=next(o for o in scene.objects if o.type=='ARMATURE')
clean=bpy.data.images.load('C:/ProjectHub3D/cache/style-iteration/'+('v27' if mip_safe else 'v23')+'/Painted_BaseColor_4K.png',check_existing=False)
clean.name='WindRonin_Painted_BaseColor_4K';clean.pack()
for obj in [o for o in scene.objects if o.type=='MESH' and not o.hide_render]:
    for mat in obj.data.materials:
        nodes,links=mat.node_tree.nodes,mat.node_tree.links
        tex=next(n for n in nodes if n.type=='TEX_IMAGE' and n.image)
        if obj==body:tex.image=clean
        # Blender's official glTF exporter detects an RGBA output as KHR_materials_unlit.
        output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
        links.new(tex.outputs['Color'],output.inputs['Surface'])
        mat['projecthub_painted_unlit']=True
body['texture_method']='Four-view painted projection, 4K unique UV atlas; per-texel foreground correction; 2K painted accessory atlas; glTF unlit'
rig['rig_method']='32-bone FK humanoid; normalized <=4 skin influences; Idle/Walk/JointTest; separate scarf and weapon bones'
for img in list(bpy.data.images):
    if not img.users:bpy.data.images.remove(img)
scene.render.resolution_x=1024;scene.render.resolution_y=1536;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=True
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.cycles.samples=32
rig.animation_data.action=None
for track in rig.animation_data.nla_tracks:track.mute=True
for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
scene.frame_set(1)
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
    scene.camera.location=pos;scene.camera.data.ortho_scale=2.12
    scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
for name,frame in [('Walk',7),('JointTest',13)]:
    rig.animation_data.action=bpy.data.actions[name];scene.frame_set(frame)
    scene.camera.location=(2,-4,1.15);scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
rig.animation_data.action=None
for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
scene.frame_set(1)
(root/'revision.json').write_text(json.dumps({'revision':'v26','body_geometry':'v22 closed triangulated retopology','body_texture':'v23 foreground-corrected 4K','hands_experiment':'v24/v25 rejected: topology and texture regressions','unlit_export':'RGBA output; FBX gets temporary Principled base-color variants'},indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(root/'prepared.blend'))
