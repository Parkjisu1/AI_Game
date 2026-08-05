import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / 'projecthub-web' / '.env.production')
load_dotenv(Path.home() / '.hermes' / 'watcher' / '.env')
from pymongo import MongoClient
db = MongoClient(os.getenv('MONGODB_URI'))[os.getenv('MONGODB_DB','aigame')]

for c in ['hermes_team_scores', 'pixelforge_tasks', 'design_base', 'design_expert', 'code_base', 'code_expert']:
    has = db[c].count_documents({'embedding': {'$exists': True}})
    total = db[c].count_documents({})
    print(f'{c:25s} | embedded {has:>5} / {total:>5}')

d = db.hermes_team_scores.find_one({'embedding': {'$exists': True}})
if d:
    print(f"\nsample: dim={len(d['embedding'])} model={d.get('embedding_model')}")
