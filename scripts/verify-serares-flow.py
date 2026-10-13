"""Run the existing Serares 2D build through real mouse/touch input, locally.
No game source edits. Canvas text observation is read-only; seeded randomness
and external-navigation interception are explicitly recorded test conditions.
"""
import argparse
import hashlib
import json
import re
import uuid
from html.parser import HTMLParser
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'projects/SeraresPlayable'
HTML = PROJECT / 'output/playable.html'
SOURCE = PROJECT / 'build/game.js'
INIT = r"""(() => {
 let seed = 20261006;
 Math.random = () => { seed = (Math.imul(seed,1664525)+1013904223)>>>0; return seed/4294967296; };
 window.__flow = {texts:[], opens:[], images:[], seed:20261006};
 const fill = CanvasRenderingContext2D.prototype.fillText;
 CanvasRenderingContext2D.prototype.fillText = function(text,x,y,...rest) {
   window.__flow.texts.push({text:String(text),x,y}); return fill.call(this,text,x,y,...rest);
 };
 const clear = CanvasRenderingContext2D.prototype.clearRect;
 CanvasRenderingContext2D.prototype.clearRect = function(...args) {
   window.__flow.texts=[]; return clear.apply(this,args);
 };
 const OriginalImage = window.Image;
 window.Image = function(...args) { const im=new OriginalImage(...args); window.__flow.images.push(im); return im; };
 window.Image.prototype = OriginalImage.prototype;
 window.open = (url,target) => { window.__flow.opens.push({url,target}); return null; };
 window.mraid = {open:(url)=>window.__flow.opens.push({url,method:'mraid'})};
})();"""

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.inside=False; self.values=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script': self.inside=True; self.values.append('')
    def handle_endtag(self,tag):
        if tag=='script': self.inside=False
    def handle_data(self,data):
        if self.inside:self.values[-1]+=data

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    parser=Scripts();parser.feed(HTML.read_text(encoding='utf-8-sig'))
    body=SOURCE.read_text(encoding='utf-8-sig').strip()
    same=any(s.strip()==body for s in parser.values)
    result={'project':'SeraresPlayable','fixture_only':False,'source_sha256':digest(SOURCE),
            'build_sha256':digest(HTML),'runner_sha256':digest(Path(__file__)), 'run_id':str(uuid.uuid4()),'embedded_source_matches':same,
            'conditions':{'browser':'Chromium headless','seed':20261006,'network':'HTTP(S) blocked',
                          'instrumentation':'Observe canvas text/images and intercept CTA navigation; no state injection in normal journeys'},
            'scenarios':[],'checks':[], 'limitations':['Desktop browser emulation is not physical mobile-device performance.',
                'Damage display after clicking does not isolate manual skill from concurrent automatic attacks.',
                'CTA test uses existing debug query s=cta&g=5; it does not establish natural full-game completion.',
                'No original commercial game parity, player enjoyment, conversion or market success claim.']}
    assert same, 'Packaged script differs from inspected game.js; reconcile baseline first'
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        result['conditions']['browser_version']=browser.version
        for mode,width,height in [('mouse',390,844),('touch',390,844),('mouse',844,390)]:
            name=f'{mode}-{width}x{height}'
            page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,has_touch=True)
            errors=[]; requests=[]; observations=[]
            page.on('pageerror',lambda err:errors.append(str(err)))
            def block(route):
                requests.append(route.request.url);route.abort()
            page.route('http://**/*',block);page.route('https://**/*',block)
            page.add_init_script(INIT)
            def texts():return page.evaluate('window.__flow.texts')
            def contains(text):
                page.wait_for_function('(s)=>window.__flow?.texts.some(x=>x.text===s)',arg=text,timeout=5000)
            def capture(label):
                p=out/f'{name}-{label}.png';page.screenshot(path=str(p))
                observations.append({'step':label,'canvas_text':texts(),'screenshot':p.name,'sha256':digest(p)})
            def click(x,y):
                scale=min(width/1080,height/1920)
                x=(width-1080*scale)/2+x*scale;y=(height-1920*scale)/2+y*scale
                if mode=='touch':page.touchscreen.tap(x,y)
                else:page.mouse.click(x,y)
                page.wait_for_timeout(65)
            try:
                page.goto(HTML.as_uri())
                contains('Lv.60')
                page.wait_for_function('window.__flow.images.length>0 && window.__flow.images.every(i=>i.complete)',timeout=5000)
                missing=page.evaluate('window.__flow.images.filter(i=>!i.naturalWidth).length')
                assert missing==0,f'{missing} failed images'
                capture('initial')
                click(276,959)
                assert any(225<x['y']<905 and re.search(r'\d',x['text']) for x in texts()),'Attack produced no visible damage feedback'
                capture('attack')
                for level in [61,62]:
                    click(90,1865);contains('변신!')
                    capture(f'popup-{level}')
                    click(540,1320);contains(f'Lv.{level}')
                    page.wait_for_timeout(1200)
                    assert not any(x['text']=='변신!' for x in texts()),'Morph popup did not close'
                    capture(f'level-{level}')
                assert not page.evaluate('window.__flow.opens'),'Normal journey opened store'
                # Separate branch coverage: preexisting debug hook, clearly not natural journey.
                page.goto(HTML.as_uri()+'?s=cta&g=5');contains('지금 무료 설치')
                capture('cta-debug-branch');click(540,1550)
                opened=page.evaluate('window.__flow.opens')
                assert len(opened)==1 and 'com.billionairegames.serares' in opened[0]['url']
                assert not errors,errors
                assert not requests,requests
                result['scenarios'].append({'id':name,'status':'passed','input_mode':mode,'viewport':[width,height],
                    'observations':observations,'page_errors':errors,'external_requests':requests,
                    'cta_intercepted':opened,'image_errors':missing})
            except Exception as exc:
                failure=out/f'{name}-failure.png';page.screenshot(path=str(failure))
                result['scenarios'].append({'id':name,'status':'failed','error':str(exc),'observations':observations,
                    'page_errors':errors,'external_requests':requests,'failure_screenshot':failure.name})
            finally:page.close()
        browser.close()
    result['passed']=all(s['status']=='passed' for s in result['scenarios'])
    result['checks']=['packaged source identity','all requested images decode','attack visible damage','first morph level increase',
                      'post-morph input and second morph','normal flow no store navigation','CTA explicit click intercepted',
                      'no page errors','no external HTTP(S) requests']
    (out/'browser-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'scenarios':[{k:v for k,v in s.items() if k in ['id','status','error']} for s in result['scenarios']],
                      'checks_per_scenario':len(result['checks']),'result':str(out/'browser-results.json')},ensure_ascii=True))
    return 0 if result['passed'] else 1

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'output/flow-plan-20261006/browser');args=ap.parse_args()
    target=args.output.resolve();target.mkdir(parents=True,exist_ok=True)
    result_file=target/'browser-results.json'
    result_file.write_text(json.dumps({'passed':False,'status':'running','runner_sha256':digest(Path(__file__))}),encoding='utf-8')
    try:
        code=run(target)
    except Exception as error:
        result_file.write_text(json.dumps({'passed':False,'status':'fatal_error','error':str(error),'runner_sha256':digest(Path(__file__))}),encoding='utf-8')
        raise
    raise SystemExit(code)
