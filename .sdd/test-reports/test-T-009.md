| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-009 页面功能导航与交付说明独立验收 |
| 版本 | v1.2 |

**总结果：BLOCKED（恢复补验）。** 已补真实Chrome导航、功能卡展开、共享API跳转、路径复制和实际布局；复制失败手选分支与源文件浏览尚未完成。T010证据新增后的安装进度与指纹已由Developer刷新并通过本轮静态复验。以下保留旧记录，不把未验分支写成通过。

## 环境与边界

- Tester backend_test；项目 `/Users/zhaojiaqi/Documents/evanSDDKit/Projects_Repo/tess-chrome`。
- 依据 `harness-core/protocols/project-delivery.md`、当前 T-009 DEL-001～005 与明确派发范围。
- dispatcher errors=[]，仍 awaiting_user/T-006；沿用用户委托独立验收自动继续的 execution_authorization 例外，未改门禁或配置。
- 本轮只静态读取源码/模板/导航/既有验收报告，使用 Python 标准库和临时副本验证生成器。不 import 业务模块，不读取真实 `.env`、数据库、日志、上传内容；未请求生产8099、未启动业务、未调用外部服务。
- Chrome 无可用读屏/截图/操作能力，沿用 T-010 和编排器已有一次恢复失败记录，不重复安装或重试。

## 逐项判定

| DEL | 结果 | 证据与未验范围 |
|---|---|---|
| DEL-001 | BLOCKED（结构部分PASS） | 6个页面按实际路由组织：客户、建档、会话、历史、预览、固定报告；各功能有默认可见流程，接口/来源使用details；不存在旧六区看板。锚点目标静态完整。实际点击导航、展开及桌面/窄屏无遮挡未验，CSS源码不能证明视觉通过。 |
| DEL-002 | PASS（静态契约） | 所有功能具备trigger/input/output及actor/action/data/branch流程；24个接口method/URL逐一与指定路由AST解析结果匹配。核对tess.ts→runs/customers/sessions/reports/audio路由，JSON/WS/文件响应区别明确；schema由AST静态提取，明确类型/位置/字段。共享API引用均对应存在的HTML ID。 |
| DEL-003 | PASS（静态实现） | 定向核对事实替代/历史隔离、金融Decimal/末期上限/有限修正、报告候选+产品最新artifact、Agent同run路由与工具观察循环/终止、地图部分失败。参数标为源码默认值而非当前.env/真实服务验证值；普通函数与Agent工具区分；未编造向量RAG、SSE、任意shell或OS沙盒。 |
| DEL-004 | BLOCKED（来源与边界部分PASS） | 60个来源reviewed_sha256全部与当前文件匹配，定位片段有效；页面/功能/API/模块可传播来源状态。README区分真实spike已验、正式dist尚未实装、三供应商缺Key、默认空库、仅本机Report、显式Mock、8099交接状态。真实浏览器来源打开、路径复制成功/失败手选、hash跳转未验；开发DOM替身不算浏览器证据。 |
| DEL-005 | PASS | README所述生成器在隔离根/输出运行：基线strict退出0；源变化/缺失/Python语法错strict退出2并传播待复核；坏JSON/根类型/无效引用退出1生成错误页；HTML输入转义。不会自动更新reviewed_sha256。正式4交付文件前后hash不变，无业务或任务改动。 |

## 独立隔离验证

证据脚本：`.sdd/test-reports/test_t009_static.py`。

```sh
python3 .sdd/test-reports/test_t009_static.py
# exit 0
# sources=60, pages=6, apis_checked_against_AST=24, modules=12
# isolated_degradation_and_propagation=PASS
# original_files_unchanged=true
# browser_navigation_visual_copy=NOT_RUN
```

脚本仅复制清单内允许的静态来源到临时目录，调用原生成器 `--root <临时目录> --map <临时JSON> --output <临时HTML> --strict`。具体断言：

