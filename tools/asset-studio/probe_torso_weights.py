import bpy,collections,json
bpy.ops.wm.open_mainfile(filepath='C:/ProjectHub3D/cache/style-iteration/v28/prepared.blend',load_ui=False,use_scripts=False)
obj=bpy.data.objects['WindRonin_LOD0'];counts=collections.Counter();examples=[]
for v in obj.data.vertices:
    if abs(v.co.x)<.19 and 1.05<v.co.z<1.4:
        groups=[(obj.vertex_groups[g.group].name,round(g.weight,3)) for g in v.groups if g.weight>.05]
        bad=[(name,w) for name,w in groups if name.startswith(('thigh','hand','forearm','upper_arm','finger','shin','foot'))]
        if bad:
            counts.update(name for name,w in bad)
            if len(examples)<10:examples.append({'xyz':list(v.co),'groups':groups})
print('TORSO_WEIGHT_AUDIT',json.dumps({'counts':dict(counts),'examples':examples}))
