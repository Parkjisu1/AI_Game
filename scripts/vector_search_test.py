#!/usr/bin/env python3
"""Quick vector search smoke test on existing indexes."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / 'projecthub-web' / '.env.production')
load_dotenv(Path.home() / '.hermes' / 'watcher' / '.env')

from openai import OpenAI
from pymongo import MongoClient

client = MongoClient(os.getenv('MONGODB_URI'))
db = client[os.getenv('MONGODB_DB','aigame')]
oa = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def search(coll_name, query_text, k=5, projection=None):
    qvec = oa.embeddings.create(model='text-embedding-3-small', input=[query_text]).data[0].embedding
    pipeline = [
        {'$vectorSearch': {
            'index': 'vector_index',
            'path': 'embedding',
            'queryVector': qvec,
            'numCandidates': 50,
            'limit': k,
        }},
        {'$project': {**(projection or {}), 'score': {'$meta': 'vectorSearchScore'}}},
    ]
    return list(db[coll_name].aggregate(pipeline))


queries = [
    ('hermes_team_scores', 'UIShop 구조 변경에서 사용자가 거부한 이유',
     {'role': 1, 'verdict': 1, 'summary': 1, 'task_id': 1}),
    ('pixelforge_tasks', '풍선 프리팹 신규 생성 + Addressables 등록',
     {'title': 1, 'team': 1, 'sub_team': 1, 'status': 1}),
    ('pixelforge_tasks', 'UIShop ShopListItem 리소스 교체',
     {'title': 1, 'status': 1}),
    ('design_base', '시즌패스 30단계 보상 곡선 설계',
     {'system': 1, 'genre': 1, 'domain': 1, 'project': 1}),
]

for coll, q, proj in queries:
    print(f'\n=== {coll} ===\nQ: "{q}"')
    try:
        results = search(coll, q, k=5, projection=proj)
        for r in results:
            score = r.pop('score', 0)
            r.pop('_id', None)
            print(f'  [{score:.3f}] {r}')
    except Exception as e:
        print(f'  ERR: {e}')