- 基线60指纹、全部24路由、功能流程字段和内部HTML引用成立。
- reports.py追加无业务含义注释后，src-report、mod-report、API-015、feature-review、page-session均变changed；删除文件显示missing；无效Python显示parse_error。
- source基线未自动重写；恢复原来源后严格生成可通过。
- 测试purpose中的 `</script><img ...>` 被HTML转义，未成为标签；共享API引用缺失、导航根为数组、损坏JSON均生成明确错误页。
- 生成HTML仅自带一个脚本，没有fetch业务调用；本轮不执行其浏览器脚本，复制/手选不据源码判PASS。

## 被验产物指纹

| 文件 | SHA256 |
|---|---|
| README.md | 54b3f760140c9507c28eb796e3ec6204581d87db678f10660d47ab01d43792cd |
| docs/project-console.html | f829d2dc517758239ddddc898d661e5c737f2bbfcd9b397191932ce04943af24 |
| docs/project-map.json | 3220e5c630688ddb6d042c1915462efe59945f2e156de0696d40628b1ff5d733 |
| scripts/build-project-console.py | 259677bb245337733b51a7210cc5733ac236578aa67b0971fc05c68f500aa9ff |

README中的运行/缺配置状态是有链接的 T-007/T-008/T-010 交接证据，本轮未重新读取实际运行配置，不冒充重新实测；源代码默认值和configured≠可用边界均清楚。

## 恢复后最短补验

恢复可操作Chrome及截图能力后，打开 `docs/project-console.html`，依次点击页面→功能→共享API→模块→来源；核对桌面和窄屏无遮挡/无整页溢出，验证details、hash定位、路径复制及拒绝剪贴板时手动选择。此导航不需要供应商Key或业务数据，不发起业务/付费请求。完成这些项目后再决定 DEL-001/004 和总结果，不重跑无关业务测试。

本轮没有业务修复或待沉淀新经验；冻结交付文件归还编排器，任务状态由编排器维护。

## 2026-09-20 浏览器恢复补验（browser_resume_test）

CUA原生Chrome实际打开file:///Users/zhaojiaqi/Documents/evanSDDKit/Projects_Repo/tess-chrome/docs/project-console.html。源码/算法静态检查复用上轮冻结证据，本轮未运行业务或付费接口；导航后端无请求代码静态证据延用。

- DEL-001 浏览器部分 PASS：首次带SidePanel时可视区域约580px，顶部导航自动换行，正文无可见横向溢出；关闭SidePanel后窗口截图约908px，左侧页面导航与右侧功能卡正常。点击“客户会话/销售复盘”落到#page-session，点击“接口与算法”展开，点击“恢复会话”落到#API-006。截图人工看过，未保存为独立图片文件。
- DEL-004 部分 PASS：点击“源码定位”落到#sources，来源路径与指纹可见；首条“复制路径”显示已复制，在Chrome地址栏粘贴（未执行搜索）实际为`frontend/src/router/index.tsx`。复制失败手选分支、源码链接实际查看未验，故本项仍BLOCKED。
- DEL-002/003/005 上轮静态证据仍保留。当前正在新增T010报告证据，导航关于“未安装/浏览器不可用”的进度已滞后，需原交付写入者定向核对后刷新；Tester没有更新map reviewed_sha256或放宽指纹规则。

本轮未修改业务、README、map、生成器或导航页面。浏览器控制权交给presentation_test，后续导航刷新后由编排器指定定向复验，不应机械重跑全部业务。

## 2026-09-20 导航刷新定向复验（静态阶段）

本轮Developer只刷新README、project-map与生成HTML，T010报告保持冻结。重新执行dispatcher errors=[]，沿用明确授权例外。

