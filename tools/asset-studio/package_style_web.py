from pathlib import Path
import tarfile,shutil,json
root=Path(__file__).resolve().parents[2];web=root/'tools/projecthub-web';studio=root/'tools/asset-studio'
shutil.copy2(studio/'WORKFLOW.ko.md',web/'public/asset-studio/workflow.md')
shutil.copy2(studio/'STYLE_ITERATIONS.ko.md',web/'public/asset-studio/STYLE_ITERATIONS.ko.md')
with tarfile.open(studio/'web-overlay.tar.gz','w:gz') as archive:
    for rel in ['src/app/assets-3d/page.tsx','public/asset-studio']:
        archive.add(web/rel,arcname=rel)
provenance=studio/'TRELLIS2_MODEL_PROVENANCE.json'
doc=json.loads(provenance.read_text());doc.update({'code_repository':'https://github.com/IgorAherne/TRELLIS.2-stableprojectorz','code_commit':'d5d38f1e033a881e2c00e3137822ef8aa4e193de','official_repository':'https://github.com/microsoft/TRELLIS.2','runtime':'Build Windows Python 3.11.9, torch 2.8.0+cu128, xformers 0.0.32.post2','resolution':1024,'seed':42,'art_approved':False})
provenance.write_text(json.dumps(doc,indent=2),encoding='utf-8')
print('Packaged style page and static assets')
