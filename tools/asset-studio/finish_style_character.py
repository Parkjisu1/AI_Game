"""Fit the cleaned painted character rig and author modular scarf/katana details."""
import bpy,bmesh,math,json,sys,numpy as np
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,'D:/ProjectHub3D/pipeline');import blender_pipeline as kit
root=Path('C:/ProjectHub3D/cache/style-iteration/v21');root.mkdir(parents=True,exist_ok=True);(root/'textures').mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v19/character.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene;body=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render)
bm=bmesh.new();bm.from_mesh(body.data)
bad=[e for e in bm.edges if len(e.link_faces)>2]
if bad:
    if any(v.co.z<1.8 for e in bad for v in e.verts):raise RuntimeError('Unexpected non-manifold region outside audited hair cap')
    affected=set(e.verts[0] for e in bad);bmesh.ops.delete(bm,geom=list(affected),context='VERTS')
    bmesh.ops.holes_fill(bm,edges=[e for e in bm.edges if e.is_boundary],sides=32)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
print('HAIR_CAP_REPAIR',sum(not e.is_manifold for e in bm.edges),flush=True)
bm.to_mesh(body.data);bm.free();body.data.update()
for obj in list(scene.objects):
    if obj.type=='MESH' and obj!=body:bpy.data.objects.remove(obj,do_unlink=True)
with bpy.data.libraries.load('D:/ProjectHub3D/pipeline/rig-template.blend',link=False) as (src,dst):dst.objects=['WindRonin_Rig']
rig=dst.objects[0];bpy.context.collection.objects.link(rig);rig.animation_data.action=None
for track in rig.animation_data.nla_tracks:track.mute=True
for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
kit.active(rig);bpy.ops.object.mode_set(mode='EDIT')
for b in rig.data.edit_bones:
    b.head.y-=.025;b.tail.y-=.025
    if any(k in b.name for k in ['arm.','hand.','finger']):
        b.head.x*=.81;b.tail.x*=.81
        if b.name.startswith('finger'):b.head.z-=.035;b.tail.z-=.035
    if any(k in b.name for k in ['thigh.','shin.','foot.']):b.head.x*=1.4;b.tail.x*=1.4
rig.data.edit_bones['weapon'].head=(.23,.015,1.09);rig.data.edit_bones['weapon'].tail=(.41,.06,.42)
rig.data.edit_bones['hair'].head=(0,.12,1.83);rig.data.edit_bones['hair'].tail=(.02,.26,1.46)
rig.data.edit_bones['scarf'].head=(-.16,.08,1.54);rig.data.edit_bones['scarf'].tail=(-.34,.22,1.20)
tip=rig.data.edit_bones.new('scarf_tip');tip.head=(-.34,.22,1.20);tip.tail=(-.48,.29,.88);tip.parent=rig.data.edit_bones['scarf']
bpy.ops.object.mode_set(mode='OBJECT')
kit.active(body);rig.select_set(True);bpy.context.view_layer.objects.active=rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
deform=[b for b in rig.data.bones if b.use_deform and b.name not in ('root','hair','scarf','scarf_tip','weapon')]
fallback=0
for v in body.data.vertices:
    if sum(g.weight for g in v.groups)>.001:continue
    fallback+=1;distances=[];p=body.matrix_world@v.co
    for b in deform:
        a=rig.matrix_world@b.head_local;c=rig.matrix_world@b.tail_local;delta=c-a
        t=max(0,min(1,(p-a).dot(delta)/max(delta.length_squared,1e-12)))
        distances.append(((p-a-delta*t).length,b.name))
    best=sorted(distances)[:4];raw=[1/max(d,.012)**4 for d,_ in best];total=sum(raw)
    for (_,name),value in zip(best,raw):
        group=body.vertex_groups.get(name) or body.vertex_groups.new(name=name);group.add([v.index],value/total,'REPLACE')
