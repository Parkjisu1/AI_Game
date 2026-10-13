"""Explicit UV-space barycentric bake of the Blender projection data.

Reads geometry, guide UVs and weights; does not edit the reference images.
Records UV overlap and renders the resulting real mesh for comparison.
"""
import bpy,numpy as np,json,time,sys
from pathlib import Path
from mathutils import Vector
reunwrap='--reunwrap' in sys.argv
mip_safe='--mip' in sys.argv
root=Path('C:/ProjectHub3D/cache/style-iteration/'+('v27' if mip_safe else ('v23' if reunwrap else 'v14')));root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v11/projection-debug.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene;body=next(o for o in scene.objects if o.type=='MESH' and not o.hide_render);mesh=body.data
if reunwrap:
    bpy.ops.object.select_all(action='DESELECT');body.select_set(True);bpy.context.view_layer.objects.active=body
    mesh.uv_layers.active=mesh.uv_layers['UVMap'];mesh.uv_layers.active.active_render=True
    tri=body.modifiers.new('Stable triangles','TRIANGULATE');bpy.ops.object.modifier_apply(modifier=tri.name)
    mesh=body.data;mesh.uv_layers.active=mesh.uv_layers['UVMap'];mesh.uv_layers.active.active_render=True
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=.5,island_margin=.003,area_weight=0.)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True,margin_method='FRACTION',margin=.0007)
    bpy.ops.object.mode_set(mode='OBJECT')
mesh.calc_loop_triangles()
size=4096;atlas=np.zeros((size,size,4),np.float32);atlas[:,:,3]=1;coverage=np.zeros((size,size),np.uint8)
views={}
for key in ['front','back','left','right']:
    img=bpy.data.images.get('texture-guide-'+key+'-v8.png')
    rgba=np.asarray(img.pixels[:],np.float32).reshape(img.size[1],img.size[0],4)
    linear=np.where(rgba[:,:,:3]<=.04045,rgba[:,:,:3]/12.92,((rgba[:,:,:3]+.055)/1.055)**2.4)
    mask_data=np.load('D:/ProjectHub3D/references/guide-mask-'+key+'.npz')
    views[key]={'rgb':linear,'uv':np.array([v.uv[:] for v in mesh.uv_layers['Guide_'+key].data]),'weight':np.array([d.value for d in mesh.attributes[key+'_weight'].data]),'mask':mask_data['mask'],'nearest':mask_data['nearest']}
uv=np.array([v.uv[:] for v in mesh.uv_layers['UVMap'].data]);fallback=np.array([v.color[:3] for v in mesh.color_attributes['GuideFallbackColor'].data])
started=time.time();overlap=0
for i,tri in enumerate(mesh.loop_triangles):
    loops=np.array(tri.loops);verts=np.array(tri.vertices);xy=uv[loops]*size-.5
    lo=np.maximum(np.floor(xy.min(axis=0)).astype(int),0);hi=np.minimum(np.ceil(xy.max(axis=0)).astype(int),size-1)
    if (hi<lo).any():continue
    yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];points=np.stack([xx.ravel(),yy.ravel()],axis=1)
    a,b,c=xy;delta=b-a;edge=c-a;det=delta[0]*edge[1]-delta[1]*edge[0]
    if abs(det)<1e-10:continue
    rel=points-a;v=(rel[:,0]*edge[1]-rel[:,1]*edge[0])/det;w=(delta[0]*rel[:,1]-delta[1]*rel[:,0])/det;u=1-v-w
    inside=(u>=-1e-7)&(v>=-1e-7)&(w>=-1e-7)
    if not inside.any():continue
    bary=np.stack([u[inside],v[inside],w[inside]],axis=1);points=points[inside]
    colors=np.zeros((len(points),3));weights=np.zeros(len(points))
    for data in views.values():
        proj=bary@data['uv'][loops];rgb=data['rgb'];h,width=rgb.shape[:2]
        sx=np.clip(proj[:,0]*width-.5,0,width-1.0001);sy=np.clip(proj[:,1]*h-.5,0,h-1.0001)
        mx=np.rint(sx).astype(int);my=np.rint(sy).astype(int);outside=~data['mask'][my,mx]
        sx[outside]=data['nearest'][1,my[outside],mx[outside]];sy[outside]=data['nearest'][0,my[outside],mx[outside]]
        ix=sx.astype(int);iy=sy.astype(int);fx=sx-ix;fy=sy-iy
        sampled=(rgb[iy,ix]*(1-fx[:,None])+rgb[iy,ix+1]*fx[:,None])*(1-fy[:,None])+(rgb[iy+1,ix]*(1-fx[:,None])+rgb[iy+1,ix+1]*fx[:,None])*fy[:,None]
        weight=np.maximum(bary@data['weight'][verts],0)*(sampled.min(axis=1)<.60)
        colors+=sampled*weight[:,None];weights+=weight
    residual=np.maximum(.001-weights,0);colors+=(bary@fallback[verts])*residual[:,None];weights+=residual
    colors/=weights[:,None];colors=np.where(colors<=.0031308,colors*12.92,1.055*np.maximum(colors,0)**(1/2.4)-.055)
    px,py=points[:,0],points[:,1];overlap+=int((coverage[py,px]>0).sum());coverage[py,px]+=1;atlas[py,px,:3]=colors
    if i%5000==0:print('UV_BAKE',i,len(mesh.loop_triangles),flush=True)
# Padding is generated from baked adjacent texels, not from the source background.
mask=coverage>0
for _ in range(12 if mip_safe else 2):
    old=mask.copy()
    for dy,dx in [(0,1),(0,-1),(1,0),(-1,0)]:
        shifted=np.roll(np.roll(old,dy,0),dx,1);take=shifted&~mask
        shifted_rgb=np.roll(np.roll(atlas,dy,0),dx,1);atlas[take]=shifted_rgb[take];mask[take]=True
texture=bpy.data.images.new('WindRonin_BaseColor_4K_Explicit',size,size,alpha=False);texture.colorspace_settings.name='sRGB';texture.pixels.foreach_set(atlas.ravel())
texture.filepath_raw=str(root/'Painted_BaseColor_4K.png');texture.file_format='PNG';texture.save();texture.pack()
nodes=body.data.materials[0].node_tree.nodes;links=body.data.materials[0].node_tree.links;nodes.clear()
out=nodes.new('ShaderNodeOutputMaterial');em=nodes.new('ShaderNodeEmission');tex=nodes.new('ShaderNodeTexImage');tex.image=texture
uvnode=nodes.new('ShaderNodeUVMap');uvnode.uv_map='UVMap';links.new(uvnode.outputs[0],tex.inputs[0]);links.new(tex.outputs[0],em.inputs[0]);links.new(em.outputs[0],out.inputs[0])
for name in [u.name for u in mesh.uv_layers]:
    if name!='UVMap':mesh.uv_layers.remove(mesh.uv_layers[name])
report={'bake_seconds':time.time()-started,'covered_texels':int((coverage>0).sum()),'overlapping_texels':overlap,'padding_iterations':12 if mip_safe else 2,'method':'Explicit per-triangle barycentric UV bake of guide UVs and surface weights'}
(root/'bake-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('EXPLICIT_BAKE',report,flush=True)
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
    scene.camera.location=pos;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'character.blend'))