- `python3 .sdd/test-reports/test_t009_static.py` exit0：60来源、6页、24API AST匹配、12模块；隔离源变化/缺失/解析失败及状态传播PASS，原产物未改。
- `python3 scripts/build-project-console.py --output <临时目录>/console.html --strict` exit0：review_warnings=0。
- README面试入口指向实际`docs/interview-demo.html`；正式扩展已安装、真实Capture入库和剩余Key/宽度/麦克风边界与冻结T010 v1.1相符。导航不再沿用旧AX故障作为当前不可操作原因。
- 复制拒绝准备只读夹具`docs/evidence/browser-integration/clipboard-denied.html`，用sandbox与clipboard-write权限策略包裹原导航；不改原导航、不改浏览器默认权限。是否真的拒绝及手选成功需实际浏览器结果，不凭夹具源码判PASS。

### 本轮浏览器收口状态

presentation_test释放租约时报告操作被“user changed Chrome”保护拦截。本Tester仅执行一次只读getApp核对，当前为用户另一个Chrome窗口，输入框聚焦，非已交接的验收页面。按编排器明确要求不抢用户控制，未执行点击、导航、权限修改或测试夹具。

因此源文件实际打开与自动复制拒绝后的手选分支继续 **BLOCKED**；夹具存在不代表已经执行。当前不是AX故障，也不是产品FAIL。导航刷新静态 **PASS**，DEL-001此前实际窗口布局与导航PASS保留，DEL-002/003/005静态复验PASS，DEL-004仍因上述两个浏览器分支未完成而BLOCKED。总结果 **BLOCKED**。恢复条件是明确空闲的Chrome测试窗口控制权；无需重复安装或重跑业务测试。

## 2026-09-20 独立 Tester 补验（v1.3 / IDE browser）

**总结果：FAIL。** 本轮补齐了 v1.2 未验的源文件打开与复制失败手选；导航/展开/接口跳转/窄屏抽检通过。当前发布页对 9 个已变化来源仍标「源码已核对」，`--strict` 重跑为 9 条待复核，故 DEL-004 不能通过。未读 `.env`，未动 8099 / 产品 Side Panel。未改 `.sdd/tasks.json` 或业务代码。

dispatcher：`execution_mode=automatic`，`gate_phase=passed`（T-006），`errors=[]`；运行中含 T-008 与 T-009。Tester 静态服务仅用 8765/8766，结束后已关闭；8099 仍在听。

### 本轮产物指纹（相对 v1.2 已变，静态项重核）

| 文件 | SHA256 | vs v1.2 |
|---|---|---|
| README.md | `b554182107e389483014abf3b3c86da717b09d8429724940e4b85271ac4e67cf` | 变 |
| docs/project-console.html | `5afdda04a1e394983ae5b654115a9cb0139125044b044a8910dd1a420575de8c` | 变 |
| docs/project-map.json | `95d19160345369e7bb259352476f8e22dc30d1399ae716891166bea374733316` | 变 |
| scripts/build-project-console.py | `259677bb245337733b51a7210cc5733ac236578aa67b0971fc05c68f500aa9ff` | 同 |

导航 HTML/地图生成时间 2026-09-20 10:17。其后 10:48–11:31 有 9 个清单内源文件mtime更新（与 T-008 in-flight 时间重叠，未归 T-009 写范围）。

### 逐项判定

