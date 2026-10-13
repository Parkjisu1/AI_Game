import bpy
from pathlib import Path
root=Path('D:/ProjectHub3D/jobs/6aa118aab4e9da5eb64d438e/output')
bpy.ops.wm.open_mainfile(filepath=str(root/'character.blend'),load_ui=False,use_scripts=False)
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
for track in rig.animation_data.nla_tracks:track.mute=True
for name,frame in [('Walk',7),('JointTest',13)]:
    action=next(a for a in bpy.data.actions if a.name==name)
    rig.animation_data.action=action
    if action.slots:rig.animation_data.action_slot=action.slots[0]
    bpy.context.scene.frame_set(frame)
    bpy.context.scene.render.resolution_percentage=70
    bpy.context.scene.render.filepath=str(root/(name+'-check.png'))
    bpy.ops.render.render(write_still=True)
