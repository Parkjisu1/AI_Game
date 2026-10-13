"""Restore only hash-verified catalog snapshots; never modify source games or vectors.

Reuses archive-sources.py's sources/<sha256> layout and the Hub's eligibility
rules. The archive is read as data; paths and links are never extracted.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tarfile
import time
import uuid

HEX = re.compile(r'^[a-f0-9]{64}$')
LIMIT = 32 * 1024**2


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    global LIMIT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--max-source-mib', type=int, default=32)
    parser.add_argument('--only-hashes', type=Path)
    parser.add_argument('--source-first', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_source_mib <= 512: raise SystemExit('Source limit must be 1..512 MiB')
    LIMIT = args.max_source_mib * 1024**2
    selected = {r['sha256'] for r in json.loads(args.only_hashes.read_text(encoding='utf8'))} if args.only_hashes else None
    root, out = args.root.resolve(), args.out.resolve()
    workspace = Path('E:/AI').resolve()
    if not root.is_relative_to(workspace) or not out.is_relative_to(workspace):
        raise SystemExit('Writes must remain inside E:/AI')
    cache = root / 'sources'
    for p in [root, out, cache]:
        if any(x.is_symlink() or x.is_junction() for x in [p, *p.parents]):
            raise SystemExit('Reparse path refused')
    out.mkdir(parents=True, exist_ok=False)
    records, objects = [], {}
    excluded = collections.Counter()
    content_bad = []
    with sqlite3.connect((root / 'catalog.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        for uid, domain, project, raw in db.execute('SELECT id,domain,project,data FROM assets'):
            d = json.loads(raw)
            h = d.get('source_hash', '')
            if selected is not None and h not in selected:
                continue
            if (domain not in ('code', 'art') or not HEX.fullmatch(h) or d.get('source_scope') == 'historical'
                    or d.get('status') in ('historical_source_recovered', 'source_missing', 'sprite_rect_out_of_bounds')
                    or domain == 'code' and d.get('status') != 'parsed'):
                excluded[domain + ':' + str(d.get('status'))] += 1
                continue
            if domain == 'code' and hashlib.sha256(d.get('content', '').encode()).hexdigest() != d.get('content_hash'):
                content_bad.append(uid)
            obj = objects.setdefault(h, {'hash': h, 'aliases': {h}, 'sources': set(), 'state': 'missing'})
            if domain == 'code':
                obj['aliases'].add(h + '.original')
                name = Path(d.get('original_archive_path') or d.get('archive_path', '')).name
                if name.startswith(h + '.') and re.fullmatch(r'[a-f0-9]{64}\.[a-zA-Z0-9._-]+', name):
                    obj['aliases'].add(name)
            for k in ['original_archive_path', 'archive_path', 'source_path']:
                if d.get(k):
                    obj['sources'].add(d[k])
            records.append({'id': uid, 'domain': domain, 'project': project, 'sourceHash': h,
                            'sourcePath': d.get('source_path')})
    for obj in objects.values():
        for name in sorted(obj['aliases']):
            p = cache / name
            if p.is_file() and not p.is_symlink() and p.stat().st_size <= LIMIT:
                if digest(p) == obj['hash']:
                    obj['state'] = 'already_verified'
                    break
                obj['cacheMismatch'] = True
    needed = {h for h, obj in objects.items() if obj['state'] == 'missing'}
    initial_missing = len(needed)
    restored, restored_bytes = [], 0
    failures = []

    def install(h, raw, source):
        nonlocal restored_bytes
        if len(raw) > LIMIT or hashlib.sha256(raw).hexdigest() != h:
            failures.append({'hash': h, 'reason': 'candidate_hash_mismatch', 'source': source})
            return
        if not args.apply:
            objects[h]['state'] = 'recoverable'
            needed.discard(h)
            return
        target = cache / h
        if target.exists():
            if digest(target) != h:
                failures.append({'hash': h, 'reason': 'existing_cache_not_overwritten'})
                return
            objects[h]['state'] = 'already_verified'
        else:
            if shutil.disk_usage(cache).free < len(raw) + 1024**3:
                raise RuntimeError('Insufficient disk reserve')
            temporary = cache / (h + '.' + uuid.uuid4().hex + '.partial')
            with temporary.open('xb') as stream:
                stream.write(raw)
            if digest(temporary) != h:
                raise RuntimeError('Written snapshot hash mismatch')
            temporary.rename(target)  # Windows refuses an existing destination.
            objects[h]['state'] = 'restored_verified'
            restored.append({'sha256': h, 'bytes': len(raw), 'from': source})
            restored_bytes += len(raw)
        needed.discard(h)

    print(json.dumps({'eligibleUnits': len(records), 'uniqueHashes': len(objects), 'missingBefore': initial_missing}), flush=True)
    if args.source_first:
        for h in list(needed):
            for source in sorted(objects[h]['sources']):
                p = Path(source)
                if p.is_file() and not p.is_symlink() and p.stat().st_size <= LIMIT:
                    install(h, p.read_bytes(), source)
                    if h not in needed: break
    archive = root / 'source-artifacts.tar'
    if archive.is_file() and needed:
        with tarfile.open(archive, mode='r|') as tar:
            for member in tar:
                if not member.isfile() or not member.name.startswith('sources/'):
                    continue
                h = member.name[len('sources/'):]
                if h not in needed or not HEX.fullmatch(h) or member.size > LIMIT:
                    continue
                stream = tar.extractfile(member)
                if stream is not None:
                    install(h, stream.read(LIMIT + 1), 'source-artifacts.tar:' + member.name)
                if len(restored) and len(restored) % 3000 == 0:
                    print(json.dumps({'restored': len(restored), 'bytes': restored_bytes, 'remaining': len(needed)}), flush=True)
    for h in list(needed):
        for source in sorted(objects[h]['sources']):
            p = Path(source)
            if p.is_file() and not p.is_symlink() and p.stat().st_size <= LIMIT:
                install(h, p.read_bytes(), source)
                if h not in needed:
                    break
    # Record current-file drift separately from preserved snapshot availability.
    current = {}
    for r in records:
        key = (r['sourcePath'], r['sourceHash'])
        if key not in current:
            p = Path(r['sourcePath']) if r['sourcePath'] else None
            if p is None or not p.is_file():
                state = 'missing'
            elif p.stat().st_size > LIMIT:
                state = 'over_read_limit'
            else:
                state = 'match' if digest(p) == r['sourceHash'] else 'changed'
            current[key] = state
        r['snapshot'] = objects[r['sourceHash']]['state']
        r['currentSource'] = current[key]
    counts = collections.Counter(r['snapshot'] for r in records)
    drift = [{'sourcePath': p, 'sourceHash': h, 'current': state} for (p, h), state in current.items() if state != 'match']
    summary = {'applied': args.apply, 'eligibleUnits': len(records), 'uniqueHashes': len(objects),
               'missingBefore': initial_missing, 'restoredFiles': len(restored), 'restoredBytes': restored_bytes,
               'unresolvedHashes': len(needed), 'unitStates': dict(counts), 'currentDriftFiles': len(drift),
               'codeContentHashMismatches': len(content_bad), 'excludedUnits': dict(excluded),
               'vectorsModified': False, 'catalogModified': False, 'semanticSearchExecuted': False,
               'sourceGamesModified': False, 'at': time.time()}
    summary['sourceLimitMiB'] = args.max_source_mib
    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    save('summary.json', summary)
    save('restored.json', restored)
    save('units.json', records)
    save('reindex-candidates.json', {'meaning': 'Review changed/missing current files before reindexing. Restored snapshots are not declared current.', 'files': drift, 'badCodeUnitIds': content_bad})
    save('unresolved.json', [{'sha256': h, 'candidatePaths': sorted(objects[h]['sources'])} for h in sorted(needed)])
    save('candidate-failures.json', failures)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