| DEL | 结果 | 本轮新证据 vs 复用 |
|---|---|---|
| DEL-001 | **PASS** | **新**：桌面 977px 左侧页导航 + 右侧卡片，无旧六区；点「客户会话 / 销售复盘」→ `#page-session`，点「共享接口」落到 API-006「恢复会话」GET `/api/sessions/{session_id}` 及可展开字段。360px 抽检：aside 改为 static、导航换行、功能卡与长路径换行，未见整页遮挡。`scrollWidth` 429 vs `clientWidth` 360 来自模拟视口差，可见截图无横向裁切。 |
| DEL-002 | **PASS** | **新静态重核**（不能沿用 v1.2 盖新产物）：6 页、24 API 与当前路由 AST 全匹配、功能 trigger/input/output/flow 字段完整、内部 `href="#…"` 均有对应 id、单 script 且无 `fetch(`。 |
| DEL-003 | **PASS** | **复用结构 + 本轮抽检**：地图仍区分源码默认值/未验运行值、普通函数与 Agent 工具；未编造 RAG/SSE/OS 沙盒。算法正文未对 9 个已漂移源文件逐段重读（超出本任务只读导航授权），过期「已核对」计入 DEL-004。 |
| DEL-004 | **FAIL** | **浏览器补验 PASS**：点 `frontend/src/router/index.tsx:18` 实际打开文件，可见 `export const appRoutes` 与各 Route。点「复制路径」时 IDE 剪贴板不可写，手选框出现，值为 `frontend/src/router/index.tsx`，全选 0–29，状态「自动复制不可用，路径已选中，请按 ⌘C / Ctrl+C。」夹具 `clipboard-denied.html` 已打开并显示 `#sources`；iframe 内点击未打到按钮，手选结论以原页实操为准。**复制成功**复用 v1.2 真实 Chrome 粘贴证据（本轮环境写剪贴板失败，走的是失败分支）。**来源状态 FAIL**：发布 HTML 对下列 9 项仍写「源码已核对」，与当前文件 SHA256 不符：`src-new-ui`、`src-session-ui`、`src-modules-ui`、`src-capture`、`src-asr-ui`、`src-api-audio`、`src-asr`、`src-main`、`src-tech`。`python3 scripts/build-project-console.py --output <临时>/console.html --strict` exit 2，`review_warnings=9`，临时页正确标「来源已变化 · 待复核」。 |
| DEL-005 | **PASS（生成器/README 刷新方法）** | `--strict` 对当前树会标待复核且不改 map 的 `reviewed_sha256`。既有隔离脚本 `test_t009_static.py` 在首条指纹断言处失败（`src-new-ui`），此失败反映发布基线已过期，不是生成器漏检。README 刷新命令仍有效。**偏差（未改 README）**：README 与导航黄条仍写 T008 `llm/asr/maps` missing /「缺配置」；派发 notes 称三项供应商配置已齐。Tester 未读 `.env`、未打 8099 health，按授权记 BLOCKED/偏差，不自改 README。 |

### 技术检查

- TC-01 浏览器导航/展开/接口跳转/复制失败手选/窄屏：**PASS**（本轮实测）。
- TC-02 静态指纹与默认/运行值边界：**FAIL**（9 条过期已核对）；未 import 业务模块。
- TC-03 隔离样例与 README 刷新、无业务付费调用：**PASS**（生成器行为）；发布页未刷新。

### 最短修复方向（交编排器，Tester 不改）

1. 定向重读上述 9 个来源，更新流程/算法说明与 `reviewed_sha256`，再 `--strict` 生成导航。
2. 按真实配置状态改 README/黄条的 T008 边界（缺 Key vs 已配置未验），不要继续写 `missing` 若已不再成立。
3. T-008 仍 in-flight 时，刷新应发生在源码再稳定之后，否则指纹会再次漂移。

无业务修复、无经验落盘。8099 未杀、无 Git 提交。

## 2026-09-20 返工1独立复验（v1.4 / Tess-Chrome Tester）

**总结果：PASS。** 原 v1.3 DEL-004 FAIL 已消失：发布页对指定 9 个漂移来源均写「来源已变化 · 待复核」，其 `reviewed_sha256` 仍为旧基线、未被改成当前哈希。README 已改为 health `configured`≠可用，并如实写 T-008 v2.0 **FAIL**，不再写 `llm/asr/maps` missing 或「未配置真实凭证」。生成器 `--strict` 对当前树标待复核且不改地图指纹。v1.3 浏览器源打开/复制失败手选复用。未读 `.env`，未动 8099 / Side Panel，未改 `.sdd/tasks.json` 或业务代码。

dispatcher：`execution_mode=automatic`，`gate_phase=passed`（T-006），`errors=[]`；`tester_ready` 含 T-009，`in_flight_or_queued` 含 T-008 与 T-009。

