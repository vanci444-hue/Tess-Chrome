| 字段 | 内容 |
|---|---|
| 作者 | Tess-Chrome 独立 Tester |
| 日期 | 2026-09-20 |
| 事项 | T-010 剩余浏览器项（T-008 并入：真麦 UI / 返回快照 / 指定宽度抽检） |
| 版本 | v2.0 |
| 总结果 | **BLOCKED**（无新证实 FAIL；必要真麦、返回快照、正式 Side Panel 与金融官网 Capture 仍无法完成） |

**task_id=T-010。** 未改业务代码、`.sdd/tasks.json`、`experience.md`。未杀 8099、未清空 `backend/data/`（364544 字节，customers/sessions/reports/asr 均为 0）。未操作正式扩展 Side Panel `ejbpocfjkdofijfgehnnhdnnhigkekdn`。未重跑 T-008 真 LLM 六案例。密钥只记配置状态。cursor-ide-browser 已解锁。

## 本轮环境（v2.0）

- `sdd_dispatch.py`：`execution_mode=automatic`，`gate_phase=passed`（T-006），`tester_ready` 含 T-010。
- 8099 health：`status=ready`，`llm/asr/maps=configured`（request_id `4ca9dd4e-90f6-4e9b-b228-d020a98ed052`）。本机库空，无法用生产已发布充电报告做返回快照。
- dist 指纹：`frontend/dist/manifest.json` 仍为冻结 `552b73cf24921653259f7844a4fc16d6e060a519ceefa15e2c20dd9dadf49da7`；`frontend/dist/capture.js` **已变**（当前 `7369786e84535aa6c3239863965551bff0591383bcd5b3a3a69400ab4af51794`，冻结为 `98dc7661…`）。ASR hook/Composer 源哈希与 `asr-start-retry` 一致。
- 浏览器：仅 cursor-ide-browser + 显式 `?mock=1`。正式 Side Panel 按边界不抢用户 Chrome。

摘要：`docs/evidence/browser-integration/t010-v2-remaining.json`。

## 优先未验本轮判定

| 项 | 结果 | 实际 | 证据 |
|---|---|---|---|
| AC-006 / TC 真麦允许、拒绝、停止钮、边说字幕、停录改字发送、迟到覆盖 | **BLOCKED** | 未独占正式 Side Panel / 真麦。Mock 工作区点「实时转写」进入 connecting：可见「取消连接」「放弃本段」，状态「连接实时转写…」；取消后「已停止连接；没有发送会话消息。」未到 recording 的「■ 停止」、未授权拒绝页、无真人字幕。生产 asr_sessions 仍 0。 | 本报告；v1.1/asr_verify 契约不替代真麦 |
| AC-043 含充电模块已发布报告：记地图/列表/observed_at，开高德再回原报告不变；URL 无身份/密钥 | **BLOCKED** | 8099 `reports=0`。Mock 充电模块为 missing：「未查询真实高德，不展示虚构站点或地图」，无 `amap-link`/`map-link`。未伪造 Capture/发布。T-008 外链无 key 沿用不升级本项。 | 健康/只读库；Mock 报告 `862a289c-137f-419b-ab16-ae3f18f6e574` |
| 指定宽度 360/420/480 与 1024/1440 抽检 | **PASS（Mock / cursor-ide-browser）**；正式 Side Panel 窄栏仍 **BLOCKED** | 客户列表 360 overflowX=0、introPad 16px；480 overflowX=0、introPad 20px；420 列表与会话 composer 无横溢。Mock 报告 1024/1440 overflowX=0；1440 三问三列、主标题 44px。1024 金融条图月供与表 ¥4,025.00 同源，预算未知不画 budget-line，能源 ¥46,000 标明非整车 TCO。用户口述动态宽度不记自动视觉 PASS。 | `t010-v2-sidebar-360/420/480.png`、`t010-v2-session-420.png`、`t010-v2-report-1024.png`、`t010-v2-report-1024-finance.png`、`t010-v2-report-1440.png` |
| AC-042 录音中导航结束/放弃 | **BLOCKED** | connecting 时「＋ 新建试驾」禁用；未在录音态点返回弹出结束/放弃。 | Mock 会话 `26633c73-…` |
| AC-042 切客户输入隔离 | **PASS（Mock 抽检，当前 dist）** | A 未发送 `A-unsent-draft-isolation` → B 输入为空且不泄漏 → 回 A 原文恢复。历史报告未在本轮另测。 | Mock 会话 A/B |
| Capture 金融字段真 Tesla 官网 | **BLOCKED** | capture.js 相对冻结已变；用户未操作官网，不伪造 Capture。v1.1 真实 Capture PASS 对应旧 capture.js。 | dist SHA |
| 正式 dist 安装 / 软查重 / 真 Capture 旧证据 | 安装身份沿用（manifest 未变）；软查重/真 Capture **不重跑**；Capture 路径因 capture.js 变更不能自动沿用为当前 dist 金融字段 PASS | 未装/重载用户扩展。 | 冻结 vs 当前 SHA |

