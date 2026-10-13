"""Bake projection shader from a source object to a clean one-UV game mesh."""
import bpy
from pathlib import Path
from mathutils import Vector
root=Path('C:/ProjectHub3D/cache/style-iteration/v13');root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v11/projection-debug.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene;high=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render)
high.name='ProjectionSource_HIGH';low=high.copy();low.data=high.data.copy();low.name='WindRonin_LOD0';bpy.context.collection.objects.link(low)
bpy.ops.object.select_all(action='DESELECT');low.select_set(True);bpy.context.view_layer.objects.active=low
for name in [uv.name for uv in low.data.uv_layers]:
    if name!='UVMap':low.data.uv_layers.remove(low.data.uv_layers[name])
low.data.uv_layers.active=low.data.uv_layers['UVMap'];low.data.uv_layers.active.active_render=True
tri=low.modifiers.new('Stable bake triangulation','TRIANGULATE');bpy.ops.object.modifier_apply(modifier=tri.name)
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.pack_islands(rotate=True,margin=.003)
bpy.ops.object.mode_set(mode='OBJECT')
mat=bpy.data.materials.new('WindRonin_Painted_Game');mat.use_nodes=True;low.data.materials.clear();low.data.materials.append(mat)
nodes=mat.node_tree.nodes;links=mat.node_tree.links;nodes.clear()
texture=bpy.data.images.new('WindRonin_BaseColor_4K',4096,4096,alpha=False)
target=nodes.new('ShaderNodeTexImage');target.image=texture;nodes.active=target
scene.render.bake.use_selected_to_active=True;scene.render.bake.use_cage=False
scene.render.bake.cage_extrusion=.002;scene.render.bake.max_ray_distance=.01
high.select_set(True)
bpy.ops.object.bake(type='EMIT',uv_layer='UVMap',margin=8,margin_type='EXTEND',use_clear=True)
texture.filepath_raw=str(root/'Painted_BaseColor_4K.png');texture.file_format='PNG';texture.save();texture.pack()
out=nodes.new('ShaderNodeOutputMaterial');em=nodes.new('ShaderNodeEmission')
links.new(target.outputs[0],em.inputs[0]);links.new(em.outputs[0],out.inputs[0])
high.hide_render=True;high.hide_set(True);high.select_set(False)
scene.render.bake.use_selected_to_active=False
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
    scene.camera.location=pos;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'character.blend'))
