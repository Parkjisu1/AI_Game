"""Reference-led revision: preserve painted colors, fit the front silhouette, rebake clean UVs."""
import bpy,numpy as np,sys
from pathlib import Path
from mathutils import Vector
native='--native' in sys.argv
root=Path('C:/ProjectHub3D/cache/style-iteration/'+('v6' if native else 'v4'));root.mkdir(parents=True,exist_ok=True)
source='C:/ProjectHub3D/cache/trellis2/output/wind-ronin-512/pbr-source.blend' if native else 'D:/ProjectHub3D/jobs/6aa118aab4e9da5eb64d438e/output/character.blend'
bpy.ops.wm.open_mainfile(filepath=source,load_ui=False,use_scripts=False)
scene=bpy.context.scene
body=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render)
native_image=None
if native:
    material=body.data.materials[0]
    native_bsdf=next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    native_image=native_bsdf.inputs['Base Color'].links[0].from_node.image
for obj in list(scene.objects):
    if obj.type=='MESH' and obj!=body and 'SourceSculpt' not in obj.name:bpy.data.objects.remove(obj,do_unlink=True)
images={};masks={};bounds={}
for key in ['front','back']:
    img=bpy.data.images.load('D:/ProjectHub3D/jobs/6aa118aab4e9da5eb64d438e/'+key+'.png',check_existing=True)
    img.colorspace_settings.name='sRGB';images[key]=img
    rgb=np.asarray(img.pixels[:],dtype=np.float32).reshape(img.size[1],img.size[0],4)[:,:,:3]
    mask=rgb.min(axis=2)<.65
    yy,xx=np.nonzero(mask);bounds[key]=(xx.min(),xx.max(),yy.min(),yy.max())
    # Pull projected samples two pixels into the source figure to suppress white edge contamination.
    interior=mask.copy()
    for dx,dy in [(-2,0),(2,0),(0,-2),(0,2)]:interior &= np.roll(np.roll(mask,dx,axis=1),dy,axis=0)
    masks[key]=interior
x0,x1,y0,y1=bounds['front'];pixels_per_m=(y1-y0)/1.9
desired_width=(x1-x0)/pixels_per_m
coords=np.asarray([v.co[:] for v in body.data.vertices]);width=coords[:,0].max()-coords[:,0].min()
factor=desired_width/width
front_rows={int(y):np.flatnonzero(masks['front'][y]) for y in np.flatnonzero(masks['front'].any(axis=1))}
rows=np.array(list(front_rows));cx=(x0+x1)/2
clipped=0
for vertex in body.data.vertices:
    vertex.co.x*=factor
    py=int(round(y0+vertex.co.z*pixels_per_m));py=int(rows[np.argmin(abs(rows-py))])
    px=int(round(cx+vertex.co.x*pixels_per_m));columns=front_rows[py]
    if not native and (px<0 or px>=images['front'].size[0] or not masks['front'][py,px]):
        vertex.co.x=(int(columns[np.argmin(abs(columns-px))])-cx)/pixels_per_m;clipped+=1
body.data.update()
rig=next((o for o in scene.objects if o.type=='ARMATURE'),None)
if rig:
    bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    for bone in rig.data.edit_bones:bone.head.x*=factor;bone.tail.x*=factor
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT');body.select_set(True);bpy.context.view_layer.objects.active=body
for key in ['front','back']:
    img=images[key];x0,x1,y0,y1=bounds[key];ppm=(y1-y0)/1.9;cx=(x0+x1)/2
    uv=body.data.uv_layers.get('Projection_'+key) or body.data.uv_layers.new(name='Projection_'+key)
    valid_rows={int(y):np.flatnonzero(masks[key][y]) for y in np.flatnonzero(masks[key].any(axis=1))}
    rows=np.array(list(valid_rows));projected={};confidence=[]
    for vertex in body.data.vertices:
        py=int(round(y0+vertex.co.z*ppm));py=int(rows[np.argmin(abs(rows-py))])
        px=int(round(cx+vertex.co.x*ppm*(1 if key=='front' else -1)))
        confidence.append(float(0<=px<img.size[0] and masks[key][py,px]))
        columns=valid_rows[py];px=int(columns[np.argmin(abs(columns-px))])
        projected[vertex.index]=((px+.5)/img.size[0],(py+.5)/img.size[1])
    for loop in body.data.loops:uv.data[loop.index].uv=projected[loop.vertex_index]
    attr=body.data.attributes.get(key+'_confidence') or body.data.attributes.new(key+'_confidence','FLOAT','POINT')
    attr.data.foreach_set('value',confidence)