## 逐 AC（T-010 任务列表 + 并入项）

未在本轮独立重跑的条目保持 v1.1 边界：局部历史 PASS 不升格为整任务 PASS。

| AC | 本轮 | 说明 |
|---|---|---|
| AC-001 | 沿用 v1.1 PASS（旧 capture.js）+ 金融字段 **BLOCKED** | 新 dist 未再真官网 Capture |
| AC-002 | 沿用部分 PASS + **BLOCKED** | 页面更新中/金额冲突界面仍未触发 |
| AC-003 | 沿用 v1.1 **PASS** | 未因本轮 Mock 改判 |
| AC-006（并入） | **BLOCKED** | 真麦 UI 未验 |
| AC-008、009、010、011、012 | **BLOCKED** | 无新真服务页面走查；不重跑 T-008 |
| AC-014、015、016、017、018、019 | Mock 视觉抽检部分通过；真实组合仍 **BLOCKED** | 1024/1440 Mock 三问/金融/能源/静态 Ask disabled；无真实充电图 |
| AC-021、023、024、026、030、031、032、033、034、037、038、039、041 | 沿用 v1.1 局部；整体 **BLOCKED** | 生产库空，无法复开 v1.1 真实客户/报告 |
| AC-025 | 迟到回包仍 **BLOCKED** | 本轮未做可控延迟 |
| AC-040 | 360/420/480 Mock 列表抽检 **PASS**；正式 Side Panel 三种宽度 **BLOCKED** | cursor-ide-browser 非扩展壳 |
| AC-042 | 切客草稿 **PASS（Mock）**；录音导航 **BLOCKED** → AC 整体 **BLOCKED** | 必要录音分支未完成 |
| AC-043（并入） | **BLOCKED** | 无含充电地图的已发布报告可对照返回 |

## technicalChecks

| 检查 | 结果 |
|---|---|
| 1. P06 1024/1440 三问/参数/预算/能源/地图缺失 | Mock 三问、金融条图、预算未知不画线、能源非 TCO、充电 missing **抽检 PASS**；真实报告/地图缺失态 **BLOCKED** |
| 2. 360/420/480 侧栏与异常 | Mock 列表/会话抽检 **PASS**；正式 Side Panel 与全部异常页 **BLOCKED** |
| 3. 真麦及录音导航/迟到/切客/关闭 | connecting 取消钮可见；真麦允许/拒绝/停止录音/字幕/迟到 **BLOCKED** |
| 4. build/安装/无 CDN Key | manifest 指纹未变，安装沿用；本轮未重跑 typecheck/build |
| 5. T002 宽度/软查重/延迟 | 宽度 Mock 抽检；软查重沿用 v1.1；延迟 **BLOCKED** |
| 6. 正式 SidePanel 真 Capture→发布 | 本轮未操作正式扩展；生产 reports=0 **BLOCKED** |

