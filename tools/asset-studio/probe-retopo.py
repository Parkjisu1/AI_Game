import bpy,bmesh,json
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v9/retopo-source.blend',load_ui=False,use_scripts=False)
o=next(o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render)
bm=bmesh.new();bm.from_mesh(o.data)
print('BEFORE',len(bm.verts),len(bm.faces),sum(e.is_boundary for e in bm.edges),sum(e.is_wire for e in bm.edges),sum(len(e.link_faces)>2 for e in bm.edges),flush=True)
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00002)
boundary=[e for e in bm.edges if e.is_boundary]
result=bmesh.ops.holes_fill(bm,edges=boundary,sides=32)
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
print('AFTER',len(bm.verts),len(bm.faces),sum(e.is_boundary for e in bm.edges),sum(e.is_wire for e in bm.edges),sum(len(e.link_faces)>2 for e in bm.edges),'filled',len(result['faces']),flush=True)
