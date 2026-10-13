import bpy,bmesh,json
bpy.ops.wm.open_mainfile(filepath='D:/ProjectHub3D/jobs/000000000000000000000003/output/character.blend',load_ui=False,use_scripts=False)
for obj in bpy.context.scene.objects:
    if obj.type!='MESH' or 'WindRonin' not in obj.name:continue
    bm=bmesh.new();bm.from_mesh(obj.data)
    print('BEFORE',obj.name,{n:sum(len(e.link_faces)==n for e in bm.edges) for n in range(5)})
    bmesh.ops.delete(bm,geom=[e for e in bm.edges if not e.link_faces],context='EDGES')
    bmesh.ops.holes_fill(bm,edges=[e for e in bm.edges if e.is_boundary],sides=0)
    print('AFTER',obj.name,sum(not e.is_manifold for e in bm.edges))
    bm.free()