## 恢复条件

1. 交接正式扩展 Side Panel（ID `ejbpocfjkdofijfgehnnhdnnhigkekdn`）独占时段：真麦允许与拒绝、recording「停止」、边说字幕、停录改字手动发送、迟到覆盖、录音中返回结束/放弃。
2. 8099 上含充电模块的已发布报告（或用户允许用现有真实报告）：记录地图/列表/`observed_at`，开高德外链后再开原报告对照；不写密钥。
3. 用户在 Tesla 中国 Model Y 页手验当前 dist 的金融字段 Capture（因 capture.js 已变）。
4. 不要把 Mock 宽度/草稿隔离或 T-008 供应商 API PASS 写成 T-010 整任务 PASS。

未修改任务状态。本文件以下保留 v1.1 历史。

---

# 历史 v1.1（2026-09-20 浏览器恢复补验）

| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-010 最终 Chrome 安装、交互及布局验收缺口独立核对 |
| 版本 | v1.1 |

**结果：BLOCKED（2026-09-20 恢复补验）。** 正式 `frontend/dist` 已实际安装，真实 SidePanel 建档、真实 Tesla Capture 与本地持久化通过；软查重三分支、未发送草稿恢复、缺模型/ASR提示通过。完整真实报告生成仍缺供应商配置，精确宽度、麦克风与可控迟到等必要项尚未齐。下面保留原阻塞记录及新增证据，不把局部 PASS 写成整体通过。

## 本轮范围与证据

项目 `Projects_Repo/tess-chrome`，F-003 / T-010，T-006/T-007 阶段 PASS。当前派发仅核对现有证据及缺口；dispatcher `errors=[]`、`awaiting_user / T-006` 如实保留，依 tasks.execution_authorization 明确的独立验收授权例外收口，不假称用户亲验或配置完成。

仅对 `http://127.0.0.1:8099/api/health` 发起一次只读请求：`status=degraded`、`database=true`、`llm/asr/maps=missing`；request_id `532dd8a2-70c3-4390-92b0-75827f5e8328`。没有操作默认客户库、读取密钥、安装工具或再次恢复 Chrome。

Chrome 既有故障为 AX 只剩窗口标题、截图不可用；编排器一次定向恢复仍失败。沿用 [T-002](test-T-002.md) 的失败、修复和工具阻塞历史。当前没有新环境变化，不重复试错。

证据简称：E1=[T-001 真实官网 spike](test-T-001.md)；E2=[T-002 契约 Mock UI](test-T-002.md)；E4=[T-004 Adapter/计算/ASR 后端协议](test-T-004.md)；E5=[T-005 Agent 协议](test-T-005.md)；E6=[T-006 Report/音频实现协议](test-T-006.md)；E7=[T-007 正式本地 HTTP/数据](test-T-007.md)。版本指纹复用 [冻结清单](../../docs/evidence/local-integration/frozen-sha256.json)，开发自验见 [T007-handoff](../../docs/evidence/local-integration/T007-handoff.md)。本轮未改业务，没有重复执行稳定模块测试。

## technicalChecks

