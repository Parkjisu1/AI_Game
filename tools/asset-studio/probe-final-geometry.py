import bpy,bmesh,json
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v20/prepared.blend',load_ui=False,use_scripts=False)
for o in bpy.context.scene.objects:
    if o.type!='MESH' or o.hide_render:continue
    bm=bmesh.new();bm.from_mesh(o.data)
    print('MESH',o.name,flush=True)
    for e in bm.edges:
        if not e.is_manifold:print('BAD_EDGE',e.index,len(e.link_faces),[v.co[:] for v in e.verts],[(f.index,f.calc_area(),[v.index for v in f.verts]) for f in e.link_faces],flush=True)
