import bpy,bmesh
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/trellis2/output/wind-ronin-512/pbr-source.blend',load_ui=False,use_scripts=False)
body=next(o for o in bpy.context.scene.objects if o.type=='MESH')
bm=bmesh.new();bm.from_mesh(body.data)
print('RAW_TOPOLOGY',len(bm.verts),len(bm.faces),sum(not e.is_manifold for e in bm.edges),flush=True)
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
print('WELDED_TOPOLOGY',len(bm.verts),len(bm.faces),sum(not e.is_manifold for e in bm.edges),flush=True)
bm.free()
