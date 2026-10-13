"""Turn a generated humanoid shape into a textured, rigged review candidate in Blender.

Automatic shape reduction/weights and two-view projection are drafts, not final art approval.
"""
import json
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8-sig'))
out=Path(job['output']);out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=job['source'])
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes: obj.select_set(True)
bpy.context.view_layer.objects.active=meshes[0]
bpy.ops.object.join()
body=bpy.context.object
body.name='WindRonin_AI_LOD0'
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
coords=np.array([v.co[:] for v in body.data.vertices])
low,high=coords.min(axis=0),coords.max(axis=0)
scale=1.9/(high[2]-low[2])
center=(low+high)/2
for v in body.data.vertices:
    v.co=Vector(((v.co.x-center[0])*scale,(v.co.y-center[1])*scale,(v.co.z-low[2])*scale))
body.data.update()
sculpt=body.copy();sculpt.data=body.data.copy();sculpt.name='SourceSculpt_HIGH'
bpy.context.collection.objects.link(sculpt)
sculpt.hide_render=True;sculpt.hide_set(True)
# Reconstruct a closed surface before reduction. The untouched input remains in the blend.
body.data.remesh_voxel_size=.006
body.data.use_remesh_preserve_volume=True
bpy.ops.object.voxel_remesh()
smooth=body.modifiers.new('Surface cleanup','SMOOTH');smooth.factor=.35;smooth.iterations=2
bpy.ops.object.modifier_apply(modifier=smooth.name)
body.data.calc_loop_triangles()
mod=body.modifiers.new('Game mesh candidate','DECIMATE')
target=11000 if job.get('profile')=='mobile' else 28000
mod.ratio=min(1,target/len(body.data.loop_triangles))
bpy.ops.object.modifier_apply(modifier=mod.name)
body.data.validate(clean_customdata=False)
for poly in body.data.polygons: poly.use_smooth=True
coords=np.array([v.co[:] for v in body.data.vertices]);lo,hi=coords.min(axis=0),coords.max(axis=0)

images={}
for key in ['front','back']:
    img=bpy.data.images.load(job[key],check_existing=True)
    img.colorspace_settings.name='sRGB'
    images[key]=img
    pixels=np.array(img.pixels[:],dtype=np.float32).reshape(img.size[1],img.size[0],4)
    mask=np.min(pixels[:,:,:3],axis=2)<.65
    yy,xx=np.nonzero(mask)
    if not len(xx):raise ValueError('Reference needs a visible full-body figure on a white background')
    x0,x1=xx.min()/img.size[0],xx.max()/img.size[0]
    y0,y1=yy.min()/img.size[1],yy.max()/img.size[1]
    uv=body.data.uv_layers.new(name='Projection_'+key)
    # Project UV coordinates onto the existing foreground; never repaint the reference bitmap.
    columns={int(row):np.flatnonzero(mask[row]) for row in np.unique(yy)}
    rows=np.array(list(columns))
    projected={}
    for v in body.data.vertices:
        u=(v.co.x-lo[0])/(hi[0]-lo[0]);z=(v.co.z-lo[2])/(hi[2]-lo[2])
        py=int(round((y0+z*(y1-y0))*(img.size[1]-1)))
        py=int(rows[np.argmin(abs(rows-py))])
        px=int(round((x0+(u if key=='front' else 1-u)*(x1-x0))*(img.size[0]-1)))
        candidates=columns[py]
        if px<0 or px>=img.size[0] or not mask[py,px]:
            px=int(candidates[np.argmin(abs(candidates-px))])
        projected[v.index]=((px+.5)/img.size[0],(py+.5)/img.size[1])
    for loop in body.data.loops:
        uv.data[loop.index].uv=projected[loop.vertex_index]

uv=body.data.uv_layers.new(name='UVMap')
body.data.uv_layers.active=uv
uv.active_render=True
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15,island_margin=.008,area_weight=.5)
bpy.ops.object.mode_set(mode='OBJECT')
material=bpy.data.materials.new('WindRonin_Baked')
material.use_nodes=True
body.data.materials.clear();body.data.materials.append(material)
nodes=material.node_tree.nodes;links=material.node_tree.links
nodes.clear()
output=nodes.new('ShaderNodeOutputMaterial');emission=nodes.new('ShaderNodeEmission')
links.new(emission.outputs[0],output.inputs['Surface'])
mix=nodes.new('ShaderNodeMixRGB')
for i,key in enumerate(['front','back']):
    uvnode=nodes.new('ShaderNodeUVMap');uvnode.uv_map='Projection_'+key
    tex=nodes.new('ShaderNodeTexImage');tex.image=images[key];tex.extension='EXTEND'
    links.new(uvnode.outputs[0],tex.inputs['Vector']);links.new(tex.outputs['Color'],mix.inputs[i+1])
