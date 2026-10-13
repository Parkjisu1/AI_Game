"""ProjectHub's Blender worker. Run with --background --disable-autoexec --python ... -- job.json.

The procedural demo is a technical prototype, never an art-approved delivery.
Imported assets retain their authored topology/materials/rig. Missing rig/UV goes to review.
"""
import argparse
import hashlib
import json
import math
import re
import runpy
from pathlib import Path
import sys
import time
import zipfile

import bpy
import bmesh
import numpy as np
from mathutils import Vector

PARTS = []
BONES = {}
MAT = None


def active(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def atlas(out, palette_override=None):
    """Authored parametric material atlas; deliberately shared swatch UVs, not unique bake UVs."""
    global MAT
    size = 2048
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u, v = (xx % 512) / 512, (yy % 1024) / 1024
    palette = np.array([(0.65, .40, .25), (.045, .11, .13), (.022, .032, .058),
                        (.42, .12, .075), (.59, .54, .41), (.09, .06, .043),
                        (.39, .48, .54), (.56, .35, .12)], dtype=np.float32)
    if palette_override is not None: palette=np.array(palette_override,dtype=np.float32)
    slots = (xx // 512 + (yy // 1024) * 4).astype(np.int32)
    broad = .78 + .22 * v + .055 * np.sin(u * math.pi)
    weave = .012 * np.sin(xx * 1.6) * np.sin(yy * 1.9)
    brush = .015 * np.sin(u * 54 + np.sin(v * 14))
    maps = {}
    for name in ('BaseColor', 'Roughness', 'Metallic', 'Normal'):
        data = np.ones((size, size, 4), dtype=np.float32)
        if name == 'BaseColor':
            data[:, :, :3] = np.clip(palette[slots] * (broad + weave + brush)[:, :, None], 0, 1)
        elif name == 'Roughness':
            values = np.array([.62, .82, .7, .79, .86, .57, .3, .38])
            data[:, :, :3] = (values[slots] + weave)[:, :, None]
        elif name == 'Metallic':
            data[:, :, :3] = np.where(slots >= 6, 1., 0.)[:, :, None]
        else:
            data[:, :, 0] = .5 + .015 * np.sin(xx * 1.6)
            data[:, :, 1] = .5 + .015 * np.sin(yy * 1.9)
            data[:, :, 2] = .9995
        img = bpy.data.images.new('WindRonin_' + name, size, size, alpha=True)
        # Pixel values are authored in linear space; Blender converts color data to sRGB PNG.
        img.colorspace_settings.name = 'sRGB' if name == 'BaseColor' else 'Non-Color'
        img.pixels.foreach_set(data.ravel())
        img.filepath_raw = str(out / 'textures' / (name + '.png'))
        img.file_format = 'PNG'
        img.save()
        maps[name] = img
    MAT = bpy.data.materials.new('WindRonin_Atlas')
    MAT.use_nodes = True
    nodes, links = MAT.node_tree.nodes, MAT.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    for name, socket in [('BaseColor', 'Base Color'), ('Roughness', 'Roughness'), ('Metallic', 'Metallic')]:
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = maps[name]
        links.new(tex.outputs['Color'], bsdf.inputs[socket])
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = maps['Normal']
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(tex.outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])


def finish(obj, name, slot, bone, smooth=True):
    obj.name = name
    active(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.data.materials.clear()
    obj.data.materials.append(MAT)
    if not obj.data.uv_layers:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(island_margin=.015)
        bpy.ops.object.mode_set(mode='OBJECT')
    for loop in obj.data.uv_layers.active.data:
        loop.uv.x = (slot % 4 + .035 + loop.uv.x * .93) / 4
        loop.uv.y = (slot // 4 + .02 + loop.uv.y * .96) / 2
    for poly in obj.data.polygons:
        poly.use_smooth = smooth
    group = obj.vertex_groups.new(name=bone)
    group.add(list(range(len(obj.data.vertices))), 1., 'REPLACE')
    PARTS.append(obj)
    return obj


def ellipsoid(name, location, scale, slot, bone, segments=20, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.scale = scale
    return finish(obj, name, slot, bone)


def tube(name, points, radii, slot, bone, sides=12):
    vertices, faces = [], []
    for i, point in enumerate(points):
        tangent = Vector(points[min(i+1, len(points)-1)]) - Vector(points[max(i-1, 0)])
        tangent.normalize()
        ref = Vector((0, 1, 0)) if abs(tangent.y) < .9 else Vector((1, 0, 0))
        right = tangent.cross(ref).normalized()
        forward = tangent.cross(right).normalized()
        radius = radii[i]
        rx, ry = radius if isinstance(radius, tuple) else (radius, radius)
        for j in range(sides):
            a = 2 * math.pi * j / sides
            vertices.append(Vector(point) + right * math.cos(a) * rx + forward * math.sin(a) * ry)
    for i in range(len(points)-1):
        for j in range(sides):
            a, b = i*sides+j, i*sides+(j+1)%sides
            faces.append((a, b, b+sides, a+sides))
    faces.extend([tuple(reversed(range(sides))), tuple((len(points)-1)*sides+j for j in range(sides))])
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    return finish(obj, name, slot, bone)


def ribbon(name, points, widths, slot, bone):
    verts, faces = [], []
    for i, (x, y, z) in enumerate(points):
        w = widths[i]
        verts.extend([(x-w, y, z), (x, y-.022, z+.008), (x+w, y, z)])
    for i in range(len(points)-1):
        for j in range(2):
            a = i*3+j
            faces.append((a, a+1, a+4, a+3))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    active(obj)
    mod = obj.modifiers.new('Cloth thickness', 'SOLIDIFY')
    mod.thickness = .008
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return finish(obj, name, slot, bone)


def bone(name, head, tail, parent=None):
    BONES[name] = (head, tail, parent)


def make_demo(out):
    atlas(out)
    bone('root', (0, 0, 0), (0, 0, .15))
    bone('hips', (0, 0, .92), (0, 0, 1.1), 'root')
    bone('spine', (0, 0, 1.1), (0, 0, 1.31), 'hips')
    bone('chest', (0, 0, 1.31), (0, 0, 1.53), 'spine')
    bone('neck', (0, 0, 1.53), (0, 0, 1.66), 'chest')
    bone('head', (0, 0, 1.66), (0, 0, 1.91), 'neck')
    bone('hair', (0, .08, 1.89), (.03, .23, 1.54), 'head')
    bone('scarf', (-.18, .09, 1.5), (-.42, .19, 1.18), 'chest')
    tube('Tunic', [(0,0,1.02),(0,0,1.12),(0,0,1.3),(0,0,1.44),(0,0,1.51)],
         [(.16,.10),(.145,.092),(.2,.12),(.245,.12),(.16,.085)],4,'chest',20)
    tube('Neck', [(0,0,1.48),(0,0,1.68)], [.065,.062],0,'neck')
    ellipsoid('Face', (0,-.015,1.762), (.098,.083,.137),0,'head',24,16)
    tube('Jaw', [(0,-.004,1.647),(0,-.033,1.685),(0,-.014,1.745)], [.055,(.082,.061),(.087,.065)],0,'head')
    ellipsoid('Nose', (0,-.097,1.755), (.017,.03,.034),0,'head',12,8)
    for s, side in [(1,'L'),(-1,'R')]:
        ellipsoid('Ear.'+side,(s*.1,0,1.765),(.018,.022,.035),0,'head',12,8)
        ellipsoid('Eye.'+side,(s*.041,-.089,1.793),(.022,.009,.009),4,'head',12,8)
        ellipsoid('Iris.'+side,(s*.04,-.097,1.792),(.007,.004,.007),2,'head',12,8)
        tube('Brow.'+side,[(s*.02,-.089,1.812),(s*.042,-.093,1.817),(s*.068,-.079,1.811)], [.007,.009,.003],2,'head',8)
        bone('clavicle.'+side,(0,0,1.49),(s*.23,0,1.47),'chest')
        shoulder, elbow, wrist = (s*.23,0,1.47),(s*.4,0,1.25),(s*.51,-.025,1.035)
        bone('upper_arm.'+side,shoulder,elbow,'clavicle.'+side)
        bone('forearm.'+side,elbow,wrist,'upper_arm.'+side)
        bone('hand.'+side,wrist,(s*.56,-.03,.94),'forearm.'+side)
        tube('UpperArm.'+side,[shoulder,(s*.3,0,1.4),(s*.36,0,1.32),elbow], [.079,.085,.066,.052],0,'upper_arm.'+side)
        ellipsoid('Elbow.'+side,elbow,(.05,.049,.052),0,'forearm.'+side,16,10)
        tube('Forearm.'+side,[elbow,(s*.44,-.012,1.17),wrist],[.05,.062,.034],0,'forearm.'+side)
        tube('Bracer.'+side,[(s*.446,-.014,1.16),wrist],[.058,.039],5,'forearm.'+side)
        ellipsoid('Palm.'+side,(s*.538,-.028,.985),(.038,.022,.058),0,'hand.'+side)
        for finger in range(4):
            x=s*(.515+finger*.014)
            p0=(x,-.032,.959)
            p1=(x+s*.022,-.035,.90+abs(finger-1)*.008)
            finger_name='finger%d.%s'%(finger,side)
            bone(finger_name,p0,p1,'hand.'+side)
            tube(finger_name,[p0,p1],[.009,.006],0,finger_name,8)
        tube('Thumb.'+side,[(s*.509,-.043,1.01),(s*.487,-.059,.97)], [.013,.008],0,'hand.'+side,8)
        hip,knee,ankle=(s*.1,0,1.02),(s*.12,-.016,.55),(s*.13,0,.14)
        bone('thigh.'+side,hip,knee,'hips')
        bone('shin.'+side,knee,ankle,'thigh.'+side)
        bone('foot.'+side,ankle,(s*.13,-.16,.065),'shin.'+side)
        tube('Trousers.'+side,[hip,(s*.115,0,.89),(s*.14,0,.69),knee], [.12,.135,.115,.071],2,'thigh.'+side,16)
        tube('Shin.'+side,[knee,(s*.128,0,.40),ankle], [.072,.067,.043],5,'shin.'+side)
        for k in range(6):
            z=.22+k*.047
            tube('LegWrap.%s.%d'%(side,k),[(s*.13,0,z),(s*.13,0,z+.017)], [.057+(z-.22)*.04]*2,4,'shin.'+side,12)
        ellipsoid('Boot.'+side,(s*.13,-.05,.082),(.064,.133,.066),5,'foot.'+side)
    tube('Sash',[(0,0,1.026),(0,0,1.08),(0,0,1.12)],[(.169,.112),(.166,.105),(.158,.1)],3,'hips',24)
    ribbon('SashTail',[(.14,-.11,1.08),(.21,-.13,.91),(.24,-.1,.73),(.32,-.08,.63)],[.035,.04,.032,.006],3,'hips')
    ribbon('TunicSkirt',[(0,-.105,1.045),(0,-.13,.92),(.025,-.13,.79)],[.13,.135,.09],4,'hips')
    for k in range(3):
        z=1.51-k*.047
        ellipsoid('ShoulderPlate%d'%k,(.265+k*.008,-.005,z),(.12,.143,.06),2,'upper_arm.L',16,8)
        tube('PlateTrim%d'%k,[(.175,-.116,z),(.265,-.148,z-.013),(.35,-.1,z-.021)],[.008]*3,7,'upper_arm.L',8)
    for k in range(4):
        ribbon('ScarfFold%d'%k,[(-.24,-.03,1.52-k*.02),(-.13,-.14,1.52-k*.024),(.02,-.146,1.51-k*.018),(.15,-.09,1.53-k*.017)], [.035,.038,.03,.025],1,'chest')
    ribbon('ScarfTail',[(-.17,.04,1.52),(-.31,.17,1.39),(-.38,.22,1.21),(-.57,.24,1.2)],[.095,.09,.065,.004],1,'scarf')
    ribbon('BeltStrap',[(-.17,-.11,1.43),(-.08,-.136,1.29),(.045,-.112,1.1)],[.022]*3,5,'chest')
    ellipsoid('HairCap',(0,.018,1.835),(.105,.081,.104),2,'head',20,12)
    for k in range(11):
        x=(k-5)*.017
        tube('HairLock%d'%k,[(x,.055,1.88),(x*.8,-.015,1.929),(x,-.081,1.868),(x*1.1,-.08,1.805+abs(k-5)*.005)], [.017,.02,.016,.001],2,'head',8)
    for k in range(7):
        x=(k-3)*.012
        tube('Ponytail%d'%k,[(x,.085,1.88),(x,.17,1.78),(x+.02,.23,1.61),(x+.09,.25,1.48)], [.018,.032,.024,.001],2,'hair',8)
    tube('Moustache',[(-.028,-.091,1.709),(0,-.103,1.718),(.028,-.091,1.709)],[.007,.008,.007],2,'head',8)
    ellipsoid('Beard',(0,-.071,1.68),(.052,.018,.025),2,'head',16,8)
    # Sheathed katana on hip, with a dedicated attachment bone.
    bone('weapon',(-.2,.025,1.04),(-.4,.1,.5),'hips')
    tube('KatanaSheath',[(-.18,.025,1.08),(-.26,.04,.88),(-.38,.07,.61),(-.44,.095,.45)], [.025,.026,.022,.012],2,'weapon',10)
    tube('KatanaHandle',[(-.18,.025,1.08),(-.11,.011,1.28)],[.021,.02],5,'weapon',12)
    ellipsoid('KatanaGuard',(-.178,.025,1.083),(.065,.05,.013),7,'weapon',20,8)
    for k in range(5):
        z=1.12+k*.03
        x=-.18+(z-1.08)*.35
        tube('HandleWrap%d'%k,[(x,.021,z),(x+.005,.02,z+.012)],[.023,.023],4,'weapon',10)
    # Separate drawn blade, included as an optional object in the .blend.
    blade=tube('Katana_Drawn',[(-.75,0,.22),(-.735,0,.45),(-.70,0,.75),(-.66,0,1.08)],[(.014,.004),(.019,.004),(.019,.004),(.001,.001)],6,'weapon',4)
    PARTS.remove(blade)
    blade.hide_render=True
    blade.hide_viewport=True
    active(PARTS[0])
    for obj in PARTS:
        obj.select_set(True)
    bpy.ops.object.join()
    body=bpy.context.object
    body.name='WindRonin_LOD0'
    rig_data=bpy.data.armatures.new('WindRoninSkeleton')
    rig=bpy.data.objects.new('WindRonin_Rig',rig_data)
    bpy.context.collection.objects.link(rig)
    active(rig)
    bpy.ops.object.mode_set(mode='EDIT')
    for name,(head,tail,parent) in BONES.items():
        b=rig_data.edit_bones.new(name)
        b.head,b.tail=head,tail
        if parent:
            b.parent=rig_data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    body.parent=rig
    mod=body.modifiers.new('Armature','ARMATURE')
    mod.object=rig
    rig.show_in_front=True
    # Smooth influence transitions close to limb joints; <=2 influences per vertex.
    joints=[('upper_arm.'+s,'forearm.'+s,BONES['forearm.'+s][0],.065) for s in ['L','R']]
    joints += [('thigh.'+s,'shin.'+s,BONES['shin.'+s][0],.075) for s in ['L','R']]
    for ga,gb,position,radius in joints:
        a,b=body.vertex_groups.get(ga),body.vertex_groups.get(gb)
        for vertex in body.data.vertices:
            if not any(g.group in (a.index,b.index) for g in vertex.groups):
                continue
            p=body.matrix_world @ vertex.co
            d=(p-Vector(position)).length
            if d<radius:
                wa=.5+.5*max(-1,min(1,(p.z-position[2])/radius))
                a.add([vertex.index],wa,'REPLACE')
                b.add([vertex.index],1-wa,'REPLACE')
    rig.animation_data_create()
    for name,frames in [('Idle',61),('Walk',25),('JointTest',49)]:
        action=bpy.data.actions.new(name)
        action.use_fake_user=True
        rig.animation_data.action=action
        for frame in range(1,frames+1,3):
            t=(frame-1)/(frames-1)*2*math.pi
            for pb in rig.pose.bones:
                pb.rotation_mode='XYZ'
                pb.rotation_euler=(0,0,0)
                pb.location=(0,0,0)
            rig.pose.bones['chest'].rotation_euler.y=math.sin(t)*.025
            rig.pose.bones['hair'].rotation_euler.x=math.sin(t+.6)*.08
            rig.pose.bones['scarf'].rotation_euler.y=math.sin(t+.3)*.1
            if name in ('Walk','JointTest'):
                amplitude=.35 if name=='Walk' else .8
                for sign,side in [(1,'L'),(-1,'R')]:
                    rig.pose.bones['thigh.'+side].rotation_euler.x=sign*math.sin(t)*amplitude
                    rig.pose.bones['shin.'+side].rotation_euler.x=max(0,-sign*math.sin(t))*amplitude
                    rig.pose.bones['upper_arm.'+side].rotation_euler.x=-sign*math.sin(t)*amplitude*.7
                    rig.pose.bones['forearm.'+side].rotation_euler.x=max(0,sign*math.sin(t))*amplitude
            for pb in rig.pose.bones:
                pb.keyframe_insert('rotation_euler',frame=frame,group=pb.name)
        rig.animation_data.action=None
        track=rig.animation_data.nla_tracks.new()
        track.name=name
        track.strips.new(name,1,action)
        track.mute=True
    # Exporter exports action datablocks. Muted NLA keeps the rest pose clean in the source scene.
    bpy.context.scene.frame_set(1)
    return [body],[rig]


def metrics(meshes, rigs):
    result={'triangles':0,'vertices':0,'materials':0,'bones':sum(len(r.data.bones) for r in rigs),
            'missing_uv':[],'unweighted_vertices':0,'weight_sum_errors':0,'max_influences':0,
            'degenerate_faces':0,'non_manifold_edges':0,'missing_images':[]}
    materials=set()
    for obj in meshes:
        mesh=obj.data
        mesh.calc_loop_triangles()
        result['triangles']+=len(mesh.loop_triangles)
        result['vertices']+=len(mesh.vertices)
        materials.update(m.name for m in mesh.materials if m)
        if not mesh.uv_layers:
            result['missing_uv'].append(obj.name)
        bm=bmesh.new(); bm.from_mesh(mesh)
        result['non_manifold_edges']+=sum(not e.is_manifold for e in bm.edges)
        result['degenerate_faces']+=sum(f.calc_area()<1e-10 for f in bm.faces)
        bm.free()
        arm=next((m.object for m in obj.modifiers if m.type=='ARMATURE' and m.object),None)
        deform={g.index for g in obj.vertex_groups if arm and g.name in arm.data.bones and arm.data.bones[g.name].use_deform}
        for vert in mesh.vertices:
            weights=[g.weight for g in vert.groups if g.group in deform and g.weight>1e-6]
            if rigs and not weights:
                result['unweighted_vertices']+=1
            if weights and abs(sum(weights)-1)>.01:
                result['weight_sum_errors']+=1
            result['max_influences']=max(result['max_influences'],len(weights))
    result['materials']=len(materials)
    for img in bpy.data.images:
        if img.source=='FILE' and not img.packed_file and not Path(bpy.path.abspath(img.filepath)).is_file():
            result['missing_images'].append(img.name)
    return result


def normalize_skin(obj):
    if any(m.type=='ARMATURE' and m.object for m in obj.modifiers):
        active(obj)
        bpy.ops.object.vertex_group_limit_total(group_select_mode='BONE_DEFORM',limit=4)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode='BONE_DEFORM',lock_active=False)


def export_fbx(meshes, path):
    """FBX needs a Principled base-color connection; glTF's unlit nodes are different."""
    replacements, variants = [], {}
    try:
        for obj in meshes:
            for index, mat in enumerate(obj.data.materials):
                if not mat or not mat.get('projecthub_painted_unlit'): continue
                if mat not in variants:
                    variant=mat.copy();variant.name=mat.name+'_FBX'
                    nodes,links=variant.node_tree.nodes,variant.node_tree.links
                    tex=next(n for n in nodes if n.type=='TEX_IMAGE' and n.image)
                    output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
                    bsdf=nodes.new('ShaderNodeBsdfPrincipled')
                    bsdf.inputs['Roughness'].default_value=.85
                    links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
                    links.new(bsdf.outputs[0],output.inputs['Surface'])
                    variants[mat]=variant
                replacements.append((obj,index,mat));obj.data.materials[index]=variants[mat]
        bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,
            object_types={'MESH','ARMATURE'},add_leaf_bones=False,
            bake_anim=True,bake_anim_use_nla_strips=False,bake_anim_use_all_actions=True,
            path_mode='COPY',embed_textures=True,axis_forward='-Z',axis_up='Y')
    finally:
        for obj,index,mat in replacements: obj.data.materials[index]=mat
        for variant in variants.values(): bpy.data.materials.remove(variant)


def render_preview(meshes, out):
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=32
    try:
        prefs=bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type='OPTIX'
        prefs.get_devices()
        gpu=False
        for d in prefs.devices:
            d.use=d.type!='CPU'
            gpu |= d.use
        if gpu: scene.cycles.device='GPU'
    except Exception: pass
    scene.render.resolution_x=1000
    scene.render.resolution_y=1000
    scene.render.resolution_percentage=100
    if not scene.world: scene.world=bpy.data.worlds.new('Studio World')
    scene.world.color=(.18,.18,.18)
    bounds=[obj.matrix_world@Vector(v) for obj in meshes for v in obj.bound_box]
    low=Vector(tuple(min(p[i] for p in bounds) for i in range(3)))
    high=Vector(tuple(max(p[i] for p in bounds) for i in range(3)))
    center=(low+high)/2
    height=max(high.z-low.z,.1)
    bpy.ops.object.camera_add(location=center+Vector((height*.95,-height*2,height*.45)))
    camera=bpy.context.object
    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO'
    camera.data.ortho_scale=height*1.32
    scene.camera=camera
    for name,loc,energy,color in [('Key',(-3,-4,5),650,(1,.86,.7)),('Fill',(3,-2,3),450,(.65,.82,1)),('Rim',(1,3,4),900,(.6,.85,1))]:
        bpy.ops.object.light_add(type='AREA',location=center+Vector(loc)*height/2)
        light=bpy.context.object
        light.name=name
        light.data.energy=energy
        light.data.color=color
        light.data.shape='DISK';light.data.size=height*1.5
        light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
    scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG'
    scene.render.filepath=str(out/'preview.png')
    bpy.ops.render.render(write_still=True)


def main(job):
    out=Path(job['output']).resolve()
    out.mkdir(parents=True,exist_ok=True)
    (out/'textures').mkdir(exist_ok=True)
    bpy.context.preferences.filepaths.temporary_directory='C:/ProjectHub3D/cache/'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.unit_settings.system='METRIC'
    scene.unit_settings.scale_length=1
    scene.render.fps=30
    demo=job.get('mode')=='demo'
    if demo:
        meshes,rigs=make_demo(out)
    else:
        if job.get('mode')=='image':
            runpy.run_path(str(Path(__file__).with_name('prepare_generated.py')),run_name='__main__')
        else:
            source=Path(job['source'])
            ext=source.suffix.lower()
            if ext=='.blend': bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
            elif ext=='.glb': bpy.ops.import_scene.gltf(filepath=str(source))
            elif ext=='.fbx': bpy.ops.import_scene.fbx(filepath=str(source))
            elif ext=='.obj': bpy.ops.wm.obj_import(filepath=str(source))
            else: raise ValueError('Unsupported source format')
        meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render]
        rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
        if not meshes: raise ValueError('No visible mesh in input')
        used_images={node.image for obj in meshes for mat in obj.data.materials if mat and mat.use_nodes
                     for node in mat.node_tree.nodes if node.type=='TEX_IMAGE' and node.image}
        for index,img in enumerate(sorted(used_images,key=lambda i:i.name)):
            # Packed images can be lazy-loaded after opening a .blend in background mode.
            # Checking has_data before touching pixels silently omitted standalone PNGs.
            if len(img.pixels): _=img.pixels[0]
            if not img.has_data: continue
            name=re.sub(r'[^A-Za-z0-9_.-]','_',img.name)
            img.filepath_raw=str(out/'textures'/f'{index:02d}_{name}.png')
            img.file_format='PNG';img.save()
    lod0=metrics(meshes,rigs)
    issues=[]
    if not rigs: issues.append('Rig missing: fit a humanoid rig and paint/test weights before delivery.')
    if lod0['missing_uv']: issues.append('UV unwrap required: '+', '.join(lod0['missing_uv']))
    if lod0['missing_images']: issues.append('Missing external textures; upload a packed .blend or embedded GLB.')
    for key in ['unweighted_vertices','weight_sum_errors','degenerate_faces']:
        if lod0[key]: issues.append(f'{key}: {lod0[key]}')
    if lod0['max_influences']>4: issues.append('More than 4 bone influences per vertex.')
    budget=12000 if job.get('profile')=='mobile' else 30000
    if lod0['triangles']>budget: issues.append(f'LOD0 has {lod0["triangles"]} triangles; target {budget}. Retopology review required.')
    lods=[]
    all_assets=list(meshes)+list(rigs)
    for level,ratio in enumerate([1,.5,.25]):
        copies=[]
        if level==0: copies=meshes
        else:
            for original in meshes:
                obj=original.copy();obj.data=original.data.copy()
                bpy.context.collection.objects.link(obj)
                obj.name=original.name.replace('_LOD0','')+f'_LOD{level}'
                active(obj)
                modifier=obj.modifiers.new('LOD reduction','DECIMATE')
                modifier.ratio=ratio
                while obj.modifiers.find(modifier.name)>0:
                    bpy.ops.object.modifier_move_up(modifier=modifier.name)
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                obj.data.validate(verbose=False,clean_customdata=False)
                obj.data.update()
                normalize_skin(obj)
                copies.append(obj)
                all_assets.append(obj)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in copies+rigs:
            obj.hide_set(False);obj.select_set(True)
        bpy.context.view_layer.objects.active=copies[0]
        file=out/f'character_LOD{level}.glb'
        bpy.ops.export_scene.gltf(filepath=str(file),export_format='GLB',use_selection=True,
                                  export_animations=True,export_animation_mode='ACTIONS',export_rest_position_armature=True)
        if level==0:
            export_fbx(meshes,out/'character.fbx')
        lods.append({'level':level,'file':file.name,**metrics(copies,rigs)})
        if level:
            for obj in copies: obj.hide_render=True;obj.hide_set(True)
    for lod in lods:
        if lod['max_influences']>4:issues.append(f'LOD{lod["level"]}: more than 4 bone influences')
        for key in ['degenerate_faces','weight_sum_errors','unweighted_vertices','non_manifold_edges']:
            if lod[key]: issues.append(f'LOD{lod["level"]} {key}: {lod[key]} (inspect geometry/deformation)')
    render_preview(meshes,out)
    for img in bpy.data.images:
        if img.source=='FILE' and img.has_data:
            try: img.pack()
            except RuntimeError: pass
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'character.blend'))
    report={'schema_version':1,'state':'technical_preview' if demo else 'needs_review',
            'art_approved':False,'engine_verified':False,'technical_pass':not issues,
            'mode':job.get('mode'),'blender_version':bpy.app.version_string,'profile':job.get('profile','pc'),
            'painted_unlit':all(m.get('projecthub_painted_unlit',False) for o in meshes for m in o.data.materials if m),
            'lods':lods,'issues':issues,'review_required':['Silhouette and likeness against reference',
            'Face anatomy, hand detail and material painting','Shoulder/elbow/knee deformation and cloth clipping',
            'LOD silhouette at engine camera distance','Unity/Unreal import, clips, draw calls and GPU timing'],
            'texture_method':'Shared parametric 2K atlas with intentional UV reuse; microdetail normal, no high-poly bake' if demo else next((o.get('texture_method') for o in meshes if o.get('texture_method')),'Preserved source materials'),
            'rig_method':'Procedural FK humanoid with blended limb joint weights; no facial rig or IK' if demo else next((o.get('rig_method') for o in rigs if o.get('rig_method')),'Preserved source rig'),
            'created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    (out/'README.txt').write_text('PROJECTHUB 3D ASSET PACK\nStatus: TECHNICAL PREVIEW / ART REVIEW REQUIRED\n'
        'Open character.blend. Textures are packed. GLB files contain separate LODs; use only one LOD at a time.\n'
        'FBX is exported for Unity/Unreal; Humanoid mapping, animation and runtime performance require engine verification.\n'
        'Painted packs use KHR_materials_unlit in GLB. For matching FBX appearance, assign an engine Unlit shader with the included BaseColor textures.\n'
        f'Mode: {report["mode"]}\nTexture: {report["texture_method"]}\nRig: {report["rig_method"]}\n'
        'Do not interpret a technical_pass as final art approval. See report.json for evidence and limitations.\n',encoding='utf8')
    manifest=[]
    for path in sorted(out.rglob('*')):
        if path.is_file() and path.suffix not in ('.zip','.blend1') and path.name not in ('manifest.json','roundtrip-check.json'):
            manifest.append({'path':path.relative_to(out).as_posix(),'bytes':path.stat().st_size,
                             'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (out/'manifest.json').write_text(json.dumps({'files':manifest},indent=2),encoding='utf8')
    with zipfile.ZipFile(out/'model-pack.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for item in manifest: archive.write(out/item['path'],item['path'])
        archive.write(out/'manifest.json','manifest.json')
    print('PROJECTHUB_RESULT '+json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('job')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    main(json.loads(Path(args.job).read_text(encoding='utf-8-sig')))
