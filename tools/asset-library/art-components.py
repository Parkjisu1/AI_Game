"""Unity sprite subassets: exact importer rectangles, IDs and serialized uses."""
import collections,functools,hashlib,json,pathlib,re,uuid,yaml
from PIL import Image
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data'
parents=[json.loads(x) for x in (data/'art-assets.jsonl').open(encoding='utf8')]
parts=[];issues=[]
@functools.lru_cache(maxsize=24)
def lines(path):return pathlib.Path(path).read_text(encoding='utf-8-sig').splitlines()
for a in parents:
 if a.get('import_settings',{}).get('spriteMode')!='2' or a['status']!='image_decoded':continue
 meta=pathlib.Path(a['source_path']+'.meta')
 try:
  raw=meta.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=a['meta_hash']:raise ValueError('Source metadata changed')
  doc=yaml.safe_load(raw.decode('utf-8-sig'))['TextureImporter'];sprites=doc.get('spriteSheet',{}).get('sprites',[])
  if not sprites:issues.append({'parent_id':a['id'],'status':'no_sprite_rectangles_in_importer'});continue
  with Image.open(a['source_path']) as image:
   image.load()
   for s in sprites:
    r=s.get('rect',{});x,y,w,h=(int(r[k]) for k in ['x','y','width','height'])
    internal=s.get('internalID');name=str(s.get('name','unnamed'))
    if not internal:
     choices=[k for k,v in (doc.get('fileIDToRecycleName') or {}).items() if v==name]
     if len(choices)==1:internal=choices[0]
    identity=str(uuid.uuid5(uuid.NAMESPACE_URL,'sprite:'+a['id']+':'+str(internal)+':'+name+':'+json.dumps(r,sort_keys=True)))
    c={k:v for k,v in a.items() if k not in ['id','name','preview','uses','width','height','kind','error_type']}
    c.update(id=identity,parent_id=a['id'],name=name,kind='sprite_subasset',source_asset_name=a['name'],width=w,height=h,rect=r,pivot=s.get('pivot'),border=s.get('border'),internal_file_id=internal,sprite_id=s.get('spriteID'),component_evidence='Unity TextureImporter spriteSheet',uses=[],preview=None,preview_kind='sprite_rectangle',runtime_verified=False)
    if min(x,y,w,h)<0 or w==0 or h==0 or x+w>image.width or y+h>image.height:c['status']='sprite_rect_out_of_bounds'
    else:
     # Unity rectangle coordinates start at the bottom-left; image decode starts at top-left.
     crop=image.crop((x,image.height-y-h,x+w,image.height-y)).convert('RGBA');crop.thumbnail((512,512));name=identity+'.png';crop.save(root/'previews'/name);c['preview']=name
    if internal is not None:
     for u in a['uses']:
      try:line=lines(u['file'])[u['line']-1]
      except (OSError,UnicodeError,IndexError):continue
      if any(m.group(1)==str(internal) and m.group(2)==a.get('guid') for m in re.finditer(r'\{\s*fileID:\s*(-?\d+),\s*guid:\s*([a-f0-9]{32})',line)):
       c['uses'].append({**u,'file_id':internal,'resolution':'exact_guid_and_file_id'})
    c['usage_status']='references_found' if c['uses'] else 'no_exact_subasset_reference_found';parts.append(c)
 except Exception as e:issues.append({'parent_id':a['id'],'status':'component_extraction_failed','error_type':type(e).__name__})
 if len(parts)%100<20:print('sprite components',len(parts),flush=True)
p=data/'art-components.jsonl';tmp=p.with_suffix('.tmp')
with tmp.open('w',encoding='utf8') as f:
 for c in parts:f.write(json.dumps(c,ensure_ascii=False)+'\n')
tmp.replace(p)
summary={'sprite_sheets':sum(x.get('import_settings',{}).get('spriteMode')=='2' for x in parents),'components':len(parts),'status':dict(collections.Counter(x['status'] for x in parts)),'with_exact_uses':sum(bool(x['uses']) for x in parts),'issues':issues,'coverage':'Unity sprites only; PSD layers, mesh pieces and Spine internal animation units unverified'}
(data/'art-components-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in summary.items() if k!='issues'}),flush=True)
