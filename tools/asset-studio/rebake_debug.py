import bpy
from pathlib import Path
from mathutils import Vector
root=Path('C:/ProjectHub3D/cache/style-iteration/v12');root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v11/projection-debug.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene;body=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render)
bpy.ops.object.select_all(action='DESELECT');body.select_set(True);bpy.context.view_layer.objects.active=body
mat=body.data.materials[0];nodes=mat.node_tree.nodes;links=mat.node_tree.links
target=next(n for n in nodes if n.type=='TEX_IMAGE' and n.image and n.image.name.startswith('WindRonin_Painted_BaseColor'))
texture=target.image;nodes.active=target
scene.render.bake.use_selected_to_active=False;scene.render.bake.use_cage=False
bpy.ops.object.bake(type='EMIT',uv_layer='UVMap',margin=4,margin_type='EXTEND',use_clear=True)
texture.filepath_raw=str(root/'Painted_BaseColor_4K.png');texture.file_format='PNG';texture.save();texture.pack()
nodes.clear();out=nodes.new('ShaderNodeOutputMaterial');em=nodes.new('ShaderNodeEmission');tex=nodes.new('ShaderNodeTexImage');tex.image=texture
uv=nodes.new('ShaderNodeUVMap');uv.uv_map='UVMap';links.new(uv.outputs[0],tex.inputs['Vector']);links.new(tex.outputs[0],em.inputs[0]);links.new(em.outputs[0],out.inputs[0])
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
    scene.camera.location=pos;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'character.blend'))