| 当前任务检查 | 结果 | 现有局部证据 | 必须补齐 |
|---|---|---|---|
| 1. P06 1024/1440、三问/参数/预算/能源/地图缺失 | BLOCKED | E6/E7 SSR、同源数值、缺失不补零、能源非 TCO | 实际两个桌面宽度的完整渲染、首屏信息层级、图表及异常可读性。 |
| 2. 360/420/480、各页关键异常、静态按钮及地图例外 | BLOCKED | E2 已验部分逐层导航；E6 静态按钮/地图 URL 契约 | 三个宽度实际布局、独立滚动/固定输入、所有关键异常和真实点击行为。 |
| 3. 真麦克风及录音导航/结束/放弃/尾段/迟到/切客/关闭 | BLOCKED | E4/E6 协议与 PCM、编辑/发送锁定、释放；不是实际麦克风 | Chrome 权限允许/拒绝、真实采音/字幕与导航关闭操作；识别依赖 T008。 |
| 4. build/安装/无 CDN 或 Key/失败历史等 | BLOCKED（组合项） | E6/E7 构建、类型、MV3/CSP、本地资源、静态扫描、Missing/stale/冲突接口已验 | 正式 dist 安装、权限实际执行与异常界面。构建/静态局部 PASS 不使整项 PASS。 |
| 5. T002 剩余宽度/软查重/同名异联系/会话与延迟 | BLOCKED | E2 草稿隔离、同客新会话和 F01 修复；E7 API 归属/历史边界 | 未验软查重与同名不合并的最终点击路径；可控延迟 Capture/工具/ASR 回包时切客、切会话的可见归属。 |
| 6. 正式 SidePanel 真实 Capture→持久化→审核发布→固定链接 | BLOCKED | E1 真采集；E7 正式 HTTP 以 E1 fixture 入库到发布重启 | 正式扩展完整连续用户操作；fixture 注入与 HTTP 不能替代该路径。 |

## AC 映射

下列每个 AC 的**最终浏览器验收结果均为 BLOCKED**。已有稳定局部证据保留，不表示所有实现重新失败，也不表示真实完整业务已通过。

| AC ID | 已有局部证据 | 必须补齐的最终操作 |
|---|---|---|
| AC-001、AC-002 | E1 两套真实配置/旧快照/缺金融不补值；E7 Capture 字节与冻结脚本一致 | 正式 dist 的当前页 Capture、更新中/缺字段/冲突呈现及旧快照不变。 |
| AC-003 | E2 第四候选提示先移除且无覆盖；E7 第四候选 409、旧数组不变 | 正式插件接真实后端重复确认限制和提示。 |
| AC-008、AC-009 | E4 地图失败/无 Key/路线缺失契约；E6 缺图保留已有列表 | 真/缺失条件下实际页面区分 Unknown、查询失败、无匹配，估算依据及不擅自判便利。真实服务归 T008。 |
| AC-010、AC-011、AC-012 | E4 独立账本、末期上限、无解/优惠缺项/未知费率拒算、Capture 不变；E7 独立复算 | 最终页面金融硬约束、各金额/费用呈现、无解及冲突提示；试算后原方案仍不变。 |
| AC-014、AC-015、AC-037、AC-038 | E4/E5 工具失败与 Mock/Estimate/Missing；E7 来源、原采集时间、固定报告重启不变 | 生成/审核/旧链接页面显示全部来源与时间，工具失败不可假成功，Mock 金融不升级官方。 |
| AC-016、AC-031 | E7 HTTP 审核发布、唯一 ID、不可变内容与服务重启 | 浏览器打开不同审核报告/新旧固定链接、刷新和关闭重开仍对应正确快照。 |
| AC-017 | E6 业务按钮 disabled、地图为明确外链例外 | 最终 Report 实际点击不触发业务请求；外链实际打开由 T008 同步验。 |
| AC-018、AC-019 | E6/E7 SSR 图表与文字同源、金额单位、能源假设和缺失；未称 TCO | 实际图表视觉、预算线、缺数据状态，1024/1440 的可读性。 |
| AC-021、AC-034 | E5 隐私白名单、无依据解决结论拒绝，F-001 修复独立通过；E2 Mock 摘要 | 最终侧栏含私人事件的摘要不泄露、不推断购买意愿，无依据不得标已解决。 |
| AC-023 | E7 客户 API/数据边界仅提供部分支持；没有完整软查重 UI 独立证据 | 同联系方式提示进入已有客户、同昵称异联系方式不合并、明确不同人可建档。 |
| AC-024、AC-026 | E2 同客多会话；E7 历史采用创建本次事实、旧 ID 跨会话拒绝、本次 Unknown 优先 | 正式 UI 新会话身份沿用、历史来源/再次确认、旧数据不变、继续未完成不重复创建。 |
| AC-025、AC-042 | E2 草稿跨会话恢复；E6 音频 generation/导航源码与协议；E7 revision/会话边界 | 可控迟到回包时实际切客/切会话，录音结束或放弃提示，报告历史导航和面板关闭；不得拿后端隔离等同前端归属正确。 |
| AC-030、AC-032 | E6 审核文字/数字权限；E7 输入改变 stale、发布 409、部分缺失可留档 | 实际审核改预算/区域/成本后旧稿不可发、可部分发布的缺失说明、整体失败无成功卡/链接。 |
| AC-033 | E6 首屏三问 SSR、按 report_id 清理显示状态；E7 隐私投影 | 桌面首屏实际可见性、跨不同客户报告不残留、正文无联系方式。 |
| AC-039、AC-040 | E2 模拟 Alex、逐层单主视图；health 的 demo_advisor=Alex/is_demo=true | 正式插件无登录流程，顾问/客户区分，三种窄宽导航、Report 新标签而非铺满侧栏。 |
| AC-041 | E2 报告卡/历史同 ID；E7 幂等发布、单卡、无草稿混入及重启数据 | 正式点击卡片/历史列表同内容、跨会话可找到，面板重开和响应丢失重试不增重复卡。 |

