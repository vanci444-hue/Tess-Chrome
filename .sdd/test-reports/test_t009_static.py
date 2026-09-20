"""T009 静态/隔离降级验证；不导入业务，不读 .env、DB、日志或上传。"""
import ast
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/build-project-console.py'
MAP=json.loads((ROOT/'docs/project-map.json').read_text())
FROZEN=['README.md','docs/project-map.json','docs/project-console.html','scripts/build-project-console.py']
fingerprints={x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in FROZEN}

# 定向静态核对所有来源和API；仅解析指定文件 AST，绝不import业务。
routes=set()
for source in MAP['sources']:
    p=Path(source['path'])
    assert not p.is_absolute() and '..' not in p.parts
    assert not {'data','logs','uploads','.venv','node_modules'}.intersection(p.parts)
    assert not p.name.startswith('.env') or p.name=='.env.example'
    raw=(ROOT/p).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==source['reviewed_sha256'],source['id']
    if '/api/routes/' not in str(p) or p.suffix!='.py':continue
    tree=ast.parse(raw.decode());prefix=''
    for node in tree.body:
        if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call):
            if isinstance(node.value.func,ast.Name) and node.value.func.id=='APIRouter':
                prefix=next((ast.literal_eval(k.value) for k in node.value.keywords if k.arg=='prefix'),'')
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute) and dec.func.attr in ('get','post','patch','websocket'):
                    routes.add((dec.func.attr.upper(),prefix+ast.literal_eval(dec.args[0])))
for api in MAP['apis']:
    assert (api['method'].upper(),api['url']) in routes,api['id']
    assert api['request'] and api['response'] and api['algorithm']['steps']
for page in MAP['pages']:
    for feature in page['features']:
        assert all(feature[k] for k in ('trigger','input','output','flow'))
        assert all(all(k in step for k in ('actor','action','data','branch')) for step in feature['flow'])

with tempfile.TemporaryDirectory(prefix='tess-delivery-test-') as tmp:
    tmp=Path(tmp); sandbox=tmp/'project';sandbox.mkdir()
    for source in MAP['sources']:
        path=Path(source['path']);(sandbox/path).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/path,sandbox/path)
    mapfile=tmp/'map.json';output=tmp/'console.html'
    def generate(data,code):
        mapfile.write_text(json.dumps(data,ensure_ascii=False))
        result=subprocess.run([sys.executable,str(SCRIPT),'--root',str(sandbox),'--map',str(mapfile),
            '--output',str(output),'--strict'],capture_output=True,text=True,timeout=20)
        assert result.returncode==code,(result.returncode,result.stdout,result.stderr)
        return output.read_text()
    baseline=generate(MAP,0)
    ids=set(re.findall(r'id="([^"]+)"',baseline))
    assert set(re.findall(r'href="#([^"]+)"',baseline))<=ids
    assert len(re.findall(r'<script',baseline))==1 and 'fetch(' not in baseline
    # 修改一项共享服务，验证来源和其上游页面/功能/API/模块均传播待复核。
    changed=sandbox/'backend/src/services/reports.py';original=changed.read_text()
    changed.write_text(original+'\n# isolated changed source\n')
    page=generate(MAP,2)
    for item in ['src-report','mod-report','API-015','feature-review','page-session']:
        match=re.search(r'<(?:article|section)[^>]*id="'+re.escape(item)+r'".*?<p class="state ([^"]+)"',page,re.S)
        assert match and match[1]=='changed',(item,match[1] if match else None)
    assert MAP['sources']==json.loads(mapfile.read_text())['sources']
    changed.unlink(); assert '来源失效 · 待复核' in generate(MAP,2)
    changed.write_text('def broken(:\n');assert '来源解析失败 · 待复核' in generate(MAP,2)
    changed.write_text(original)
    malicious=copy.deepcopy(MAP);malicious['purpose']='</script><img src=x onerror=alert(1)>'
    escaped=generate(malicious,0);assert '<img src=x onerror=alert(1)>' not in escaped and '&lt;img' in escaped
    bad=copy.deepcopy(MAP);bad['pages'][0]['features'][0]['api_ids']=['missing-api']
    assert '导航数据解析失败' in generate(bad,1)
    assert '导航数据解析失败' in generate([],1)
    mapfile.write_text('{bad json')
    result=subprocess.run([sys.executable,str(SCRIPT),'--root',str(sandbox),'--map',str(mapfile),
        '--output',str(output),'--strict'],capture_output=True,text=True,timeout=20)
    assert result.returncode==1 and '导航数据解析失败' in output.read_text()

assert fingerprints=={x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in FROZEN}
print(json.dumps({'sources':len(MAP['sources']),'pages':len(MAP['pages']),'apis_checked_against_AST':len(MAP['apis']),
    'modules':len(MAP['modules']),'isolated_degradation_and_propagation':'PASS','original_files_unchanged':True,
    'browser_navigation_visual_copy':'NOT_RUN'},ensure_ascii=False))
