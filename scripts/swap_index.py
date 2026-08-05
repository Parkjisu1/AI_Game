"""Drop design_base vector index, create code_base vector index."""
import os, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / 'projecthub-web' / '.env.production')
load_dotenv(Path.home() / '.hermes' / 'watcher' / '.env')
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

db = MongoClient(os.getenv('MONGODB_URI'))[os.getenv('MONGODB_DB','aigame')]

print('Dropping design_base.vector_index...')
db.design_base.drop_search_index('vector_index')

# Wait for drop to complete (Atlas async)
for _ in range(60):
    idxs = list(db.design_base.list_search_indexes())
    if not any(i.get('name') == 'vector_index' for i in idxs):
        break
    time.sleep(2)
else:
    raise SystemExit('drop timed out')
print('  dropped.')

print('Creating code_base.vector_index...')
model = SearchIndexModel(
    definition={'fields': [{
        'type': 'vector',
        'path': 'embedding',
        'numDimensions': 1536,
        'similarity': 'cosine',
    }]},
    name='vector_index',
    type='vectorSearch',
)
result = db.code_base.create_search_index(model=model)
print(f'  created: {result}')

print('\nFinal index state:')
for c in db.list_collection_names():
    for i in db[c].list_search_indexes():
        print(f'  {c:25s} | {i.get("name"):15s} | {i.get("status","-")}')
