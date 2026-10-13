"""Correct audited arm/finger/leg influence leakage into the torso and hands."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,'D:/ProjectHub3D/pipeline');import blender_pipeline as kit
root=Path('C:/ProjectHub3D/cache/style-iteration/v29');root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v28/prepared.blend',load_ui=False,use_scripts=False)
scene=bpy.context.scene;body=bpy.data.objects['WindRonin_LOD0'];rig=next(o for o in scene.objects if o.type=='ARMATURE')
def smooth(value):
    t=max(0,min(1,value));return t*t*(3-2*t)
changes={'torso':0,'hands':0}
for vertex in body.data.vertices:
    x,y,z=vertex.co;old={body.vertex_groups[g.group].name:g.weight for g in vertex.groups if g.weight>1e-6}
    strength=smooth((.245-abs(x))/.065)*smooth((z-.96)/.08)*(1-smooth((z-1.38)/.10)) if y<.16 else 0
    if strength>0:
        if z<1.12:target={'hips':1.}
        elif z<1.31:
            t=smooth((z-1.12)/.19);target={'hips':1-t,'spine':t}
        else:
            t=smooth((z-1.31)/.19);target={'spine':1-t,'chest':t}
        weights={name:value*(1-strength) for name,value in old.items()}
        for name,value in target.items():weights[name]=weights.get(name,0)+value*strength
        changes['torso']+=1
    elif abs(x)>.34 and z<1.12:
        side='.L' if x>0 else '.R'
        weights={name:value for name,value in old.items() if name.endswith(side) and name.startswith(('hand','forearm','finger'))}
        if not weights:weights={'hand'+side:1.}
        changes['hands']+=1
    else:continue
    for group in body.vertex_groups:group.remove([vertex.index])
    total=sum(weights.values())
    for name,value in weights.items():
        if value>1e-6:body.vertex_groups[name].add([vertex.index],value/total,'REPLACE')
kit.normalize_skin(body)
rig['rig_method']='32-bone FK humanoid; torso/hand influence leakage corrected with smooth region masks; normalized <=4 influences; Idle/Walk/JointTest'
rig.animation_data.action=None
for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
scene.frame_set(1)
for name,pos in [('front',(0,-4,.95)),('three-quarter',(2,-4,1.15)),('back',(0,4,.95))]:
    scene.camera.location=pos;scene.camera.data.ortho_scale=2.12;scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
for name,frame in [('Walk',7),('JointTest',13)]:
    rig.animation_data.action=bpy.data.actions[name];scene.frame_set(frame)
    scene.camera.location=(2,-4,1.15);scene.camera.rotation_euler=(Vector((0,0,.95))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
rig.animation_data.action=None
for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0)
scene.frame_set(1)
(root/'weight-correction.json').write_text(json.dumps(changes,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(root/'prepared.blend'));print('WEIGHTS_CORRECTED',changes)
