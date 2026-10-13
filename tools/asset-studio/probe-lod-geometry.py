import bpy,bmesh,json
bpy.ops.wm.open_mainfile(filepath='D:/ProjectHub3D/jobs/6aa12c68b4e9da5eb64d439c/output/character.blend',load_ui=False,use_scripts=False)
for o in bpy.context.scene.objects:
    if o.type!='MESH':continue
    bm=bmesh.new();bm.from_mesh(o.data)
    print('MESH',o.name,flush=True)
    for e in bm.edges:
        if not e.is_manifold:print('BAD_EDGE',e.index,len(e.link_faces),[v.co[:] for v in e.verts],[(f.index,f.calc_area(),[v.index for v in f.verts]) for f in e.link_faces],flush=True)
