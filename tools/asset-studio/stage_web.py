"""Prepare an isolated build from the live ProjectHub source; preserve unrelated work."""
from pathlib import Path
import shutil
import tarfile
import re
from datetime import datetime, timezone

root=Path('/home/aimed/projecthub-web')
stage=Path('/home/aimed/projecthub-3d/web-stage')
stage.mkdir(exist_ok=True)
shutil.copytree(root/'src',stage/'src',dirs_exist_ok=True)
for name in ['package.json','package-lock.json','next.config.ts','tsconfig.json','next-env.d.ts','postcss.config.mjs','eslint.config.mjs','.env.local','.env.production']:
    if (root/name).is_file(): shutil.copy2(root/name,stage/name)
if not (stage/'node_modules').exists(): (stage/'node_modules').symlink_to(root/'node_modules',target_is_directory=True)
with tarfile.open('/home/aimed/projecthub-3d/web-overlay.tar.gz') as archive:
    archive.extractall(stage,filter='data')
changes={
 'src/components/paper/Rail.tsx': ('      { href: "/gallery", label: "설계 갤러리", icon: "image" },', '      { href: "/assets-3d", label: "3D 제작실", icon: "palette" },'),
 'src/components/TopNav.tsx': ('  { href: "/gallery", label: "설계 갤러리", game: true },', '  { href: "/assets-3d", label: "3D 제작실", game: true },'),
 'src/components/InstrumentNav.tsx': ('    { href: "/gallery", label: "설계 갤러리" },', '    { href: "/assets-3d", label: "3D 제작실" },'),
 'src/app/layout.tsx': ('  { href: "/gallery", label: "디자인 갤러리", icon: "image" },', '  { href: "/assets-3d", label: "3D 제작실", icon: "palette" },'),
}
for rel,(needle,line) in changes.items():
    file=stage/rel
    text=file.read_text()
    if '/assets-3d' not in text:
        match=re.search(r'^.*href: "/gallery".*$',text,re.MULTILINE)
        if not match: raise RuntimeError(f'Navigation anchor missing: {rel}')
        original=match.group(0)
        insertion=re.sub(r'label: "[^"]+"','label: "3D 제작실"',original.replace('"/gallery"','"/assets-3d"'))
        file.write_text(text.replace(original,original+'\n'+insertion,1))
cfg=stage/'next.config.ts'
text=cfg.read_text()
needle='proxyClientMaxBodySize: 30 * 1024 * 1024'
if needle not in text and 'proxyClientMaxBodySize: 110 * 1024 * 1024' not in text: raise RuntimeError('Review upload proxy limit before build')
cfg.write_text(text.replace(needle,'proxyClientMaxBodySize: 110 * 1024 * 1024'))
text=cfg.read_text()
if 'source: "/asset-studio/:path*"' not in text:
    anchor='      { source: "/playable/:path*", headers: PLAYABLE_HEADERS },'
    if anchor not in text: raise RuntimeError('Review CSP header insertion')
    text=text.replace(anchor,anchor+'''\n      // GLB embedded textures are read through local blob URLs.
      { source: "/asset-studio/:path*", headers: SECURITY_HEADERS.map(h => h.key === "Content-Security-Policy"
        ? { ...h, value: h.value.replace("connect-src 'self'", "connect-src 'self' blob:") } : h) },''')
    cfg.write_text(text)
roles=stage/'src/app/api/agents/roles/route.ts'
roles.write_text(roles.read_text().replace('export const SUB_TEAMS:', 'const SUB_TEAMS:'))
print('Prepared isolated build',stage)
