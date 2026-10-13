"""Diagnostic only: align total foreground height/center, then compare front views."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from scipy.ndimage import binary_fill_holes,gaussian_filter
root=Path(__file__).resolve().parents[2];public=root/'tools/projecthub-web/public/asset-studio'
def normalized(path,reference=False):
    image=Image.open(path).convert('RGBA');pixels=np.asarray(image)
    mask=binary_fill_holes(pixels[:,:,:3].min(2)<245) if reference else pixels[:,:,3]>127
    yy,xx=np.where(mask);box=(xx.min(),yy.min(),xx.max()+1,yy.max()+1)
    crop=image.crop(box);height=1400;width=round(crop.width*height/crop.height)
    crop=crop.resize((width,height),Image.Resampling.LANCZOS)
    alpha=Image.fromarray((mask*255).astype('uint8')).crop(box).resize((width,height),Image.Resampling.NEAREST)
    canvas=Image.new('RGB',(1400,1500),'white');canvas.paste(crop.convert('RGB'),((1400-width)//2,50))
    coverage=Image.new('L',canvas.size);coverage.paste(alpha,((1400-width)//2,50))
    return np.asarray(canvas,dtype=float)/255,np.asarray(coverage)>127
ref,refmask=normalized(public/'wind-ronin-front.png',True);results=[]
for version in ['v3','v4','v8','v17','v21','v26']:
    path=public/(version+'-front.png')
    if not path.exists():path=root/'output/asset-studio'/(version+'-front.png')
    rgb,mask=normalized(path);overlap=mask&refmask
    a=ref@np.array([.2126,.7152,.0722]);b=rgb@np.array([.2126,.7152,.0722])
    x=gaussian_filter(a,1.5);y=gaussian_filter(b,1.5)
    va=gaussian_filter(a*a,1.5)-x*x;vb=gaussian_filter(b*b,1.5)-y*y;cov=gaussian_filter(a*b,1.5)-x*y
    ssim=(2*x*y+.01**2)*(2*cov+.03**2)/((x*x+y*y+.01**2)*(va+vb+.03**2))
    results.append({'version':version,'silhouette_iou':float(overlap.sum()/(mask|refmask).sum()),'foreground_rgb_mae':float(abs(rgb-ref)[overlap].mean()),'foreground_ssim':float(ssim[overlap].mean())})
report={'scope':'Front only. Foreground crop aligned by total height and horizontal center. Includes added equipment; pose and camera differences remain. Not a quality percentage or art approval. Raw PNGs unchanged.','results':results,'art_approved':False}
(root/'output/asset-studio/v26-comparison-metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