### 本轮产物指纹

| 文件 | SHA256 | vs v1.3 |
|---|---|---|
| README.md | `290a657fe0ae07f4624e5774988ce34c0e85c5af3d8899e5218579cd3ffaf93a` | 变 |
| docs/project-console.html | `09e607101e5af74d983b22806a77c3dc6ea29ba15f01ca505859d8a0de905690` | 变 |
| docs/project-map.json | `edf6bd485fa04bab05990fcc151bca3316c7b82196e097c2ade7439603f701e1` | 变（evidence_boundary + src-test8） |
| scripts/build-project-console.py | `259677bb245337733b51a7210cc5733ac236578aa67b0971fc05c68f500aa9ff` | 同 |

### 原 FAIL 9 源（发布 HTML 卡片）

| id | 发布标签 | reviewed 仍为旧基线 | 当前文件哈希 | 假装复核？ |
|---|---|---|---|---|
| src-new-ui | 来源已变化 · 待复核 | `f3b16a52…` | `a0d25452…` | 否 |
| src-session-ui | 来源已变化 · 待复核 | `48203e6e…` | `1d1ba907…` | 否 |
| src-modules-ui | 来源已变化 · 待复核 | `6578b15e…` | `e087c7ab…` | 否 |
| src-capture | 来源已变化 · 待复核 | `98dc7661…` | `7369786e…` | 否 |
| src-asr-ui | 来源已变化 · 待复核 | `4688b583…` | `87ee25ba…` | 否 |
| src-api-audio | 来源已变化 · 待复核 | `835d7eb0…` | `bd7bd81d…` | 否 |
| src-asr | 来源已变化 · 待复核 | `0579a039…` | `071e1442…` | 否 |
| src-main | 来源已变化 · 待复核 | `00a1200b…` | `2be12b53…` | 否 |
| src-tech | 来源已变化 · 待复核 | `786764ca…` | `3ff44e9c…` | 否 |

`src-test8` 已按 T-008 v2.0 重读：`reviewed_sha256=4acca2d3…` 与当前文件一致，标签「源码已核对 · 不等于实机通过」；定位片段为 `| 总结果 | **FAIL**`。

### 逐项判定

| DEL | 结果 | 本轮新证据 vs 复用 |
|---|---|---|
| DEL-001 | **PASS** | **抽检新 HTML**：6 页入口仍在（客户/建档/会话/历史/预览/固定报告）+ 共享接口/模块/来源；无「项目概况/启动指南/验收看板/决策看板」。**浏览器布局/导航**复用 v1.3 PASS，新 HTML 未破坏导航结构。 |
| DEL-002 | **PASS** | **抽检**：单 `<script>`、无 `fetch(` / `XMLHttpRequest`；复制失败手选节点仍在。**契约/AST** 复用 v1.3，未重跑业务接口。 |
| DEL-003 | **PASS** | **复用 v1.3 结构**。9 个已漂移业务源未定向重读、未更新算法基线，与「只标待复核」一致；未编造能力。 |
| DEL-004 | **PASS**（原 FAIL 已消失） | **新**：上表 9 卡均为待复核，旧指纹未改成新哈希。黄条写 llm/asr/maps=`configured`≠可用，T008 v2.0 FAIL。**浏览器源打开/复制失败手选**复用 v1.3 PASS。 |
| DEL-005 | **PASS** | README 刷新命令仍为 `python3 scripts/build-project-console.py --strict`；写明不自动更新 `reviewed_sha256`。隔离输出 `--strict` exit **2**，`review_warnings=17`，地图哈希 `--strict` 前后均为 `edf6bd48…`，`fingerprint_ids_changed=[]`。README 无「均为 missing」/「未配置真实凭证」，验证表写 T008 **FAIL**、T010 **BLOCKED**，「不写已全部通过」。 |

### 技术检查

