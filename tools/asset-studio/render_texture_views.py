import bpy,json
from pathlib import Path
from mathutils import Vector
root=Path('C:/ProjectHub3D/cache/trellis2/output/wind-ronin-1024')
bpy.ops.wm.open_mainfile(filepath=str(root/'pbr-source.blend'),load_ui=False,use_scripts=False)
scene=bpy.context.scene;scene.render.resolution_x=1024;scene.render.resolution_y=1536;scene.render.resolution_percentage=100
scene.camera.data.ortho_scale=2.03
views={'front':(0,-4,.95),'left':(-4,0,.95),'right':(4,0,.95),'back':(0,4,.95)}
for name,pos in views.items():
    scene.camera.location=pos;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/('guide-source-'+name+'.png'));bpy.ops.render.render(write_still=True)
(root/'guide-cameras.json').write_text(json.dumps({'views':views,'look_at':[0,0,.95],'ortho_scale':2.03,'resolution':[1024,1536]},indent=2))
