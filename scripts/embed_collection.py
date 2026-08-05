#!/usr/bin/env python3
"""
embed_collection.py — OpenAI text-embedding-3-small + Atlas Vector Search

Usage (on Mother):
    ~/.hermes/watcher/venv/bin/python scripts/embed_collection.py <collection> [--limit N] [--reembed]
    ~/.hermes/watcher/venv/bin/python scripts/embed_collection.py <collection> --create-index

Targets: hermes_team_scores, pixelforge_tasks, design_base, design_expert, code_base, code_expert
"""

import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient, UpdateOne
from pymongo.operations import SearchIndexModel

# Load env from both possible locations
for env_path in [
    Path.home() / 'projecthub-web' / '.env.production',
    Path.home() / '.hermes' / 'watcher' / '.env',
    Path(__file__).resolve().parent.parent / '.env',
]:
    if env_path.exists():
        load_dotenv(env_path, override=False)

MONGO_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
MONGO_DB = os.getenv('MONGODB_DB') or os.getenv('MONGO_DB_NAME') or 'aigame'
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not MONGO_URI or not OPENAI_API_KEY:
    sys.exit('Missing MONGO URI or OPENAI key in env')

EMBEDDING_MODEL = 'text-embedding-3-small'
EMBEDDING_DIM = 1536
BATCH_SIZE = 100
MAX_TEXT_CHARS = 8000

mongo = MongoClient(MONGO_URI)
db = mongo[MONGO_DB]
oa = OpenAI(api_key=OPENAI_API_KEY)


# ---------- Per-collection text builders ----------

def _trunc(s, n=MAX_TEXT_CHARS):
    return (s or '')[:n]


def _join(*parts, sep=' | '):
    return sep.join(p for p in (str(x).strip() for x in parts if x is not None) if p)


def build_text_score(doc):
    return _trunc(_join(
        f"role:{doc.get('role','')}",
        f"team:{doc.get('team','')}/{doc.get('sub_team','')}",
        f"verdict:{doc.get('verdict','')}",
        f"score:{doc.get('score','')}",
        doc.get('summary', ''),
    ))


def build_text_task(doc):
    desc = doc.get('description', '') or ''
    if isinstance(desc, dict):
        desc = desc.get('text') or str(desc)
    comments = doc.get('comments') or []
    # 사용자 코멘트 우선 — author != 'hermes' 인 것이 실제 사용자 요청/거부 사유
    user_comments = [c for c in comments if isinstance(c, dict) and c.get('author') != 'hermes']
    user_text = ' /// '.join(
        (c.get('text') or c.get('content') or c.get('body') or '').strip()
        for c in user_comments
    )[:3000]
    return _trunc(_join(
        f"team:{doc.get('team','')}/{doc.get('sub_team','')}",
        f"status:{doc.get('status','')}",
        f"title:{doc.get('title','')}",
        desc[:2000] if isinstance(desc, str) else '',
        f"user_requests:{user_text}",
    ))


def build_text_design(doc):
    provides = ', '.join(doc.get('provides', []) or [])[:500]
    requires = ', '.join(doc.get('requires', []) or [])[:500]
    analysis = doc.get('design_analysis') or {}
    intent = analysis.get('design_intent', '') if isinstance(analysis, dict) else ''
    return _trunc(_join(
        f"genre:{doc.get('genre','')}",
        f"domain:{doc.get('domain','')}",
        f"system:{doc.get('system','')}",
        f"data_type:{doc.get('data_type','')}",
        f"provides:{provides}",
        f"requires:{requires}",
        f"intent:{intent}",
    ))


def build_text_code(doc):
    # 클래스 시그니처 (className : baseClass, interfaces)
    cls_parts = []
    for c in (doc.get('classes') or [])[:3]:
        if not isinstance(c, dict):
            continue
        name = c.get('className', '')
        base = c.get('baseClass', '')
        ifaces = ', '.join(c.get('interfaces', []) or [])
        sig = name + (f" : {base}" if base else "") + (f", {ifaces}" if ifaces else "")
        if sig.strip():
            cls_parts.append(sig)
    classes_str = '; '.join(cls_parts)

    # provides/requires/uses 는 top-level (contract 아님)
    provides = ', '.join((doc.get('provides') or [])[:12])[:600]
    requires = ', '.join((doc.get('requires') or [])[:10])[:300]
    uses = ', '.join((doc.get('uses') or [])[:15])[:400]
    tags = ', '.join(doc.get('tags', []) or [])
    recipe = doc.get('recipe') or {}
    recipe_cat = recipe.get('category', '') if isinstance(recipe, dict) else ''
    usage = recipe.get('typical_usage', '') if isinstance(recipe, dict) else ''

    return _trunc(_join(
        f"class:{classes_str}",
        f"genre:{doc.get('genre','')}",
        f"layer:{doc.get('layer','')}",
        f"role:{doc.get('role','')}",
        f"system:{doc.get('system','')}",
        f"recipe:{recipe_cat}",
        f"file:{doc.get('filePath','')}",
        f"provides:{provides}",
        f"requires:{requires}",
        f"uses:{uses}",
        f"tags:{tags}",
        f"usage:{usage[:300]}",
    ))


