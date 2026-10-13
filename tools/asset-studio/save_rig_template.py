import bpy
bpy.ops.wm.open_mainfile(filepath='D:/ProjectHub3D/jobs/00000000000001a08526dee4/output/character.blend',use_scripts=False)
rig=bpy.data.objects['WindRonin_Rig']
bpy.data.libraries.write('D:/ProjectHub3D/pipeline/rig-template.blend',{rig},fake_user=True,compress=True)
print('RIG_TEMPLATE_SAVED')
