"""Bake four camera-aligned painted guides onto the actual TRELLIS mesh.

Guide images are inputs, never substituted for actual rendered validation views.
Visibility, facing and foreground confidence suppress projection contamination.
"""
import bpy, json, numpy as np, sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from bpy_extras.object_utils import world_to_camera_view

source=Path('C:/ProjectHub3D/cache/trellis2/output/wind-ronin-1024')
retopo='--retopo' in sys.argv
clean='--clean' in sys.argv
spatial='--spatial' in sys.argv
root=Path('C:/ProjectHub3D/cache/style-iteration/'+('v11' if spatial else 'v10' if clean else 'v9' if retopo else 'v8'));root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v9/retopo-source.blend' if retopo else str(source/'pbr-source.blend'),load_ui=False,use_scripts=False)
scene=bpy.context.scene
body=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render)
oldmat=body.data.materials[0]
bsdf=next(n for n in oldmat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
native_image=bsdf.inputs['Base Color'].links[0].from_node.image
base_uv_name=body.data.uv_layers.active.name
bpy.ops.object.select_all(action='DESELECT');body.select_set(True);bpy.context.view_layer.objects.active=body
vertices=[v.co.copy() for v in body.data.vertices]
bvh=BVHTree.FromPolygons(vertices,[list(p.vertices) for p in body.data.polygons],all_triangles=False)
material=bpy.data.materials.new('WindRonin_FourView_Painted');material.use_nodes=True
body.data.materials.clear();body.data.materials.append(material)
nodes,links=material.node_tree.nodes,material.node_tree.links;nodes.clear()

def math(op,a,b=None):
    n=nodes.new('ShaderNodeMath');n.operation=op
    for i,val in enumerate([a,b]):
        if val is None:continue
        if isinstance(val,(int,float)):n.inputs[i].default_value=val
        else:links.new(val,n.inputs[i])
    return n.outputs[0]

def vec(op,a,b):
    n=nodes.new('ShaderNodeVectorMath');n.operation=op;links.new(a,n.inputs[0])
    links.new(b,n.inputs[3] if op=='SCALE' else n.inputs[1]);return n.outputs[0]

def bbox(mask):
    yy,xx=np.nonzero(mask);return [int(xx.min()),int(xx.max()),int(yy.min()),int(yy.max())]

report={'method':'Four-view foreground-masked visibility-weighted projection, baked onto native UVs','views':{}}
sum_color=None;sum_weight=None
fallback_colors=np.zeros((len(vertices),3),dtype=np.float64);fallback_weights=np.zeros(len(vertices),dtype=np.float64)
for key,pos in [('front',(0,-4,.95)),('left',(-4,0,.95)),('right',(4,0,.95)),('back',(0,4,.95))]:
    img=bpy.data.images.load('D:/ProjectHub3D/references/texture-guide-'+key+'-v8.png',check_existing=True)
    img.colorspace_settings.name='sRGB'
    rgb=np.asarray(img.pixels[:],dtype=np.float32).reshape(img.size[1],img.size[0],4)[:,:,:3]
    gb=bbox(rgb.min(axis=2)<.85)
    foreground_mask=rgb.min(axis=2)<.80
    if clean:
        interior=foreground_mask.copy()
        for dx,dy in [(-5,0),(5,0),(0,-5),(0,5)]:interior &= np.roll(np.roll(foreground_mask,dx,axis=1),dy,axis=0)
        valid_rows={int(y):np.flatnonzero(interior[y]) for y in np.flatnonzero(interior.any(axis=1))}
        row_ids=np.array(list(valid_rows))
        boundary=interior & (~np.roll(interior,1,0)|~np.roll(interior,-1,0)|~np.roll(interior,1,1)|~np.roll(interior,-1,1))
        by,bx=np.nonzero(boundary);nearest=KDTree(len(bx))
        for idx,(x,y) in enumerate(zip(bx,by)):nearest.insert((float(x),float(y),0.),idx)
        nearest.balance()
    rendered=bpy.data.images.load(str(source/('guide-source-'+key+'.png')),check_existing=True)
    ra=np.asarray(rendered.pixels[:],dtype=np.float32).reshape(rendered.size[1],rendered.size[0],4)
    rb=bbox(ra[:,:,3]>.5)
    scene.camera.location=pos
    scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera.data.ortho_scale=2.03;scene.render.resolution_x=1024;scene.render.resolution_y=1536
    bpy.context.view_layer.update()
    direction=(Vector(pos)-Vector((0,0,.95))).normalized()
    uv=body.data.uv_layers.new(name='Guide_'+key)
    projected=[];weights=[];occluded=0
    for vertex in body.data.vertices:
        p=world_to_camera_view(scene,scene.camera,body.matrix_world@vertex.co)
        px=(p.x*rendered.size[0]-rb[0])/(rb[1]-rb[0])*(gb[1]-gb[0])+gb[0]
        py=(p.y*rendered.size[1]-rb[2])/(rb[3]-rb[2])*(gb[3]-gb[2])+gb[2]
        if clean:
            iy=int(round(py));iy=int(row_ids[np.argmin(abs(row_ids-iy))])
            cols=valid_rows[iy];ix=int(round(px))
            if ix<0 or ix>=img.size[0] or not interior[iy,ix]:
                point,idx,distance=nearest.find((float(px),float(py),0.));px=float(point.x);py=float(point.y)
        projected.append(((px+.5)/img.size[0],(py+.5)/img.size[1]))
        facing=max(0.,vertex.normal.dot(direction))
        hit=bvh.ray_cast(vertex.co+direction*.0015,direction,4.) if facing>.08 else (None,None,None,None)
        visible=hit[0] is None or clean
        if not visible:occluded+=1
        # Side guides contain an overlapping hand in this height band. Use the
        # unobstructed front/back views for the tunic/thighs to avoid a ghost hand.
        if key in ('left','right') and .76<vertex.co.z<1.15 and abs(vertex.co.x)<.30:visible=False
        weight=facing**(4 if clean else 8) if visible else 0.
        if spatial:
            t=float(np.clip((vertex.co.y+.055)/.11,0,1));t=t*t*(3-2*t)
            weight=1-t if key=='front' else t if key=='back' else 0.
            # Head side views provide ear/profile detail only on the visible side.
            if vertex.co.z>1.63 and abs(vertex.co.x)>.07:
                weight=(facing**4 if hit[0] is None else 0.)
        weights.append(weight)
        ix=int(np.clip(round(px),0,img.size[0]-1));iy=int(np.clip(round(py),0,img.size[1]-1))
        sample=rgb[iy,ix];linear=np.where(sample<=.04045,sample/12.92,((sample+.055)/1.055)**2.4)
        fallback_colors[vertex.index]+=linear*weight;fallback_weights[vertex.index]+=weight
    for loop in body.data.loops:uv.data[loop.index].uv=projected[loop.vertex_index]
    attr=body.data.attributes.new(key+'_weight','FLOAT','POINT');attr.data.foreach_set('value',weights)
    uvnode=nodes.new('ShaderNodeUVMap');uvnode.uv_map=uv.name
    tex=nodes.new('ShaderNodeTexImage');tex.image=img;tex.extension='CLIP';links.new(uvnode.outputs[0],tex.inputs['Vector'])
    color=nodes.new('ShaderNodeSeparateColor');links.new(tex.outputs['Color'],color.inputs[0])
    darkest=math('MINIMUM',math('MINIMUM',color.outputs[0],color.outputs[1]),color.outputs[2])
    foreground=math('LESS_THAN',darkest,.85)
    attribute=nodes.new('ShaderNodeAttribute');attribute.attribute_name=attr.name
    weight=math('MULTIPLY',attribute.outputs['Fac'],foreground)
    weighted=vec('SCALE',tex.outputs['Color'],weight)
    sum_color=weighted if sum_color is None else vec('ADD',sum_color,weighted)
    sum_weight=weight if sum_weight is None else math('ADD',sum_weight,weight)
    report['views'][key]={'guide_bbox':gb,'render_bbox':rb,'occluded_vertices':occluded,'positive_vertices':sum(w>0 for w in weights)}
    print('GUIDE_READY',key,report['views'][key],flush=True)

base=nodes.new('ShaderNodeTexImage');base.image=native_image
nativeuv=nodes.new('ShaderNodeUVMap');nativeuv.uv_map=base_uv_name;links.new(nativeuv.outputs[0],base.inputs['Vector'])
fallback_color=base.outputs['Color']
if spatial:
    fallback_colors/=np.maximum(fallback_weights[:,None],1e-8)
    missing=fallback_weights<1e-8;fallback_colors[missing]=(.03,.025,.02)
    attr=body.data.color_attributes.new(name='GuideFallbackColor',type='FLOAT_COLOR',domain='POINT')
    rgba=np.column_stack([fallback_colors,np.ones(len(vertices))]).astype(np.float32);attr.data.foreach_set('color',rgba.ravel())
    n=nodes.new('ShaderNodeAttribute');n.attribute_name=attr.name;fallback_color=n.outputs['Color']
fallback=math('MAXIMUM',math('SUBTRACT',.001 if spatial else .000001 if clean else .005,sum_weight),0.)
sum_color=vec('ADD',sum_color,vec('SCALE',fallback_color,fallback))
denominator=math('ADD',sum_weight,fallback)
final_color=vec('SCALE',sum_color,math('DIVIDE',1.,denominator))
output=nodes.new('ShaderNodeOutputMaterial');emission=nodes.new('ShaderNodeEmission')
links.new(final_color,emission.inputs['Color']);links.new(emission.outputs[0],output.inputs['Surface'])
texture=bpy.data.images.new('WindRonin_Painted_BaseColor_4K',4096,4096,alpha=False)
texture.colorspace_settings.name='sRGB'
target=nodes.new('ShaderNodeTexImage');target.image=texture;nodes.active=target
body.data.uv_layers.active=body.data.uv_layers[base_uv_name];body.data.uv_layers.active.active_render=True
scene.render.engine='CYCLES';scene.cycles.samples=8;scene.render.bake.use_selected_to_active=False;scene.render.bake.margin=16
prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
for device in prefs.devices:device.use=device.type!='CPU'
scene.cycles.device='GPU'
if '--debug-projection' in sys.argv:
    scene.camera.location=(0,-4,.95);scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.resolution_x=1024;scene.render.resolution_y=1536;scene.cycles.samples=16
    scene.render.filepath=str(root/'before-bake.png');bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'projection-debug.blend'))
    raise SystemExit(0)
bpy.ops.object.bake(type='EMIT')
texture.filepath_raw=str(root/'Painted_BaseColor_4K.png');texture.file_format='PNG';texture.save();texture.pack()
nodes.clear();output=nodes.new('ShaderNodeOutputMaterial');emission=nodes.new('ShaderNodeEmission')
tex=nodes.new('ShaderNodeTexImage');tex.image=texture
uv=nodes.new('ShaderNodeUVMap');uv.uv_map=base_uv_name;links.new(uv.outputs[0],tex.inputs['Vector'])
links.new(tex.outputs[0],emission.inputs['Color']);links.new(emission.outputs[0],output.inputs['Surface'])
body['texture_method']=report['method']
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.cycles.samples=32
scene.camera.data.ortho_scale=2.03;scene.render.resolution_x=1024;scene.render.resolution_y=1536
scene.render.resolution_percentage=100;scene.render.film_transparent=True
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95)),('left',(-4,0,.95))]:
    scene.camera.location=pos;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'character.blend'))
(root/'texture-bake-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('FOUR_VIEW_BAKE_COMPLETE',flush=True)