# Rigid accessories must not pull the body during FK motion.
for name,destination in [('weapon','hips'),('scarf','chest'),('scarf_tip','chest'),('hair','head')]:
    group=body.vertex_groups.get(name)
    if group:
        target=body.vertex_groups.get(destination) or body.vertex_groups.new(name=destination)
        for vertex in body.data.vertices:
            value=next((g.weight for g in vertex.groups if g.group==group.index),0.)
            if value:target.add([vertex.index],value,'ADD')
        body.vertex_groups.remove(group)
kit.normalize_skin(body)
body['texture_method']='Reference-guided painted 4K atlas, explicit UV bake after overlap repair; unlit style'
rig['rig_method']=f'32-bone fitted FK humanoid, automatic heat skinning with distance fallback for {fallback} vertices; cloth and weapon attachment bones'
kit.atlas(root,[(.65,.40,.25),(.30,.40,.41),(.075,.082,.10),(.38,.16,.115),(.7,.64,.51),(.23,.15,.105),(.6,.65,.69),(.55,.40,.22)])
nodes=kit.MAT.node_tree.nodes;links=kit.MAT.node_tree.links
base=next(n for n in nodes if n.type=='TEX_IMAGE' and n.image.name.endswith('_BaseColor'))
base.image=bpy.data.images.load('D:/ProjectHub3D/references/accessory-atlas-v21.png',check_existing=True)
output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL');em=nodes.new('ShaderNodeEmission');links.new(base.outputs[0],em.inputs[0]);links.new(em.outputs[0],output.inputs[0])
# Model an articulated flowing cloth strip behind the bare shoulder.
points=[];widths=[]
for i in range(25):
    t=i/24;points.append((-.16-.31*t,.08+.21*t+.045*math.sin(t*math.pi*2),1.54-.67*t))
    widths.append(.095*(1-.6*t)+.012*math.sin(t*math.pi))
cloth=kit.ribbon('ScarfTail_LOD0',points,widths,1,'scarf')
for v in cloth.data.vertices:
    t=max(0,min(1,(1.26-v.co.z)/.25))
    cloth.vertex_groups['scarf'].add([v.index],1-t,'REPLACE')
    group=cloth.vertex_groups.get('scarf_tip') or cloth.vertex_groups.new(name='scarf_tip');group.add([v.index],t,'REPLACE')
for k in range(6):
    x=(k-2.5)*.012
    kit.tube('PonytailLock'+str(k),[(x,.12,1.81),(x,.21,1.72),(x+.01,.27,1.58),(x+.035,.28,1.44+abs(k-2)*.012)], [.017,.027,.020,.0015],2,'hair',10)
kit.tube('KatanaSheath',[(.23,.015,1.09),(.27,.025,.92),(.35,.045,.66),(.41,.06,.42)],[(.026,.019),(.026,.019),(.023,.017),(.016,.014)],2,'weapon',12)
kit.tube('SheathTip',[(.403,.058,.446),(.414,.06,.408)],[(.019,.017),(.017,.015)],7,'weapon',12)
kit.tube('KatanaHandle',[(.228,.015,1.10),(.168,.001,1.32)],[(.018,.014),(.017,.014)],2,'weapon',12)
kit.ellipsoid('KatanaGuard',(.23,.015,1.091),(.056,.038,.010),7,'weapon',24,8)
for k in range(8):
    t=k/8;x=.222-.054*t;z=1.125+.19*t
    kit.tube('HandleBinding'+str(k),[(x,.013-.012*t,z),(x-.002,.012-.012*t,z+.010)],[(.020,.017)]*2,5,'weapon',8)
kit.tube('HandleCap',[(.173,.002,1.31),(.166,0,1.335)],[(.020,.017)]*2,7,'weapon',12)
for obj in kit.PARTS:
    obj.parent=rig;mod=obj.modifiers.new('Armature','ARMATURE');mod.object=rig
