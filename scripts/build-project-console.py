#!/usr/bin/env python3
"""只静态读取导航清单中的源码，生成自包含 HTML；不导入业务模块或读取运行数据。

人工归纳与其 reviewed_sha256 绑定。普通刷新只计算当前指纹，绝不自动认可变更。
--root/--map/--output 允许用临时目录验证变更、缺失和错误降级。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

LABELS = {"checked": "源码已核对 · 不等于实机通过", "changed": "来源已变化 · 待复核",
          "missing": "来源失效 · 待复核", "parse_error": "来源解析失败 · 待复核",
          "design": "仅设计", "not_found": "未找到实现"}


def esc(value):
    return html.escape(str(value), quote=True)


def safe_path(root, relative):
    """阻断目录穿越、秘密文件和运行数据；扩展名白名单只用于静态源文件。"""
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or any(x in p.parts for x in ('data', 'uploads', 'logs', 'node_modules', '.venv')):
        raise ValueError('来源路径不允许')
    if p.name.startswith('.env') and p.name != '.env.example':
        raise ValueError('禁止读取真实配置')
    if p.suffix.lower() not in {'.py', '.ts', '.tsx', '.js', '.json', '.txt', '.md', '.sh', '.html', '.command'} and p.name != '.env.example':
        raise ValueError('来源类型不允许')
    result = (root / p).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('来源越出项目')
    return result


def inspect_source(root, source):
    result = {**source, 'state': 'checked', 'current_sha256': None, 'line': 1, 'error': None, 'tree': None}
    try:
        path = safe_path(root, source['path'])
        raw = path.read_bytes()
        result['current_sha256'] = hashlib.sha256(raw).hexdigest()
        text = raw.decode('utf-8')
        if path.suffix == '.py':
            result['tree'] = ast.parse(text)
        elif path.suffix == '.json':
            json.loads(text)
        # TS/JS 不执行，也不冒充编译器语法校验；只验证人工核对的定位片段存在。
        needle = source.get('locator', '')
        if needle:
            if needle not in text:
                raise ValueError('核对定位片段已失效')
            result['line'] = text[:text.index(needle)].count('\n') + 1
        if result['current_sha256'] != source.get('reviewed_sha256'):
            result['state'] = 'changed'
    except FileNotFoundError:
        result['state'], result['error'] = 'missing', '源文件不存在'
    except (ValueError, SyntaxError, UnicodeError, OSError, KeyError):
        result['state'], result['error'] = 'parse_error', '格式、权限、路径或定位片段校验失败；未输出源文件内容'
    return result


def definitions(tree):
    """提取声明字段，不执行 default_factory / Settings / Pydantic。"""
    if tree is None:
        return {}
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def fields_for(name, classes, seen=None):
    seen = set() if seen is None else seen
    if name in seen or name not in classes:
        return []
    seen.add(name)
    node, result = classes[name], []
    for base in node.bases:
        if isinstance(base, ast.Name):
            result.extend(fields_for(base.id, classes, seen))
    for child in node.body:
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            result.append((child.target.id, ast.unparse(child.annotation),
                           ast.unparse(child.value) if child.value is not None else '必填'))
    return result


def validate_map(data):
    if not isinstance(data, dict):
        raise ValueError("导航根必须为对象")
    for key in ('sources', 'pages', 'apis', 'modules'):
        if not isinstance(data.get(key), list):
            raise ValueError('导航结构无效：' + key)
    ids = []
    sources = {s['id'] for s in data['sources']}
    apis = {a['id'] for a in data['apis']}
    modules = {m['id'] for m in data['modules']}
    for group in ('sources', 'pages', 'apis', 'modules'):
        ids.extend(x['id'] for x in data[group])
    for p in data['pages']:
        ids.extend(f['id'] for f in p['features'])
    if len(ids) != len(set(ids)) or any(not all(c.isalnum() or c in '-_' for c in x) for x in ids):
        raise ValueError('导航 ID 重复或无效')
    def check(node):
        for key, allowed in [('sources', sources), ('api_ids', apis), ('module_ids', modules)]:
            if not set(node.get(key, [])) <= allowed:
                raise ValueError('引用不存在：' + str(node.get('id', key)))
        if 'algorithm' in node:
            check(node['algorithm'])
    for group in ('pages', 'apis', 'modules'):
        for node in data[group]:
            check(node)
            for f in node.get('features', []):
                check(f)


def build(root, data):
    validate_map(data)
    sources = {s['id']: inspect_source(root, s) for s in data['sources']}
    apis = {a['id']: a for a in data['apis']}
    modules = {m['id']: m for m in data['modules']}
    classes = {}
    for source in sources.values():
        classes.update(definitions(source['tree']))
    def source_ids(node, visited=None):
        visited = set() if visited is None else visited
        ids = set(node.get('sources', [])) | set(node.get('algorithm', {}).get('sources', []))
        for key, lookup in [('api_ids', apis), ('module_ids', modules)]:
            for ref in node.get(key, []):
                if ref not in visited:
                    visited.add(ref)
                    ids |= source_ids(lookup[ref], visited)
        for f in node.get('features', []):
            ids |= source_ids(f, visited)
        return ids
    def badge(node):
        states = {sources[s]['state'] for s in source_ids(node)}
        state = next((s for s in ('parse_error', 'missing', 'changed') if s in states), 'checked')
        if node.get('implementation_status') in ('design', 'not_found'):
            state = node['implementation_status']
        return f'<p class="state {state}">{LABELS[state]}</p>'
    def links(ids, lookup):
        return ' '.join(f'<a class="ref" href="#{esc(x)}">{esc(lookup[x].get("name", x))}</a>' for x in ids)
    def refs(node):
        return '<details><summary>实现来源与核对指纹</summary>' + links(sorted(source_ids(node)), sources) + '</details>'
    def ul(values):
        return '<ul>' + ''.join('<li>' + esc(v) + '</li>' for v in values) + '</ul>'
    def algorithm(a):
        parts = [f'<p><strong>处理对象：</strong>{esc(a.get("subject", ""))}</p>']
        for key, label in [('steps','处理步骤'),('branches','条件与分支'),('selection','结果如何选择'),('failures','失败与边界')]:
            values = a.get(key, [])
            parts.append(f'<h4>{label}</h4>' + ul(values if isinstance(values,list) else [values]))
        params = a.get('parameters', [])
        if params:
            parts.append('<h4>参数与证据性质</h4><div class="table-scroll"><table><thead><tr><th>参数</th><th>值 / 性质</th><th>位置与影响</th></tr></thead><tbody>')
            for p in params:
                parts.append(f'<tr><td>{esc(p["key"])}</td><td>{esc(p["value"])}<br>{esc(p["value_kind"])}</td><td>{esc(p["location"])}<br>{esc(p["impact"])}</td></tr>')
            parts.append('</tbody></table></div>')
        return ''.join(parts)
    def schema(name):
        values = fields_for(name, classes)
        if not values:
            return '<p class="state missing">声明未提取：' + esc(name) + '；需核对来源。</p>'
        return '<details><summary>展开 ' + esc(name) + ' 字段声明（静态提取）</summary><div class="table-scroll"><table><thead><tr><th>字段</th><th>类型</th><th>默认表达式 / 约束</th></tr></thead><tbody>' + ''.join(f'<tr><td>{esc(n)}</td><td><code>{esc(t)}</code></td><td><code>{esc(v)}</code></td></tr>' for n,t,v in values) + '</tbody></table></div></details>'
    nav = ''.join(f'<a href="#{esc(p["id"])}">{esc(p["name"])}</a>' for p in data['pages'])
    out = [f'<header><p class="eyebrow">TESS-CHROME / 实现导航</p><h1>从一个页面，看懂它如何工作。</h1><p>{esc(data["purpose"])}</p><p class="boundary">{esc(data["evidence_boundary"])}</p><p>人工核对基线：{esc(data["reviewed_at"])}。本次生成：{esc(datetime.now(timezone.utc).isoformat(timespec="seconds"))}。生成时间不代表重新核对或新的运行验收。</p></header>']
    if data.get('differences'):
        out.append('<details><summary>源码与设计的实现差异</summary>' + ul(data['differences']) + '</details>')
    for p in data['pages']:
        out.append(f'<section class="page" id="{esc(p["id"])}"><h2>{esc(p["name"])}</h2><code>{esc(p["route"])}</code><p>{esc(p["purpose"])}</p>' + badge(p))
        for f in p['features']:
            out.append(f'<article id="{esc(f["id"])}"><h3>{esc(f["name"])}</h3>' + badge(f) + f'<p><strong>触发：</strong>{esc(f["trigger"])}</p><p><strong>输入：</strong>{esc(f["input"])}</p><p><strong>结果：</strong>{esc(f["output"])}</p><ol class="flow">')
            for step in f['flow']:
                out.append(f'<li><strong>{esc(step["actor"])}</strong> {esc(step["action"])}<span>{esc(step["data"])}</span><small>{esc(step["branch"])}</small></li>')
            out.append('</ol><details><summary>接口与算法</summary>' + links(f.get('api_ids', []), apis) + links(f.get('module_ids', []), modules) + '</details>' + refs(f) + '</article>')
        out.append('</section>')
    out.append('<section class="page" id="interfaces"><h2>共享接口</h2><p>REST 返回 PyCore JSON 信封：success:boolean、data:T、error/error_code:string|null、metadata:object、message:string|null、timestamp:datetime、request_id:string|null 可追踪；业务字段见展开声明。POST 使用 Idempotency-Key:UUID，写入要求允许的 Origin。PATCH 使用 expected_revision 避免覆盖新数据。400 校验、403 来源拒绝、404 归属/资源不存在、409 冲突、503 缺配置按实际错误返回；WS 和文件不套此信封。</p>')
    for a in data['apis']:
        out.append(f'<article id="{esc(a["id"])}"><h3>{esc(a["id"])} · {esc(a["name"])}</h3><code>{esc(a["method"])} {esc(a["url"])}</code>' + badge(a) + f'<p><strong>请求：</strong>{esc(a["request"])}</p><p><strong>响应：</strong>{esc(a["response"])}</p>')
        for name in a.get('models', []):
            out.append(schema(name))
        out.append('<details><summary>处理算法 / 对应模块</summary>' + algorithm(a['algorithm']) + links(a.get('module_ids', []), modules) + '</details>' + refs(a) + '</article>')
    out.append('</section><section class="page" id="modules"><h2>实现模块与 Agent</h2><p>普通服务函数负责验证或计算；只有模型能通过 tool_calls 选择的白名单项才标为 Agent 工具。没有任意脚本、SQL 或通用网络浏览工具。</p>')
    for m in data['modules']:
        out.append(f'<article id="{esc(m["id"])}"><h3>{esc(m["name"])}</h3><p class="kind">{esc(m["kind"])}</p>' + badge(m) + f'<p>{esc(m["responsibility"])}</p><p><strong>输入：</strong>{esc(m["input"])}</p><p><strong>输出：</strong>{esc(m["output"])}</p><details><summary>算法、参数与失败处理</summary>' + algorithm(m['algorithm']) + '</details>')
        if m.get('agent'):
            out.append('<details><summary>模型如何选择工具、观察结果并停止</summary>')
            for key,label in [('model','模型'),('prompt','提示词'),('tools','可选择工具'),('observation','观察'),('loop','循环'),('stop','停止'),('limits','执行上限'),('result','结果')]:
                value=m['agent'][key]
                out.append(f'<h4>{label}</h4>' + (ul(value) if isinstance(value,list) else f'<p>{esc(value)}</p>'))
            out.append('</details>')
        out.append(refs(m) + '</article>')
    out.append('</section><section class="page" id="sources"><h2>源码与证据定位</h2><p>源码状态只比较人工核对指纹。Python 用 AST、JSON 用 JSON 解析；TS/JS 只校验定位片段，不在这里编译执行。文件链接按此 HTML 所在目录解析；浏览器不能显示源码时复制路径在编辑器打开。</p>')
    for s in sources.values():
        relative = '../' + s['path']
        out.append(f'<article id="{esc(s["id"])}"><h3>{esc(s.get("name",s["path"]))}</h3><p class="state {s["state"]}">{LABELS[s["state"]]}</p><a href="{esc(quote(relative, safe="/"))}#L{s["line"]}">{esc(s["path"])}:{s["line"]}</a><p>{esc(s.get("locator", ""))}</p><p class="micro">核对 SHA256：{esc(s.get("reviewed_sha256", "未记录"))}<br>当前 SHA256：{esc(s["current_sha256"] or "不可读")}</p><button class="copy" data-value="{esc(s["path"])}">复制路径</button><input class="copy-fallback" aria-label="复制失败时手动选择路径" value="{esc(s["path"])}" readonly hidden><span class="copy-status" role="status"></span></article>')
    out.append('</section>')
    warnings=[s['id']+':'+s['state'] for s in sources.values() if s['state']!='checked']
    return document(nav, ''.join(out)), warnings


CSS = """
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:#f7f7f7;color:#202124;font:15px/1.7 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}a{color:#24577b;overflow-wrap:anywhere}a:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid #568aac;outline-offset:4px}aside{position:fixed;inset:0 auto 0 0;width:225px;padding:28px 18px;overflow-y:auto;background:#fff;border-right:1px solid #ddd}nav a{display:block;padding:7px 10px;text-decoration:none;border-radius:4px}nav a:hover{background:#eee}main{max-width:1160px;margin-left:225px;padding:40px 50px 80px;min-width:0}h1{font-size:30px;line-height:1.35;font-weight:550;letter-spacing:-.7px}h2{font-size:25px;font-weight:550;margin:44px 0 10px}h3{font-size:19px;font-weight:550;margin:0 0 12px}h4{font-size:14px;margin:18px 0 5px}p{margin:8px 0 12px}.eyebrow,.micro{font-size:11px;color:#687078}.boundary{background:#fff3dc;padding:15px;border-left:3px solid #a47123}.page{scroll-margin-top:20px}article{margin:20px 0;background:#fff;border:1px solid #ddd;border-radius:7px;padding:24px;min-width:0;scroll-margin-top:20px}.state{font-size:12px;padding:3px 8px;background:#f2f4f4;display:inline-block;white-space:normal}.changed,.missing,.parse_error{background:#fff0d4;color:#805100}.design,.not_found{background:#f5eeee;color:#853d3d}code{font:12px/1.6 ui-monospace,monospace;overflow-wrap:anywhere;white-space:normal}.kind{font-size:12px;color:#687078}.flow{padding-left:23px}.flow li{padding:5px 0}.flow span,.flow small{display:block;color:#626a72}.flow small{font-size:12px}details{border-top:1px solid #e4e4e4;margin-top:14px;padding-top:10px}summary{cursor:pointer;font-weight:500}details:target{outline:1px solid #777}.ref{display:inline-block;margin:6px 8px 3px 0;font-size:13px}table{border-collapse:collapse;width:100%;font-size:12px;text-align:left}th,td{padding:9px;border-bottom:1px solid #ddd;vertical-align:top;overflow-wrap:anywhere;max-width:300px}.table-scroll{overflow-x:auto;max-width:100%}button{font:inherit;background:#fff;border:1px solid #aaa;border-radius:4px;padding:5px 10px;cursor:pointer}.copy-fallback{width:100%;font:13px ui-monospace,monospace;padding:8px;margin-top:8px}.copy-status{font-size:12px;margin-left:10px}header p,article p,article li{overflow-wrap:anywhere}article .micro{word-break:break-all}.copyright{font-size:12px;margin:25px 10px;color:#777}@media(max-width:760px){aside{position:static;width:auto;padding:15px;border-right:0;border-bottom:1px solid #ddd}nav{display:flex;gap:4px;flex-wrap:wrap}nav a{padding:4px 8px;font-size:13px}main{margin-left:0;padding:25px 16px}h1{font-size:26px}article{padding:18px}h2{font-size:22px}}
"""
JS = """
document.addEventListener('click',async event=>{
 const button=event.target.closest('button.copy');if(!button)return;
 const card=button.closest('article'),fallback=card.querySelector('.copy-fallback'),status=card.querySelector('.copy-status');
 try{if(!navigator.clipboard?.writeText)throw new Error('clipboard unavailable');await navigator.clipboard.writeText(button.dataset.value);status.textContent='已复制';fallback.hidden=true;}
 catch{fallback.hidden=false;fallback.focus();fallback.select();status.textContent='自动复制不可用，路径已选中，请按 ⌘C / Ctrl+C。';}
});
// 共享接口跳转会打开父 details，键盘或直接 URL hash 均可定位。
function reveal(){const id=decodeURIComponent(location.hash.slice(1));const target=document.getElementById(id);if(!target)return;let p=target.parentElement;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}}
window.addEventListener('hashchange',reveal);reveal();
"""


def document(nav, body):
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tess-Chrome · 页面功能与实现导航</title><style>' + CSS + '</style></head><body><aside><strong>Tess-Chrome</strong><nav>' + nav + '<a href="#interfaces">共享接口</a><a href="#modules">实现模块与 Agent</a><a href="#sources">源码定位</a></nav><p class="copyright">只读导航 · 无业务调用<br>不读取密钥与客户数据</p></aside><main>' + body + '</main><script>' + JS + '</script></body></html>'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--map',dest='map_path',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--strict',action='store_true',help='来源待复核时退出 2，仍输出提示页面')
    args=parser.parse_args()
    map_path=args.map_path or args.root/'docs/project-map.json'
    output=args.output or args.root/'docs/project-console.html'
    try:
        data=json.loads(map_path.read_text(encoding='utf-8'))
        content,warnings=build(args.root,data)
    except (ValueError,KeyError,TypeError,OSError) as error:
        content=document('', '<header><h1>导航数据解析失败</h1><p class="boundary">未继续展示旧的已核对内容。请检查 project-map.json 的结构、引用与文件编码。</p></header>')
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(content,encoding='utf-8')
        print('ERROR: navigation map invalid ('+type(error).__name__+')')
        return 1
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(content,encoding='utf-8')
    print(f'Generated {output}; sources={len(data["sources"])}, pages={len(data["pages"])}, APIs={len(data["apis"])}, review_warnings={len(warnings)}')
    for warning in warnings:print('REVIEW_REQUIRED '+warning)
    return 2 if warnings and args.strict else 0


if __name__=='__main__':
    raise SystemExit(main())
