import hashlib,json,pathlib,tarfile
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';rows=[json.loads(x) for x in (data/'source-recovery.jsonl').open(encoding='utf8')]
paths=set((root/'source-recovery-20261005'/'sources').glob('*'))
paths.update(root/'previews'/x['preview'] for x in rows if x.get('preview'))
paths.update(data/x for x in ['source-recovery.jsonl','source-recovery-summary.json','source-recovery-validation.json','source-resolver-validation.json','catalog-before-source-recovery-20261005.jsonl'])
paths.add(root/'SOURCE-RECOVERY.html');archive=root/'source-recovery-20261005.tar'
with tarfile.open(archive,'w') as tar:
 for p in sorted(paths):tar.add(p,arcname=p.relative_to(root).as_posix(),recursive=False)
sha=hashlib.sha256(archive.read_bytes()).hexdigest();report={'archive':str(archive),'sha256':sha,'files':len(paths),'bytes':archive.stat().st_size}
(data/'source-recovery-backup.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