- TC-01 浏览器导航/展开/接口跳转/复制失败手选/窄屏：**PASS**（复用 v1.3；本轮未重开浏览器，新 HTML 未见破坏导航）。
- TC-02 静态指纹与默认/运行值边界：**PASS**（指定 9 源待复核且未假装复核；未 import 业务模块；未读 `.env`）。
- TC-03 隔离刷新、过期不标已核对、无业务付费调用：**PASS**（`--strict` 标待复核且不改指纹；发布页无 fetch）。

### 范围外（不计入本轮判定）

T-008 仍在改 backend/frontend。Developer 冻结时 `--strict` warnings=9；本轮当前树另有 8 个来源已变，发布页仍写「源码已核对」（生成时匹配、冻结后被 T-008 改掉）：`src-facts`、`src-runtime`、`src-agent-contracts`、`src-context`、`src-registry`、`src-amap`、`src-agent-prompt`、`src-extract-prompt`。生成器对当前树已能标出这 8 条。编排器应在 T-008 源码稳定后再刷新交付页，不把并发漂移算作 T-009 返工失败。

### 经验候选核对（Tester 不写 experience.md）

Developer 建议：「交付 HTML 必须按当前树重生；并发任务改过的源只标待复核。」

`project-delivery.md`「内容提取要求」已写：机器字段更新后生成页面；源码指纹变化先标「待复核」，定向重读后才能更新核对基线，不能只刷新时间冒充已核对。状态枚举含「来源已变化待复核」。

| 候选 | 核对 | 说明 |
|---|---|---|
| 按当前树重生 HTML | **已验证**（规范已覆盖） | 本轮重生页对冻结时的 9 个漂移源已标待复核。 |
| 并发改动的源只标待复核、不改指纹 | **已验证**（规范已覆盖） | 9 条 `reviewed_sha256` 未改成新哈希；生成器 `--strict` 不写回地图。 |
| 是否新增经验 | **不新增** | 已被 `project-delivery.md` 覆盖，无需新条目。 |

无业务修复。8099 未杀、无 Git 提交。任务状态由编排器维护。

## 2026-09-20 主会话降级复验（v1.4）

**说明：** Tester 子智能体 abb254ff 因额度中断未交结论；编排器在主会话按 Tester 角色独立核对应项，**不是** Developer 自验冒充独立子智能体。未改业务代码、未改 tasks 由本段写入前的 Developer 产物。

**总结果：BLOCKED（原 v1.3 FAIL 的 9 项已消失；T-008 续改造成新的发布页过期）。**

| DEL | 结果 | 证据 |
|---|---|---|
| DEL-001 | PASS（复用 v1.3） | 未重开浏览器；v1.3 导航/窄屏仍适用当前页结构（无旧六区、无 fetch）。 |
| DEL-002 | PASS | 生成器仍 6 页 / 24 API；发布 HTML 无 `fetch(`。 |
| DEL-003 | PASS | 未宣称算法已对 T-008 新改动逐段重读。 |
| DEL-004 | 原 9 项 PASS；整体 BLOCKED | 发布页对 src-new-ui/session-ui/modules-ui/capture/asr-ui/api-audio/asr/main/tech 均为「来源已变化 · 待复核」，`reviewed_sha256` 未改成新哈希。T-008 续改后另 8 项（src-facts/runtime/agent-contracts/context/registry/amap/agent-prompt/extract-prompt）发布页仍写「源码已核对」且 SHA 已变。`--strict` 临时生成 exit 2、review_warnings=17。README 已无「均为 missing」「未配置真实凭证」，写明 configured≠可用及 T-008 v2.0 FAIL。 |
| DEL-005 | PASS | 生成器对当前树标待复核且不自动改 fingerprint。 |

**恢复条件：** T-008 源码冻结后再重生 `docs/project-console.html`，使全部漂移来源显示待复核或经定向重读后更新指纹。不因此把原 9 项 FAIL 算未修。

