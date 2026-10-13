"""Remove a triangulation flap in the audited hair cap before LOD reduction."""
import bpy,bmesh,json
from pathlib import Path
root=Path('C:/ProjectHub3D/cache/style-iteration/v22');root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v21/prepared.blend',load_ui=False,use_scripts=False)
for obj in bpy.context.scene.objects:
    if obj.type!='MESH' or obj.hide_render:continue
    bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.triangulate(bm,faces=list(bm.faces))
    removed=0
    bad_edges=[e for e in bm.edges if len(e.link_faces)>2]
    if bad_edges:
        affected=set(v for e in bad_edges for v in e.verts)
        if any(v.co.z<1.8 for v in affected):raise RuntimeError('Unexpected defect outside hair cap')
        bmesh.ops.delete(bm,geom=list(affected),context='VERTS')
        caps=bmesh.ops.holes_fill(bm,edges=[e for e in bm.edges if e.is_boundary],sides=64)['faces']
        uv=bm.loops.layers.uv.active;deform=bm.verts.layers.deform.active
        for face in list(caps):
            verts=list(face.verts);uvs=[loop[uv].uv.copy() for loop in face.loops]
            center=bm.verts.new(face.calc_center_median());average=sum(uvs,uvs[0]*0)/len(uvs)
            if deform:
                weights={}
                for vert in verts:
                    for index,value in vert[deform].items():weights[index]=weights.get(index,0)+value/len(verts)
                for index,value in weights.items():center[deform][index]=value
            bmesh.ops.delete(bm,geom=[face],context='FACES_ONLY')
            for i,vert in enumerate(verts):
                f=bm.faces.new((vert,verts[(i+1)%len(verts)],center))
                f.loops[0][uv].uv=uvs[i];f.loops[1][uv].uv=uvs[(i+1)%len(verts)];f.loops[2][uv].uv=average
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    for _ in range(3):
        flaps=[f for f in bm.faces if sum(e.is_boundary for e in f.edges)>=2 and any(len(e.link_faces)>2 for e in f.edges)]
        if not flaps:break
        if any(v.co.z<1.8 for f in flaps for v in f.verts):raise RuntimeError('Unexpected flap outside hair cap')
        removed+=len(flaps);bmesh.ops.delete(bm,geom=flaps,context='FACES')
    bad=sum(not e.is_manifold for e in bm.edges)
    print('EXPORT_TOPOLOGY',obj.name,'removed',removed,'bad',bad,flush=True)
    if bad:raise RuntimeError('Export topology still has non-manifold edges')
    bm.to_mesh(obj.data);bm.free();obj.data.update()
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.object.vertex_group_limit_total(group_select_mode='BONE_DEFORM',limit=4)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='BONE_DEFORM',lock_active=False)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'prepared.blend'))
