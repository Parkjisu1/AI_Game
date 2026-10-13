"""Preserve high-resolution finger geometry instead of body-wide coarse remeshing."""
import bpy,bmesh,json,sys
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,'D:/ProjectHub3D/pipeline');import blender_pipeline as kit
root=Path('C:/ProjectHub3D/cache/style-iteration/v25');root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v22/prepared.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene;body=bpy.data.objects['WindRonin_LOD0'];rig=next(o for o in scene.objects if o.type=='ARMATURE')
with bpy.data.libraries.load('C:/ProjectHub3D/cache/trellis2/output/wind-ronin-1024/pbr-source.blend',link=False) as (src,dst):dst.objects=['WindRonin_Native_HIGH']
high=dst.objects[0];bpy.context.collection.objects.link(high);high.name='HandsSource_HIGH'
bm=bmesh.new();bm.from_mesh(high.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
bmesh.ops.delete(bm,geom=[v for v in bm.verts if not (abs(v.co.x)>.34 and .77<v.co.z<1.075)],context='VERTS')
bmesh.ops.holes_fill(bm,edges=[e for e in bm.edges if e.is_boundary],sides=128)
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
bm.to_mesh(high.data);bm.free();high.data.update()
print('NATIVE_HANDS',len(high.data.vertices),len(high.data.polygons),flush=True)
hands=high.copy();hands.data=high.data.copy();hands.name='WindRonin_Hands_LOD0';bpy.context.collection.objects.link(hands);kit.active(hands)
hands.data.calc_loop_triangles();mod=hands.modifiers.new('Finger-preserving reduction','DECIMATE');mod.ratio=min(1,3400/len(hands.data.loop_triangles));bpy.ops.object.modifier_apply(modifier=mod.name)
for p in hands.data.polygons:p.use_smooth=True
while hands.data.uv_layers:hands.data.uv_layers.remove(hands.data.uv_layers[0])
uv=hands.data.uv_layers.new(name='UVMap');uv.active_render=True
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=.5,island_margin=.001)
bpy.ops.uv.select_all(action='SELECT');bpy.ops.uv.average_islands_scale();bpy.ops.uv.pack_islands(rotate=True,margin_method='FRACTION',margin=.002);bpy.ops.object.mode_set(mode='OBJECT')
source_mat=high.data.materials[0];n=source_mat.node_tree.nodes;l=source_mat.node_tree.links
bsdf=next(node for node in n if node.type=='BSDF_PRINCIPLED');color=bsdf.inputs['Base Color'].links[0].from_socket
em=n.new('ShaderNodeEmission');l.new(color,em.inputs[0]);l.new(em.outputs[0],next(node for node in n if node.type=='OUTPUT_MATERIAL').inputs[0])
mat=bpy.data.materials.new('Hands_Painted');mat.use_nodes=True;hands.data.materials.clear();hands.data.materials.append(mat)
nodes=mat.node_tree.nodes;links=mat.node_tree.links;nodes.clear();texture=bpy.data.images.new('Hands_BaseColor_2K',2048,2048,alpha=False)
target=nodes.new('ShaderNodeTexImage');target.image=texture;nodes.active=target
scene.render.bake.use_selected_to_active=True;scene.render.bake.cage_extrusion=.006;scene.render.bake.max_ray_distance=.02;scene.render.bake.use_cage=False
high.select_set(True);bpy.context.view_layer.objects.active=hands
bpy.ops.object.bake(type='EMIT',uv_layer='UVMap',margin=4,margin_type='EXTEND')
texture.filepath_raw=str(root/'Hands_BaseColor_2K.png');texture.file_format='PNG';texture.save();texture.pack()
out=nodes.new('ShaderNodeOutputMaterial');em=nodes.new('ShaderNodeEmission');links.new(target.outputs[0],em.inputs[0]);links.new(em.outputs[0],out.inputs[0])
high.hide_render=True;high.hide_set(True);high.select_set(False)
# Cap the old wrist boundaries; the new hands overlap inside the bracers.
bm=bmesh.new();bm.from_mesh(body.data)
bmesh.ops.delete(bm,geom=[v for v in bm.verts if abs(v.co.x)>.35 and v.co.z<1.045],context='VERTS')
bmesh.ops.holes_fill(bm,edges=[e for e in bm.edges if e.is_boundary],sides=128)
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(body.data);bm.free();body.data.update()
kit.active(rig);bpy.ops.object.mode_set(mode='EDIT')
for sign,side in [(1,'L'),(-1,'R')]:
    b=rig.data.edit_bones.new('thumb.'+side);b.head=(sign*.389,-.075,.985);b.tail=(sign*.368,-.082,.926);b.parent=rig.data.edit_bones['hand.'+side]
bpy.ops.object.mode_set(mode='OBJECT')
hands.parent=rig;modifier=hands.modifiers.new('Armature','ARMATURE');modifier.object=rig
for vertex in hands.data.vertices:
    side='L' if vertex.co.x>0 else 'R'
    candidates=[b for b in rig.data.bones if b.name.endswith('.'+side) and b.name.startswith(('hand','forearm','finger','thumb'))]
    distances=[]
    for bone in candidates:
        a=bone.head_local;delta=bone.tail_local-a;t=max(0,min(1,(vertex.co-a).dot(delta)/max(delta.length_squared,1e-12)))
        distances.append(((vertex.co-a-delta*t).length,bone.name))
    best=sorted(distances)[:4];raw=[1/max(distance,.008)**4 for distance,_ in best];total=sum(raw)
    for (_,name),weight in zip(best,raw):
        group=hands.vertex_groups.get(name) or hands.vertex_groups.new(name=name);group.add([vertex.index],weight/total,'REPLACE')
kit.normalize_skin(hands)
scene.render.bake.use_selected_to_active=False
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
    scene.camera.location=pos;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
report=kit.metrics([o for o in scene.objects if o.type=='MESH' and not o.hide_render],[rig]);print('HANDS_REVISION',report,flush=True)
for obj in [body,hands]:print('PART_METRICS',obj.name,kit.metrics([obj],[rig]),flush=True)
(root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');bpy.ops.wm.save_as_mainfile(filepath=str(root/'prepared.blend'))
