import hashlib,json,pathlib,uuid
data=pathlib.Path('E:/AI/output/asset-library-v2/data');sources=data.parent/'sources'
rows=[json.loads(x) for x in (data/'code-files.jsonl').read_text(encoding='utf8').splitlines()]
gaps=json.loads((data/'code-gaps.json').read_text(encoding='utf8'));remaining=[];recovered=0
for d in gaps:
 if d['status']!='encoding_unverified':remaining.append(d);continue
 raw=pathlib.Path(d['source_path']).read_bytes();encoding='utf-16' if raw[:2] in [b'\xff\xfe',b'\xfe\xff'] else 'cp949'
 try:
  text=raw.decode(encoding)
  if text.encode(encoding)!=raw:raise ValueError('Roundtrip mismatch')
 except (UnicodeError,ValueError):remaining.append(d);continue
 sha=hashlib.sha256(raw).hexdigest();original=sources/(sha+'.original');original.write_bytes(raw)
 normalized=sources/(sha+'.utf8.cs');normalized.write_text(text,encoding='utf8',newline='')
 d.update(source_hash=sha,archive_path=str(normalized),original_archive_path=str(original),encoding=encoding,encoding_evidence='BOM' if encoding=='utf-16' else 'strict_cp949_roundtrip; comments require language review',id=str(uuid.uuid5(uuid.NAMESPACE_URL,'asset-library-v2:'+'|'.join([d['project'],d['source_path'],sha]))),status='source_preserved')
 rows.append(d);recovered+=1
with (data/'code-files.jsonl').open('w',encoding='utf8') as f:
 for d in rows:f.write(json.dumps(d,ensure_ascii=False)+'\n')
(data/'code-gaps.json').write_text(json.dumps(remaining,ensure_ascii=False,indent=2),encoding='utf8')
(data/'encoding-recovery.json').write_text(json.dumps({'recovered':recovered,'unresolved':len(remaining),'source_files':len(rows)}),encoding='utf8')
print('recovered',recovered,'source files',len(rows),'remaining',len(remaining))