material=bpy.data.materials.new('WindRonin_Painted');material.use_nodes=True
body.data.materials.clear();body.data.materials.append(material)
nodes,links=material.node_tree.nodes,material.node_tree.links;nodes.clear()
output=nodes.new('ShaderNodeOutputMaterial');emission=nodes.new('ShaderNodeEmission');links.new(emission.outputs[0],output.inputs['Surface'])
mix=nodes.new('ShaderNodeMixRGB');reference_textures={}
for i,key in enumerate(['front','back']):
    uv=nodes.new('ShaderNodeUVMap');uv.uv_map='Projection_'+key
    tex=nodes.new('ShaderNodeTexImage');tex.image=images[key]
    links.new(uv.outputs[0],tex.inputs['Vector']);links.new(tex.outputs[0],mix.inputs[i+1])
    reference_textures[key]=tex
geometry=nodes.new('ShaderNodeNewGeometry');sep=nodes.new('ShaderNodeSeparateXYZ');ramp=nodes.new('ShaderNodeMapRange')
links.new(geometry.outputs['Position'],sep.inputs[0]);links.new(sep.outputs['Y'],ramp.inputs[0])
ramp.inputs['From Min'].default_value=-.02;ramp.inputs['From Max'].default_value=.02
links.new(ramp.outputs[0],mix.inputs[0]);links.new(mix.outputs[0],emission.inputs['Color'])
if native:
    base_tex=nodes.new('ShaderNodeTexImage');base_tex.image=native_image
    base_uv=nodes.new('ShaderNodeUVMap');base_uv.uv_map='UVMap';links.new(base_uv.outputs[0],base_tex.inputs['Vector'])
    facing=nodes.new('ShaderNodeSeparateXYZ');links.new(geometry.outputs['Normal'],facing.inputs[0])
    current=base_tex.outputs[0]
    for key,sign in [('front',-1),('back',1)]:
        side=nodes.new('ShaderNodeMath');side.operation='MULTIPLY';side.inputs[1].default_value=sign
        links.new(facing.outputs['Y'],side.inputs[0])
        weight=nodes.new('ShaderNodeMapRange');weight.inputs['From Min'].default_value=.15;weight.inputs['From Max'].default_value=.7
        links.new(side.outputs[0],weight.inputs[0])
        attr=nodes.new('ShaderNodeAttribute');attr.attribute_name=key+'_confidence'
        valid=nodes.new('ShaderNodeMath');valid.operation='MULTIPLY';links.new(weight.outputs[0],valid.inputs[0]);links.new(attr.outputs['Fac'],valid.inputs[1])
        blend=nodes.new('ShaderNodeMixRGB');links.new(valid.outputs[0],blend.inputs[0]);links.new(current,blend.inputs[1]);links.new(reference_textures[key].outputs[0],blend.inputs[2])
        current=blend.outputs[0]
    links.new(current,emission.inputs['Color'])
texture=bpy.data.images.new('Painted_BaseColor_4K',4096,4096,alpha=False)
texture.colorspace_settings.name='sRGB'
target=nodes.new('ShaderNodeTexImage');target.image=texture;nodes.active=target
body.data.uv_layers.active=body.data.uv_layers['UVMap'];body.data.uv_layers.active.active_render=True
scene.render.engine='CYCLES';scene.cycles.samples=8;scene.render.bake.use_selected_to_active=False;scene.render.bake.margin=20
try:
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    for device in prefs.devices:device.use=device.type!='CPU'
    scene.cycles.device='GPU'
except Exception:pass
bpy.ops.object.bake(type='EMIT')
texture.filepath_raw=str(root/'Painted_BaseColor_4K.png');texture.file_format='PNG';texture.save();texture.pack()
nodes.clear();output=nodes.new('ShaderNodeOutputMaterial');emission=nodes.new('ShaderNodeEmission')
tex=nodes.new('ShaderNodeTexImage');tex.image=texture
uv=nodes.new('ShaderNodeUVMap');uv.uv_map='UVMap';links.new(uv.outputs[0],tex.inputs['Vector'])
links.new(tex.outputs[0],emission.inputs['Color']);links.new(emission.outputs[0],output.inputs['Surface'])
body['texture_method']='Reference-painted unlit 4K atlas; native generated side colors blended with confidence-masked front/back reference' if native else 'Reference-painted unlit 4K color atlas; position-based two-view projection; reference aspect and silhouette fitting. No noisy high-poly normal.'
body['silhouette_fit_x_factor']=factor;body['silhouette_adjusted_vertices']=clipped
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.cycles.samples=32
scene.camera.data.ortho_scale=2.03;scene.render.resolution_x=768;scene.render.resolution_y=1152
scene.render.resolution_percentage=100;scene.render.film_transparent=True
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
    scene.camera.location=pos;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'character.blend'))
print('RESTYLE_COMPLETE',factor,clipped,flush=True)