经验候选：交付 HTML 必须按当前树重生、并发改源只标待复核。**不新增**：`project-delivery.md` 已禁止只刷新时间冒充复核。

## 2026-09-20 冻结后重生独立验收（v1.5 / Tess-Chrome Tester）

**总结果：PASS。** 按 T-008 冻结树重生的交付页：20 个盘上哈希不一致来源全部为「来源已变化 · 待复核」，`reviewed_sha256` 未改成当前盘上哈希；`fingerprint_ids_changed=[]`。README/黄条写明 T-008 v4.0 FAIL、跟进待独立 Tester、configured≠已验、T-010 未过、T-007 不是完整 UI。本轮独立浏览器点击通过，不沿用 v1.3 浏览器 PASS 代替。20 个待复核与盘不一致且文案正确，属预期，不记 FAIL。未读 `.env`，未打付费，未杀 8099，未改 backend/data、tasks.json、experience.md、test-T-008.md。

dispatcher：`execution_mode=automatic`，`gate_phase=passed`（T-006），`errors=[]`；`tester_ready` 含 T-008 与 T-009。Tester 静态 HTTP 仅用 `127.0.0.1:8767`，结束后已关闭；未占用 T-008 隔离 LLM 口。8099 仍在听，本轮未请求。

### 本轮产物指纹

| 文件 | SHA256 |
|---|---|
| README.md | `4f733c0ff58576d14e6e88453389c106513a7ad8f9a85fcdcc4c09e0132966ef` |
| docs/project-console.html | `cca2f69fb55bc9ed4e8d00e309e032c47dea664beab96ac88b048f5e52a6ab27` |
| docs/project-map.json | `1716e4e0504d3e3e12131eb9fa261d25435c5cd1868a16e07744d56f61e94cc0` |
| scripts/build-project-console.py | `dfe56e39ebb75594aa072ad7e9e18320e718decb06bf61d139a3f75a2cf66e88` |

说明：核对 `--strict` 时一度误写回正式 `docs/project-console.html`；随后用 `--output` 临时文件对照，去掉生成时间戳后与正式页相同；`project-map.json` 哈希前后均为 `1716e4e0…`。

### `--strict` 与 20 源

`python3 scripts/build-project-console.py --output <临时>/console.html --strict`：**exit 2**，`review_warnings=20`。正式地图 `implementation_status` 仍为 `checked`（基线未提升）；生成页对下列 id 标签为「来源已变化 · 待复核」，且 `reviewed_sha256 !=` 当前文件 SHA256：

`src-new-ui`、`src-session-ui`、`src-modules-ui`、`src-capture`、`src-asr-ui`、`src-api-audio`、`src-facts`、`src-runtime`、`src-agent-contracts`、`src-context`、`src-registry`、`src-amap`、`src-asr`、`src-main`、`src-agent-prompt`、`src-report-prompt`、`src-extract-prompt`、`src-followup-prompt`、`src-tech`、`src-test8`。

其余 40 源标签「源码已核对 · 不等于实机通过」，哈希一致。无「已核对却对不上盘」。`src-test8` 的 `reviewed_sha256` 仍为 `4acca2d3…`（旧 FAIL 基线），当前报告文件已变为 `e77d3e83…`，正确待复核。

### 逐项判定

