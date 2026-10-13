import bpy,json,sys
from pathlib import Path
from mathutils import Vector
root=Path('C:/ProjectHub3D/cache/trellis2/output/wind-ronin-'+('1024' if '--1024' in sys.argv else '512'))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(root/'character.glb'))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:obj.select_set(True)
bpy.context.view_layer.objects.active=meshes[0]
if len(meshes)>1:bpy.ops.object.join()
body=bpy.context.object;body.name='WindRonin_Native_HIGH'
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
coords=[v.co.copy() for v in body.data.vertices]
low=Vector([min(v[i] for v in coords) for i in range(3)]);high=Vector([max(v[i] for v in coords) for i in range(3)])
print('NATIVE_BOUNDS',list(low),list(high),flush=True)
scale=1.9/(high.z-low.z);center=(low+high)/2
for v in body.data.vertices:v.co=Vector(((v.co.x-center.x)*scale,(v.co.y-center.y)*scale,(v.co.z-low.z)*scale))
for p in body.data.polygons:p.use_smooth=True
body.data.update()
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
scene.render.resolution_x=768;scene.render.resolution_y=1152;scene.render.resolution_percentage=100;scene.render.film_transparent=True
try:
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    for d in prefs.devices:d.use=d.type!='CPU'
    scene.cycles.device='GPU'
except Exception:pass
world=bpy.data.worlds.new('Studio');scene.world=world;world.color=(.18,.18,.18)
bpy.ops.object.camera_add();scene.camera=bpy.context.object;scene.camera.data.type='ORTHO';scene.camera.data.ortho_scale=2.03
for pos,energy,size in [((-3,-4,5),200,3),((3,-2,3),90,3),((1,3,4),140,2)]:
    bpy.ops.object.light_add(type='AREA',location=pos);light=bpy.context.object;light.data.energy=energy;light.data.shape='DISK';light.data.size=size
    light.rotation_euler=(Vector((0,0,1))-light.location).to_track_quat('-Z','Y').to_euler()
for mode in ['pbr','painted']:
    if mode=='painted':
        for material in body.data.materials:
            nodes,links=material.node_tree.nodes,material.node_tree.links
            bsdf=next(n for n in nodes if n.type=='BSDF_PRINCIPLED');output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
            emission=nodes.new('ShaderNodeEmission')
            if bsdf.inputs['Base Color'].links:links.new(bsdf.inputs['Base Color'].links[0].from_socket,emission.inputs['Color'])
            else:emission.inputs['Color'].default_value=bsdf.inputs['Base Color'].default_value
            links.new(emission.outputs[0],output.inputs['Surface'])
    for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
        scene.camera.location=pos;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath=str(root/(mode+'-'+name+'.png'));bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/(mode+'-source.blend')))
print('NATIVE_PREVIEW_READY',len(body.data.polygons),flush=True)
