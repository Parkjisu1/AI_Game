import bpy
from pathlib import Path
from mathutils import Vector
root=Path('C:/ProjectHub3D/cache/style-iteration')
bpy.ops.wm.open_mainfile(filepath='D:/ProjectHub3D/jobs/6aa118aab4e9da5eb64d438e/output/character.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene
scene.render.resolution_x=768;scene.render.resolution_y=1152;scene.render.resolution_percentage=100
scene.camera.location=(0,-4,.95);scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
scene.camera.data.ortho_scale=2.03
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
body=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render)
mat=bpy.data.materials.new('Projection diagnosis');mat.use_nodes=True;body.data.materials.clear();body.data.materials.append(mat)
nodes,links=mat.node_tree.nodes,mat.node_tree.links;nodes.clear()
out=nodes.new('ShaderNodeOutputMaterial');emission=nodes.new('ShaderNodeEmission');links.new(emission.outputs[0],out.inputs['Surface'])
mix=nodes.new('ShaderNodeMixRGB')
for i,key in enumerate(['front','back']):
    uv=nodes.new('ShaderNodeUVMap');uv.uv_map='Projection_'+key
    tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load('D:/ProjectHub3D/jobs/6aa118aab4e9da5eb64d438e/'+key+'.png')
    links.new(uv.outputs[0],tex.inputs['Vector']);links.new(tex.outputs['Color'],mix.inputs[i+1])
links.new(mix.outputs[0],emission.inputs['Color'])
geometry=nodes.new('ShaderNodeNewGeometry');sep=nodes.new('ShaderNodeSeparateXYZ');ramp=nodes.new('ShaderNodeMapRange')
links.new(sep.outputs['Y'],ramp.inputs[0])
for mode in ['front-only','position-blend','normal-blend']:
    if mode=='front-only':mix.inputs[0].default_value=0
    else:
        links.new(geometry.outputs['Position' if mode=='position-blend' else 'Normal'],sep.inputs[0])
        extent=.025 if mode=='position-blend' else .45
        ramp.inputs['From Min'].default_value=-extent;ramp.inputs['From Max'].default_value=extent
        links.new(ramp.outputs[0],mix.inputs[0])
    scene.render.filepath=str(root/(mode+'.png'));bpy.ops.render.render(write_still=True)
