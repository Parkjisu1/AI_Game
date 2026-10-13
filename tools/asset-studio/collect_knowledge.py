"""Bounded public-source metadata collection and explicit source-note indexing.

Does not claim whole-platform coverage, video transcription, or paywall access.
"""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import uuid

class Headings(HTMLParser):
    def __init__(self):
        super().__init__(); self.capture=False; self.items=[]
    def handle_starttag(self, tag, attrs):
        if tag in ('title','h1','h2','h3'): self.capture=True
    def handle_endtag(self, tag):
        if tag in ('title','h1','h2','h3'): self.capture=False
    def handle_data(self, data):
        if self.capture and data.strip(): self.items.append(data.strip())

def request(url, body=None):
    headers={'User-Agent':'ProjectHubResearch/1.0 (public documentation metadata)', 'Content-Type':'application/json'}
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=25) as res:
        return res.read(2_000_000),res.status,res.url

def collect(items):
    robots={}
    for item in items:
        parsed=urllib.parse.urlparse(item['url'])
        site=parsed.scheme+'://'+parsed.netloc
        record={**item,'checked_at':datetime.now(timezone.utc).isoformat()}
        try:
            if site not in robots:
                parser=urllib.robotparser.RobotFileParser()
                try:
                    raw,_,_=request(site+'/robots.txt')
                    parser.parse(raw.decode('utf8',errors='replace').splitlines())
                except urllib.error.HTTPError as e:
                    if e.code==404: parser.parse([])
                    else: raise
                robots[site]=parser
            if not robots[site].can_fetch('ProjectHubResearch',item['url']):
                record['fetch_status']='robots_disallowed'
            else:
                raw,status,final_url=request(item['url'])
                parser=Headings();parser.feed(raw.decode('utf8',errors='replace'))
                record.update(fetch_status='metadata_fetched',http_status=status,final_url=final_url,
                              headings=parser.items[:20])
        except Exception as error:
            record.update(fetch_status='unavailable',fetch_error=str(error)[:200])
        yield record
        time.sleep(.5)

def index(items):
    base='http://127.0.0.1:6333/collections/projecthub_3d_knowledge'
    try: request(base)
    except urllib.error.HTTPError as e:
        if e.code!=404: raise
        req=urllib.request.Request(base,data=json.dumps({'vectors':{'size':768,'distance':'Cosine'}}).encode(),
                                   headers={'Content-Type':'application/json'},method='PUT')
        urllib.request.urlopen(req,timeout=20).read()
    count=0
    for item in items:
        text='search_document: '+item['title']+'\n'+item['summary']
        raw,_,_=request('http://100.87.87.59:11434/api/embed',{'model':'nomic-embed-text','input':text})
        vector=json.loads(raw)['embeddings'][0]
        if len(vector)!=768: raise RuntimeError('Embedding dimension mismatch')
        payload={k:item[k] for k in ['title','url','language','region','evidence','summary','fetch_status']}
        data={'points':[{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,item['url'])),'vector':vector,'payload':payload}]}
        req=urllib.request.Request(base+'/points?wait=true',data=json.dumps(data).encode(),
                                   headers={'Content-Type':'application/json'},method='PUT')
        urllib.request.urlopen(req,timeout=25).read();count+=1
    return count

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--index',action='store_true');args=parser.parse_args()
    root=Path(__file__).parent
    items=json.loads((root/'sources.json').read_text(encoding='utf8'))
    records=[]
    for record in collect(items):
        records.append(record)
        print(record['id'],record['fetch_status'],flush=True)
    result={'scope':'14 curated public source leads; not exhaustive; no video transcription',
            'sources':records,'indexed':index(records) if args.index else 0}
    (root/'research-evidence.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    print('Indexed',result['indexed'],flush=True)