| DEL | 结果 | 证据 |
|---|---|---|
| DEL-001 | **PASS** | **本轮浏览器**：独立会话打开 `http://127.0.0.1:8767/docs/project-console.html`（非扩展 `ejbpocfjkdofijfgehnnhdnnhigkekdn`）。6 入口：客户 `/#/`、建档 `/#/customers/new`、会话 `/#/sessions/:sessionId`、历史、预览、固定 Report；另有共享接口/模块/来源。无旧六区。点「客户会话 / 销售复盘」→ `#page-session`；功能卡默认可见触发/输入/结果/带分支流程。桌面 977px：`aside=fixed`，`scrollWidth=clientWidth=977`，无横向溢出。360px：`aside=static`、`nav flex-wrap`、卡片宽 328、文案换行；`html.scrollWidth=429` 等于 `innerWidth`（移动模拟视口差），可见截图无整页遮挡。 |
| DEL-002 | **PASS** | 6 页路由与 `frontend/src/router/index.tsx` `appRoutes` 对应。抽检 customers/sessions AST：`GET /api/sessions/{session_id}` 等与地图 24 API 的 method/URL 一致；共享 `href="#…"` 全部有对应 id。点「接口与算法」展开后点「恢复会话」→ `#API-006`，正文 `GET /api/sessions/{session_id}`，请求 Path `session_id:UUID`，响应 200 JSON `SessionDetail`。单 script、无 `fetch(` / `XMLHttpRequest`。 |
| DEL-003 | **PASS** | 抽检 `mod-agent`：真实工具观察循环，limits 6/10/180s，非固定串行全工具；无 RAG/OS 沙盒编造。`mod-finance` 为 Agent 工具 + Decimal 普通函数。地图/模块文案区分源码默认与未验运行值；黄条明确 configured≠已验。20 个漂移源未把算法基线假装已重读。 |
| DEL-004 | **PASS** | 来源均可定位；20 漂移为待复核且未提升指纹。黄条/README 边界与 T-008 v4.0 FAIL、T-010 BLOCKED、T-007≠完整 UI 一致。浏览器：导航、展开、API 跳转、复制失败手选均实测。点「复制路径」：剪贴板不可写，出现只读框值 `frontend/src/router/index.tsx`，选区 0–29，状态「自动复制不可用，路径已选中，请按 ⌘C / Ctrl+C。」成功复制分支本环境不可用，走的是失败手选（符合 AC）。来源链 `…/frontend/src/router/index.tsx#L18` curl 200 可见 `export const appRoutes`；本工具对 `application/octet-stream` 未在页内渲染 .tsx，页面已写「浏览器不能显示源码时复制路径在编辑器打开」，不记产品 FAIL。无业务/付费请求。 |
| DEL-005 | **PASS** | README 刷新命令 `python3 scripts/build-project-console.py --strict` 有效：待复核 exit 2，不写回 `reviewed_sha256`。隔离临时根：匹配源 exit 0；追加注释后 exit 2 且页含「来源已变化 · 待复核」，地图指纹不变。README 无「T-008 已通过」；写 v4.0 FAIL、待独立 Tester、health configured≠已验、T-010 未过、T-007 不是完整 UI。既有 `test_t009_static.py` 仍假设 60 源哈希全等，对当前预期待复核树会断言失败，**不作为本轮否决**；生成器隔离已另跑临时根。只读导航产物；未改业务代码与任务状态。 |

### 技术检查

- TC-01 浏览器导航/展开/接口跳转/复制失败手选/窄屏：**PASS**（本轮独立点击；URL `127.0.0.1:8767`）。
- TC-02 静态指纹与默认/运行值边界：**PASS**（20 待复核未假装已核对；未 import 业务；未读 `.env`）。Developer 自验 `--strict` exit 2 / warnings=20 **不当 PASS**，本轮同意该自验只证明待复核门禁，不证明业务已验。
- TC-03 隔离刷新、过期不标已核对、无业务付费调用：**PASS**。

### 经验候选核对（Tester 不写 experience.md）

Developer 称无需新增。同意：`project-delivery.md` 已要求指纹变化先标待复核、禁止只刷新时间冒充已核对、禁止把未重读哈希写回基线。

| 候选 | 核对 | 说明 |
|---|---|---|
| 冻结后按当前树重生、漂移只标待复核 | **已验证**（规范已覆盖） | 20 卡待复核，`fingerprint_ids_changed=[]`。 |
| 是否新增经验 | **不新增** | 规范已覆盖，无需新条目。 |

无业务修复。8767 已关、8099 未杀、无 Git 提交。任务状态由编排器维护。