## 恢复后最短收口路径

1. 恢复 Chrome 的可操作、读屏及截图能力并交接独占实例。正式加载项目 `frontend/dist`，核实固定扩展 ID `ejbpocfjkdofijfgehnnhdnnhigkekdn`、真实 SidePanel/权限与后端 Origin；旧 spike ID 不替代正式 ID。
2. 隔离测试客户从真实 Model Y 当前页面抓两套选配，确认、审核、发布和新标签旧链接复开。真实模型/ASR/高德部分需同时满足 [T-008 恢复条件](test-T-008.md)，未配置时只能验明确 Missing 路径。
3. 补 360/420/480 侧栏与 1024/1440 Report 视觉、软查重、可控延迟归属、失败呈现和录音导航；复用 E1/E2 已稳定证据，不机械重复不受影响模块。

本轮没有新证据表明存在可立即修复的独立实现缺陷；仍不能保证这些未运行路径无缺陷。未修改任务或业务文件，未占用 Chrome 控制权，后续状态由编排器处理。

## 2026-09-20 浏览器恢复补验（Tester browser_resume_test）

Chrome AX 与截图已恢复，这是重新操作的新增环境依据。dispatcher errors=[]，依据既有 execution_authorization 自动独立验收授权继续，未修改任务或门禁。通过 CUA 原生 Chrome Load unpacked 选择 frontend/dist；Chrome 实际显示“Tess · 销售工作空间 0.2.0”，ID `ejbpocfjkdofijfgehnnhdnnhigkekdn` enabled，旧 spike 未改。未使用 CDP、Playwright、脚本注入或修改业务。

### 本轮实际结果

