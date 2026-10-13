"""Render real Blender material variants using one unchanged mesh and camera."""
import bpy
from pathlib import Path
from mathutils import Vector
root=Path('C:/ProjectHub3D/cache/style-iteration')
root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='D:/ProjectHub3D/jobs/6aa118aab4e9da5eb64d438e/output/character.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene
scene.render.resolution_x=1024;scene.render.resolution_y=1536;scene.render.resolution_percentage=100
scene.camera.location=(0,-4,.95)
scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
scene.camera.data.ortho_scale=2.03
scene.render.film_transparent=True
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
body=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render)
mat=body.data.materials[0]
nodes,links=mat.node_tree.nodes,mat.node_tree.links
bsdf=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
base=next(n for n in nodes if n.type=='TEX_IMAGE' and 'BaseColor' in n.image.name)
normal=next(n for n in nodes if n.type=='NORMAL_MAP')
for mode in ['pbr','painted','hybrid']:
    if mode=='painted':
        emission=nodes.new('ShaderNodeEmission');emission.inputs['Strength'].default_value=1
        links.new(base.outputs['Color'],emission.inputs['Color']);links.new(emission.outputs[0],output.inputs['Surface'])
    elif mode=='hybrid':
        normal.inputs['Strength'].default_value=.15
        bsdf.inputs['Specular IOR Level'].default_value=0
        bsdf.inputs['Roughness'].default_value=1
        for light in bpy.data.lights:light.energy*=.18
        mix=nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=.7
        links.new(bsdf.outputs[0],mix.inputs[1]);links.new(emission.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface'])
    scene.render.filepath=str(root/(mode+'-front.png'))
    bpy.ops.render.render(write_still=True)
    print('VARIANT',mode,flush=True)