geometry=nodes.new('ShaderNodeNewGeometry');separate=nodes.new('ShaderNodeSeparateXYZ');ramp=nodes.new('ShaderNodeMapRange')
ramp.inputs['From Min'].default_value=-.45;ramp.inputs['From Max'].default_value=.45
links.new(geometry.outputs['Normal'],separate.inputs[0]);links.new(separate.outputs['Y'],ramp.inputs['Value'])
links.new(ramp.outputs['Result'],mix.inputs[0]);links.new(mix.outputs['Color'],emission.inputs['Color'])

scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16
try:
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    for device in prefs.devices: device.use=device.type!='CPU'
    scene.cycles.device='GPU'
except Exception:pass
scene.render.bake.margin=16
maps={}
for name,kind in [('BaseColor','EMIT'),('Normal','NORMAL')]:
    image=bpy.data.images.new(name,2048,2048,alpha=False)
    image.colorspace_settings.name='sRGB' if name=='BaseColor' else 'Non-Color'
    target=nodes.new('ShaderNodeTexImage');target.image=image;nodes.active=target
    bpy.ops.object.select_all(action='DESELECT');body.select_set(True);bpy.context.view_layer.objects.active=body
    scene.render.bake.use_selected_to_active=kind=='NORMAL'
    scene.render.bake.cage_extrusion=.025;scene.render.bake.max_ray_distance=.08
    if kind=='NORMAL':
        sculpt.hide_set(False);sculpt.hide_render=False;sculpt.select_set(True)
    bpy.ops.object.bake(type=kind)
    sculpt.hide_render=True;sculpt.hide_set(True)
    image.filepath_raw=str(out/(name+'.png'));image.file_format='PNG';image.save();image.pack();maps[name]=image
nodes.clear()
output=nodes.new('ShaderNodeOutputMaterial');bsdf=nodes.new('ShaderNodeBsdfPrincipled')
links.new(bsdf.outputs[0],output.inputs['Surface']);bsdf.inputs['Roughness'].default_value=.72
uvnode=nodes.new('ShaderNodeUVMap');uvnode.uv_map='UVMap'
for name in maps:
    tex=nodes.new('ShaderNodeTexImage');tex.image=maps[name];links.new(uvnode.outputs[0],tex.inputs['Vector'])
    if name=='BaseColor':links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
    else:
        normal=nodes.new('ShaderNodeNormalMap');normal.uv_map='UVMap'
        links.new(tex.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs[0],bsdf.inputs['Normal'])

with bpy.data.libraries.load(job['rig_template'],link=False) as (source,dest):
    dest.objects=['WindRonin_Rig']
rig=dest.objects[0];bpy.context.collection.objects.link(rig)
rig.name='WindRonin_AI_Rig'
rig.animation_data.action=None
for track in rig.animation_data.nla_tracks:track.mute=True
for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig
bpy.ops.object.mode_set(mode='EDIT')
xfactor=float((hi[0]-lo[0])/1.12)
for bone in rig.data.edit_bones:
    bone.head.x*=xfactor;bone.tail.x*=xfactor
    bone.head.z*=1.9/1.94;bone.tail.z*=1.9/1.94
bpy.ops.object.mode_set(mode='OBJECT')
body.select_set(True)
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
bpy.context.view_layer.objects.active=body
fallback=0
deform=[b for b in rig.data.bones if b.use_deform and b.name not in ('root','hair','scarf','weapon')]
for v in body.data.vertices:
    if sum(g.weight for g in v.groups)>.001:continue
    fallback+=1
    distances=[]
    p=body.matrix_world@v.co
    for b in deform:
        a=rig.matrix_world@b.head_local;c=rig.matrix_world@b.tail_local
        delta=c-a
        t=max(0,min(1,(p-a).dot(delta)/max(delta.length_squared,1e-12)))
        distances.append(((p-(a+delta*t)).length,b.name))
    best=sorted(distances)[:4]
    raw=[1/max(d,.012)**4 for d,_ in best];total=sum(raw)
    for (_,name),value in zip(best,raw):
        group=body.vertex_groups.get(name) or body.vertex_groups.new(name=name)
        group.add([v.index],value/total,'REPLACE')
bpy.ops.object.vertex_group_limit_total(limit=4)
bpy.ops.object.vertex_group_normalize_all(lock_active=False)
scene.frame_set(1)
scene.unit_settings.system='METRIC';scene.render.fps=30
for img in images.values():img.pack()
body['production_status']='REVIEW_CANDIDATE'
body['texture_method']='Two-view image projection baked into unique 2K UV; high-poly tangent normal bake'
rig['rig_method']=f'Fitted FK template; automatic heat weights with distance fallback for {fallback} vertices. Deformation review required.'
bpy.ops.wm.save_as_mainfile(filepath=str(out/'prepared.blend'))
print('PREPARED',str(out/'prepared.blend'),flush=True)