| AC / 检查 | 本轮结果及边界 |
|---|---|
| AC-001 | PASS：正式 SidePanel 在真实官网白色 AWD 19寸采集313500，切20寸后采集321500；两张旧/新卡并存且原19寸快照不变。两份 Capture 均实际UI触发后存至正式API。 |
| AC-002 | 金融未展开 Missing 与展开后费用/优惠未读取提示 PASS；页面更新中和核心金额冲突界面未触发，组合项仍 BLOCKED。 |
| AC-003 | PASS：第三条为展开金融后的 Capture；第四次点击显示“已有3个候选，请先移除一个”，只读API复核仍三条，无覆盖。 |
| AC-015、AC-032 | 缺模型失败分支 PASS：手动发送测试文字后显示“本轮失败”“已提交文字仍已保存”；再次进入和API确认原文仍在，无真实成功报告。地图部分失败可发布等其余分支仍未验。 |
| AC-023 | PASS：同邮箱出现已有客户入口，点击返回原session；同昵称不同邮箱创建新customer_id；相同邮箱明确“不同客户，独立建档”创建第三档案。全在正式插件和正式API。 |
| AC-024 | 新试驾保留客户身份、生成不同session、候选0且输入空；已有客户入口返回原session不新建的分支 PASS。已有报告保持不变仍需真报告路径。 |
| AC-025、AC-042 | A未发送文字返回列表再进原session恢复；新会话及另一客户输入不含A草稿。可控迟到、录音导航/关闭仍 BLOCKED，不以普通切换替代。 |
| AC-039 | 插件身份部分PASS：实际SidePanel直接显示Alex销售顾问·Demo，无登录。正式报告顾问一致性需真实报告生成后继续核对，整体仍BLOCKED。 |
| AC-040 | 客户列表→建档→会话逐层展示、返回列表 PASS；实际窄栏截图约320px内容宽可见固定输入区，无整页横溢出。完整三种要求宽度/全部历史路径尚未齐。 |
| AC-016、AC-017、AC-018、AC-019、AC-033、AC-037 | 仅显式`?mock=1`补验：新建QA Mock Report→两次Mock Capture→准备→勾选审核→发布→卡片新标签打开同ID报告。首屏三问可见，未知车型参数不画零，金融条图与表格4025一致，预算未知不画预算线，5年能源曲线/46000节省标明仅能源与Mock假设；Ask按钮AX disabled。并未验证全部实际点击无请求、所有参数/预算线或真实来源报告，因此原真实组合AC仍BLOCKED。 |
| ASR技术检查 | 点击实际“实时转写”后提示“实时语音服务未配置，可先输入文字”；没有冒出假字幕。尚未到真实采音阶段，权限允许/拒绝、录音导航和关闭继续未验。 |
| 安装/构建技术检查 | 最终dist安装 PASS，已有构建与资源安全证据延用。完整报告生成实际链路尚受Key阻塞。 |

未列入新增结果的原AC继续保持上表BLOCKED与已有局部证据，不扩大通过范围。当前没有新增已证实业务FAIL。

### 可复查证据与测试数据

- `docs/evidence/browser-integration/2026-09-20-browser-resume.json`：三份实际UI采集的只读API原始payload、会话ID、当前构建与关键源码指纹；未包含联系方式。
- 主测试客户 QA Browser A：`7aba1027-4faa-4672-bea9-c81621a182e6`；原会话`c34be5f9-0aa6-4fcc-93d8-0ac1e21da5fd`；新会话`6faadfc9-dc59-4fa9-bb42-897612208cbf`。
- 同名独立客户`906adb5b-c7ad-4888-b8ff-768fafd16e5e`，明确重复联系独立客户`4aac8556-91df-45fd-aad9-370265b66df2`。均QA测试档案，未删除其他数据。
- 显式Mock报告：`http://127.0.0.1:8099/?mock=1#/reports/6977d97f-91c2-4094-a16e-1ec1dde48c46`；只存在该浏览器Mock存储，不是正式后台报告。
- CUA会话返回的实际截图已人工检查：正式SidePanel新旧候选、金融Missing、原官网金融面板；Mock报告首屏、金融条图/表格、能源曲线。截图未另存磁盘，不声称有截图文件。
- 正式API只读复核：captures=3、active=true、提交文字存在、真实reports=0；health仍llm/asr/maps=missing。没有读取密钥或全量客户数据库。

浏览器控制权已明确移交 presentation_test。剩余精确360/420/480及1024/1440宽度、权限与迟到时序、真实模型/地图/ASR及完整发布仍需后续补验。本次普通浏览器截图不替代这些指定宽度。