# Consolidate accessories into one draw object while preserving skin groups.
bpy.ops.object.select_all(action='DESELECT')
for obj in kit.PARTS:obj.select_set(True)
bpy.context.view_layer.objects.active=cloth;bpy.ops.object.join();props=bpy.context.object;props.name='WindRonin_Accessories_LOD0'
kit.normalize_skin(props)
for obj in [body,props]:
    bm=bmesh.new();bm.from_mesh(obj.data);loose=[e for e in bm.edges if e.is_wire]
    if loose:bmesh.ops.delete(bm,geom=loose,context='EDGES')
    bm.to_mesh(obj.data);bm.free();obj.data.update()
# Bake restrained form shading into the accessory atlas, matching painted body shading.
kit.active(props)
props.data.uv_layers.active.name='SurfaceUV'
uvnode=nodes.new('ShaderNodeUVMap');uvnode.uv_map='SurfaceUV';links.new(uvnode.outputs[0],base.inputs['Vector'])
geometry=nodes.new('ShaderNodeNewGeometry');dot=nodes.new('ShaderNodeVectorMath');dot.operation='DOT_PRODUCT';dot.inputs[1].default_value=(-.35,-.6,.72);links.new(geometry.outputs['Normal'],dot.inputs[0])
shade=nodes.new('ShaderNodeMapRange');shade.inputs['From Min'].default_value=-1;shade.inputs['From Max'].default_value=1;shade.inputs['To Min'].default_value=.45;shade.inputs['To Max'].default_value=1.2;links.new(dot.outputs['Value'],shade.inputs[0])
scale=nodes.new('ShaderNodeVectorMath');scale.operation='SCALE';links.new(base.outputs[0],scale.inputs[0]);links.new(shade.outputs[0],scale.inputs[3]);links.new(scale.outputs[0],em.inputs[0])
uv=props.data.uv_layers.new(name='UVMap');props.data.uv_layers.active=uv;uv.active_render=True
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=.5,island_margin=.002)
bpy.ops.uv.select_all(action='SELECT');bpy.ops.uv.average_islands_scale();bpy.ops.uv.pack_islands(rotate=True,margin_method='FRACTION',margin=.002);bpy.ops.object.mode_set(mode='OBJECT')
texture=bpy.data.images.new('Accessories_Painted_2K',2048,2048,alpha=False);target=nodes.new('ShaderNodeTexImage');target.image=texture;nodes.active=target
scene.render.bake.use_selected_to_active=False;scene.render.bake.use_cage=False
bpy.ops.object.bake(type='EMIT',uv_layer='UVMap',margin=4,margin_type='EXTEND')
texture.filepath_raw=str(root/'textures'/'Accessories_Painted_2K.png');texture.file_format='PNG';texture.save();texture.pack()
nodes.clear();out=nodes.new('ShaderNodeOutputMaterial');em=nodes.new('ShaderNodeEmission');tex=nodes.new('ShaderNodeTexImage');tex.image=texture;uvnode=nodes.new('ShaderNodeUVMap');uvnode.uv_map='UVMap';links.new(uvnode.outputs[0],tex.inputs[0]);links.new(tex.outputs[0],em.inputs[0]);links.new(em.outputs[0],out.inputs[0])
props.data.uv_layers.remove(props.data.uv_layers['SurfaceUV'])
bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)
for img in bpy.data.images:
    if img.has_data and img.source=='FILE':img.pack()
for img in list(bpy.data.images):
    if img.users==0:bpy.data.images.remove(img)
scene.frame_set(1);scene.render.resolution_x=1024;scene.render.resolution_y=1536;scene.cycles.samples=32
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
    scene.camera.location=pos;scene.camera.data.ortho_scale=2.12;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
for action_name,frame in [('Walk',7),('JointTest',13)]:
    action=bpy.data.actions.get(action_name);rig.animation_data.action=action;scene.frame_set(frame)
    scene.camera.location=(2,-4,1.15);scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(action_name+'.png'));bpy.ops.render.render(write_still=True)
rig.animation_data.action=None
for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
scene.frame_set(1)
report=kit.metrics([body,props],[rig]);report['heat_fallback_vertices']=fallback
(root/'rig-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(root/'prepared.blend'))
print('CHARACTER_FINISHED',report,flush=True)
