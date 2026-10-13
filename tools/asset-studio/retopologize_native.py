"""Rebuild a closed connected game mesh and transfer native color as fallback."""
import bpy,bmesh,json,time
from pathlib import Path
root=Path('C:/ProjectHub3D/cache/style-iteration/v9');root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/trellis2/output/wind-ronin-1024/pbr-source.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene
high=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render)
high.name='SourceSculpt_HIGH'
low=high.copy();low.data=high.data.copy();low.name='WindRonin_LOD0';bpy.context.collection.objects.link(low)
bpy.ops.object.select_all(action='DESELECT');low.select_set(True);bpy.context.view_layer.objects.active=low
low.data.remesh_voxel_size=.004;low.data.use_remesh_preserve_volume=False
bpy.ops.object.voxel_remesh()
bm=bmesh.new();bm.from_mesh(low.data)
unseen=set(bm.verts);discard=[];components=[]
while unseen:
    seed=unseen.pop();todo=[seed];part=[seed]
    while todo:
        v=todo.pop()
        for e in v.link_edges:
            other=e.other_vert(v)
            if other in unseen:unseen.remove(other);todo.append(other);part.append(other)
    components.append(len(part))
    if len(part)<5000:discard.extend(part)
bmesh.ops.delete(bm,geom=discard,context='VERTS')
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
print('MANIFOLD_CHECK',sum(not e.is_manifold for e in bm.edges),sum(not v.is_manifold for v in bm.verts),sum(not e.is_contiguous for e in bm.edges),flush=True)
bm.to_mesh(low.data);bm.free();low.data.update();bpy.context.view_layer.update()
print('CLOSED_SURFACE',len(low.data.polygons),'components',sorted(components,reverse=True)[:15],flush=True)
high.hide_render=True;high.hide_set(True)
low.data.use_mirror_x=False
cleanup=low.modifiers.new('Precondition dense voxel surface','DECIMATE');cleanup.ratio=.12
bpy.ops.object.modifier_apply(modifier=cleanup.name)
bm=bmesh.new();bm.from_mesh(low.data)
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.000001)
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
print('PRECONDITIONED',len(bm.faces),sum(not e.is_manifold for e in bm.edges),flush=True)
bm.to_mesh(low.data);bm.free();low.data.update()
start=time.time()
for vertex in low.data.vertices:vertex.co*=1000.
low.data.update()
bpy.ops.object.quadriflow_remesh(use_mesh_symmetry=False,use_preserve_sharp=False,use_preserve_boundary=False,mode='FACES',target_faces=13500,seed=42)
for vertex in low.data.vertices:vertex.co/=1000.
low.data.update()
if len(low.data.polygons)>50000:raise RuntimeError('QuadriFlow did not reduce the mesh; do not publish this candidate')
print('QUADRIFLOW_COMPLETE',len(low.data.polygons),time.time()-start,flush=True)
bm=bmesh.new();bm.from_mesh(low.data)
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00002)
repaired=bmesh.ops.holes_fill(bm,edges=[e for e in bm.edges if e.is_boundary],sides=32)
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
print('REPAIRED_BOUNDARIES',len(repaired['faces']),sum(not e.is_manifold for e in bm.edges),flush=True)
bm.to_mesh(low.data);bm.free();low.data.update()
for poly in low.data.polygons:poly.use_smooth=True
while low.data.uv_layers:low.data.uv_layers.remove(low.data.uv_layers[0])
uv=low.data.uv_layers.new(name='UVMap');uv.active_render=True
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15,island_margin=.004,area_weight=.4)
bpy.ops.object.mode_set(mode='OBJECT')
mat=bpy.data.materials.new('NativeColor_Fallback');mat.use_nodes=True;low.data.materials.clear();low.data.materials.append(mat)
native_bsdf=next(n for n in high.data.materials[0].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
hn=high.data.materials[0].node_tree.nodes;hl=high.data.materials[0].node_tree.links
color_link=native_bsdf.inputs['Base Color'].links[0].from_socket
em=hn.new('ShaderNodeEmission');hl.new(color_link,em.inputs['Color'])
hl.new(em.outputs[0],next(n for n in hn if n.type=='OUTPUT_MATERIAL').inputs['Surface'])
texture=bpy.data.images.new('NativeFallback_4K',4096,4096,alpha=False)
target=mat.node_tree.nodes.new('ShaderNodeTexImage');target.image=texture;mat.node_tree.nodes.active=target
scene.render.engine='CYCLES';scene.cycles.samples=8;scene.render.bake.margin=12
scene.render.bake.use_selected_to_active=True;scene.render.bake.cage_extrusion=.012;scene.render.bake.max_ray_distance=.04
prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
for d in prefs.devices:d.use=d.type!='CPU'
scene.cycles.device='GPU';high.hide_set(False);high.hide_render=False;high.select_set(True)
bpy.context.view_layer.objects.active=low
bpy.ops.object.bake(type='EMIT')
texture.filepath_raw=str(root/'NativeFallback_4K.png');texture.file_format='PNG';texture.save();texture.pack()
bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');mat.node_tree.links.new(target.outputs['Color'],bsdf.inputs['Base Color']);bsdf.inputs['Roughness'].default_value=.85
high.hide_render=True;high.hide_set(True);high.select_set(False)
low.data.calc_loop_triangles();bm=bmesh.new();bm.from_mesh(low.data)
report={'triangles':len(low.data.loop_triangles),'quads':sum(len(p.vertices)==4 for p in low.data.polygons),'vertices':len(low.data.vertices),'non_manifold_edges':sum(not e.is_manifold for e in bm.edges),'removed_small_component_vertices':len(discard),'method':'4 mm volume remesh without surface reprojection, debris removal, QuadriFlow, small boundary repair, fresh unique UV atlas'}
bm.free();(root/'retopology-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(root/'retopo-source.blend'))
print('RETOPO_COMPLETE',report,flush=True)
