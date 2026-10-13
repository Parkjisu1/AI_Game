"""Separate PSD composite decode from unsupported layer enumeration."""
import collections,json,pathlib
from PIL import Image,ImageOps
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';p=data/'art-assets.jsonl'
rows=[json.loads(x) for x in p.open(encoding='utf8')];recovered=[]
for a in rows:
 if a['extension']!='.psd':continue
 a['frames']=1;a['editable_structure_status']='layers_not_verified'
 if a['status']!='image_decode_failed':continue
 try:
  with Image.open(a['source_path']) as im:
   im.load();preview=ImageOps.exif_transpose(im).convert('RGBA');preview.thumbnail((512,512));name=a['source_hash']+'.png';preview.save(root/'previews'/name)
   a.update(width=im.width,height=im.height,mode=im.mode,format=im.format,has_alpha='A' in im.getbands(),status='image_decoded',preview=name,preview_kind='composite',previous_issue='Pillow PSD layer enumeration failed; composite decoded separately')
   a.pop('error_type',None);recovered.append(a['id'])
 except Exception as e:a['error_type']=type(e).__name__
tmp=p.with_suffix('.tmp')
with tmp.open('w',encoding='utf8') as f:
 for d in rows:f.write(json.dumps(d,ensure_ascii=False)+'\n')
tmp.replace(p)
s=data/'inventory-summary.json';v=json.loads(s.read_text());v['art_status']=dict(collections.Counter(x['status'] for x in rows));v['psd_composites_recovered']=len(recovered);v['psd_layers_verified']=False
encoding=json.loads((data/'encoding-recovery.json').read_text());v.update(code_source_files=encoding['source_files'],code_unresolved=encoding['unresolved'],code_status=dict(collections.Counter(x['status'] for x in json.loads((data/'code-gaps.json').read_text()))))
s.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8');(data/'psd-recheck.json').write_text(json.dumps({'recovered':recovered,'remaining':sum(x['status']=='image_decode_failed' for x in rows)}));print('PSD composites recovered',len(recovered))
