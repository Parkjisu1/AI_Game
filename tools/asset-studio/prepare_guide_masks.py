"""Build foreground confidence and nearest-interior indices for UV baking."""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion,distance_transform_edt
root=Path('D:/ProjectHub3D/references')
for key in ['front','back','left','right']:
    rgb=np.asarray(Image.open(root/f'texture-guide-{key}-v8.png').convert('RGB'))[::-1].copy()
    mask=binary_erosion(rgb.min(axis=2)<217,iterations=5)
    nearest=distance_transform_edt(~mask,return_distances=False,return_indices=True)
    np.savez_compressed(root/f'guide-mask-{key}.npz',mask=mask,nearest=nearest.astype(np.int16))
    print('GUIDE_MASK',key,int(mask.sum()),flush=True)
