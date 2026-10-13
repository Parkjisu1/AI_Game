"""Measure frontal silhouette/color differences; these numbers do not approve 3D art quality."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from scipy.ndimage import binary_fill_holes,gaussian_filter
root=Path('C:/ProjectHub3D/cache/style-iteration')
reference=Image.open('D:/ProjectHub3D/references/wind-ronin-front.png').convert('RGB')
ref=np.asarray(reference,dtype=float)/255
ref_mask=binary_fill_holes(ref.min(axis=2)<.96)
results=[]
for version,file in [('v3',root/'pbr-front.png'),('v4',root/'v4/front.png')]:
    image=Image.open(file).convert('RGBA').resize(reference.size,Image.Resampling.LANCZOS)
    values=np.asarray(image,dtype=float)/255;mask=values[:,:,3]>.5;overlap=mask&ref_mask
    rgb=values[:,:,:3]
    mae=float(abs(rgb-ref)[overlap].mean())
    ref_y=ref@np.array([.2126,.7152,.0722]);actual_y=rgb@np.array([.2126,.7152,.0722])
    mx=gaussian_filter(ref_y,1.5);my=gaussian_filter(actual_y,1.5)
    vx=gaussian_filter(ref_y**2,1.5)-mx**2;vy=gaussian_filter(actual_y**2,1.5)-my**2
    cov=gaussian_filter(ref_y*actual_y,1.5)-mx*my
    ssim=(2*mx*my+.01**2)*(2*cov+.03**2)/((mx**2+my**2+.01**2)*(vx+vy+.03**2))
    results.append({'version':version,'silhouette_iou':float(overlap.sum()/(mask|ref_mask).sum()),
        'foreground_rgb_mae_0_to_1':mae,'foreground_luminance_ssim':float(ssim[overlap].mean())})
report={'scope':'Front view only, matching aspect and camera scale; no pose or nonrigid registration. Not final art approval.',
    'reference':'wind-ronin-front.png','results':results,'art_approved':False}
(root/'comparison-metrics.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