def build_text_unity_config(doc):
    rect = doc.get('rect_transform') or {}
    scripts = doc.get('custom_scripts') or []
    canvas = doc.get('canvas') or {}
    return _trunc(_join(
        f"project:{doc.get('project','')}",
        f"genre:{doc.get('genre','')}",
        f"kind:{doc.get('kind','')}",
        f"name:{doc.get('name','') or doc.get('file_name','')}",
        f"file:{doc.get('file_path','')}",
        f"object_count:{doc.get('object_count', doc.get('objects_count',''))}",
        f"ui_count:{doc.get('ui_count','')}",
        f"scripts:{', '.join((s.get('class') if isinstance(s, dict) else str(s)) for s in scripts)[:300]}",
        f"rect:{str(rect)[:300]}",
        f"canvas:{str(canvas)[:200]}",
    ))


def build_text_art_asset(doc):
    return _trunc(_join(
        f"project:{doc.get('project','')}",
        f"kind:{doc.get('kind','')}",
        f"source:{doc.get('source','')}",
        f"file:{doc.get('file_name','')}",
        f"folder:{doc.get('folder','')}",
        f"tags:{', '.join(doc.get('tags', []) or [])}",
        f"ext:{doc.get('ext','')}",
    ))


def build_text_level_backup(doc):
    return _trunc(_join(
        f"project:{doc.get('project','')}",
        f"backup:{doc.get('backupId','')}",
        f"timestamp:{doc.get('timestamp','')}",
        f"levels:{doc.get('level_count','')}",
        f"schema:{', '.join(doc.get('schema_keys', []) or [])}",
    ))


COLLECTION_BUILDERS = {
    'hermes_team_scores': build_text_score,
    'pixelforge_tasks': build_text_task,
    'design_base': build_text_design,
    'design_expert': build_text_design,
    'code_base': build_text_code,
    'code_expert': build_text_code,
    'unity_configs': build_text_unity_config,
    'art_assets': build_text_art_asset,
    'level_backups': build_text_level_backup,
}


# ---------- Embedding ----------

def embed_batch(texts):
    """Embed up to 100 texts. Retries on transient errors."""
    for attempt in range(3):
        try:
            resp = oa.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"  embed err: {e!s:.100}; retry in {wait}s")
            time.sleep(wait)


def run_embed(collection_name, limit=None, reembed=False, min_best_score=None):
    if collection_name not in COLLECTION_BUILDERS:
        sys.exit(f"Unknown collection: {collection_name}")
    builder = COLLECTION_BUILDERS[collection_name]
    coll = db[collection_name]

    query = {} if reembed else {'embedding': {'$exists': False}}
    if min_best_score is not None:
        # 좋은 결과만 임베딩 — 나쁜(실패/거부/차단/저득점) 결과를 RAG 참조로 학습 방지
        query['best_score'] = {'$gte': min_best_score}
    total_to_do = coll.count_documents(query)
    if limit:
        total_to_do = min(total_to_do, limit)
    print(f"[{collection_name}] target docs: {total_to_do}")
    if total_to_do == 0:
        return

    cursor = coll.find(query, batch_size=BATCH_SIZE)
    if limit:
        cursor = cursor.limit(limit)

    batch = []
    done = 0
    started = time.time()
    embedded_at = datetime.now(timezone.utc).isoformat()

    for doc in cursor:
        text = builder(doc)
        if not text or len(text) < 5:
            continue
        batch.append((doc['_id'], text))

        if len(batch) >= BATCH_SIZE:
            done += _flush_batch(coll, batch, embedded_at)
            batch.clear()
            elapsed = time.time() - started
            rate = done / elapsed if elapsed else 0
            print(f"  {done}/{total_to_do}  rate={rate:.1f}/s")

    if batch:
        done += _flush_batch(coll, batch, embedded_at)

    print(f"[{collection_name}] done: {done} embedded in {time.time()-started:.1f}s")


def _flush_batch(coll, batch, embedded_at):
    ids = [b[0] for b in batch]
    texts = [b[1] for b in batch]
    embs = embed_batch(texts)
    ops = [
        UpdateOne(
            {'_id': _id},
            {'$set': {
                'embedding': emb,
                'embedding_model': EMBEDDING_MODEL,
                'embedded_at': embedded_at,
            }}
        )
        for _id, emb in zip(ids, embs)
    ]
    coll.bulk_write(ops, ordered=False)
    return len(ops)


# ---------- Vector index ----------

def create_vector_index(collection_name, index_name='vector_index'):
    coll = db[collection_name]
    existing = list(coll.list_search_indexes())
    if any(i.get('name') == index_name for i in existing):
        print(f"[{collection_name}] index {index_name} already exists")
        return

    model = SearchIndexModel(
        definition={
            'fields': [{
                'type': 'vector',
                'path': 'embedding',
                'numDimensions': EMBEDDING_DIM,
                'similarity': 'cosine',
            }]
        },
        name=index_name,
        type='vectorSearch',
    )
    result = coll.create_search_index(model=model)
    print(f"[{collection_name}] vector index created: {result}")


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('collection', help='Collection name (or "all")')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--reembed', action='store_true', help='Re-embed even if embedding exists')
    ap.add_argument('--create-index', action='store_true', help='Create vector index instead of embedding')
    ap.add_argument('--min-best-score', type=int, default=None, help='best_score>=N 문서만 임베딩 (좋은 결과만)')
    args = ap.parse_args()

    targets = list(COLLECTION_BUILDERS.keys()) if args.collection == 'all' else [args.collection]

    for c in targets:
        if args.create_index:
            create_vector_index(c)
        else:
            run_embed(c, limit=args.limit, reembed=args.reembed, min_best_score=args.min_best_score)


if __name__ == '__main__':
    main()
