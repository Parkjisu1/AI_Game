"""Vector search smoke test on code_base."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / 'projecthub-web' / '.env.production')
load_dotenv(Path.home() / '.hermes' / 'watcher' / '.env')
from openai import OpenAI
from pymongo import MongoClient

db = MongoClient(os.getenv('MONGODB_URI'))[os.getenv('MONGODB_DB','aigame')]
oa = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

queries = [
    'ObjectPool 패턴 풍선 재사용',
    'Addressables 그룹 등록 라벨 부착',
    'UIShop ShopListItem 데이터 바인딩',
    'EventBus 이벤트 발행 구독 구조',
    '시즌패스 보상 테이블 적용',
]

for q in queries:
    print(f'\n=== Q: "{q}" ===')
    qvec = oa.embeddings.create(model='text-embedding-3-small', input=[q]).data[0].embedding
    pipe = [
        {'$vectorSearch': {
            'index': 'vector_index', 'path': 'embedding',
            'queryVector': qvec, 'numCandidates': 100, 'limit': 5,
        }},
        {'$project': {
            'className': 1, 'genre': 1, 'layer': 1, 'role': 1, 'system': 1, 'project': 1,
            'score': {'$meta': 'vectorSearchScore'},
        }},
    ]
    for r in db.code_base.aggregate(pipe):
        s = r.pop('score', 0); r.pop('_id', None)
        print(f'  [{s:.3f}] {r}')
