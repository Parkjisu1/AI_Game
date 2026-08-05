import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / 'projecthub-web' / '.env.production')
load_dotenv(Path.home() / '.hermes' / 'watcher' / '.env')
from pymongo import MongoClient
client = MongoClient(os.getenv('MONGODB_URI'))
db = client[os.getenv('MONGODB_DB','aigame')]

# List all search indexes across collections
total = 0
for c in db.list_collection_names():
    idxs = list(db[c].list_search_indexes())
    if idxs:
        for i in idxs:
            total += 1
            print(f"{c:30s} | {i.get('name'):20s} | {i.get('type','-'):15s} | {i.get('status','-')}")
print(f"\ntotal search indexes: {total}")
