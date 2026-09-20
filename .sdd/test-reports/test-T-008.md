| 字段 | 内容 |
|---|---|
| 作者 | Tess-Chrome 独立 Tester |
| 日期 | 2026-09-20 |
| 事项 | T-008 返工3 独立复验（AC-020 发布后跟进；AC-013 抽检） |
| 版本 | v5.0 |
| 总结果 | **BLOCKED**（本轮无已证实 FAIL；AC-020 已修复。真麦 UI / 返回快照仍无法验证） |

**task_id=T-008。** 隔离 Uvicorn `http://127.0.0.1:18141` + 临时 SQLite；真实百炼 `qwen3.7-plus`。未改 `.sdd/tasks.json`、PRD、tech-spec 或业务代码；未清空 `backend/data/`（364544 字节，前后一致）；未杀 8099（PID 35992，health ready）。隔离口 18141 已关闭。未占用 8099/18108/18131。未操作 Chrome / Side Panel `ejbpocfjkdofijfgehnnhdnnhigkekdn`。未提交 Git。Developer 自验与 pytest 35 passed 不计入判定。

摘要：`docs/evidence/external-integration/t008-retest-r3-summary.json`。本文件保留 v4.0 / v3.0 / v2.0 / v1.0 历史，见下文。

## 本轮环境（v5.0）

- git `9b5d0d7` + 工作区返工3。规范 `default`。`sdd_dispatch.py`：`execution_mode=automatic`，`gate_phase=passed`（T-006），T-008 `tester_ready`。
- 配置字段存在性（不记值）：`bailian_api_key/base_url/asr_ws_url`、`amap_web_service_key` 均为 true；隔离 health `ready`，llm/asr/maps=`configured`。
- Capture：`tester-0.1.1-awd-white20.json`。真模型跟进；Mock 仅 fixture 事件。未把 Developer 自验当 PASS。

## 原 FAIL 复验结论（v4.0 → v5.0）

| 原问题 | 本轮 | 说明 |
|---|---|---|
| family-charging-followup run `failed` `INVALID_MODEL_OUTPUT` | **已修复** | 发布后注入 fixture，`intent=followup` → `succeeded`，`error_code=null`，未调充电/金融工具。 |
| budget-followup succeeded 但 GET `/sessions` brief 空、`source_event_ids=null` | **已修复** | GET 会话 `followup.brief` 非空；`source_event_ids` 含本轮注入 ID。 |
| 无证据标 resolved | **未复现** | 无 `resolution_evidence` 的项为 `needs_confirmation`；budget 充电项因 Mock 确认依据为 `resolved`。 |

## 逐 AC（v5.0）

| AC | 结果 | 操作 | 实际 | 证据 |
|---|---|---|---|---|
| AC-004 | **PASS**（API-022，沿用 v3.0）+ UI **BLOCKED** | 本轮未重跑 WS；未操作 Side Panel/麦。 | 非返工3路径。 | v3.0 `ac004-ws-r1.json` |
| AC-005 | **PASS**（沿用 v4.0 抽检） | 本轮未重跑 Unknown。 | 无回归迹象。 | v4.0 `ac005-unknown-r2.json` |
| AC-006 | **BLOCKED** | 未操作原生 Chrome 拒权 UI。 | 同前。 | — |
| AC-007 | **PASS**（沿用 v4.0 抽检） | 本轮未重跑高德查站。 | 非返工3路径。 | v4.0 confirm-center |
| AC-013 | **PASS**（抽检，未全量六案例） | 齐全案 Capture+家充+车位+月供确认后 `prepare_report`。 | `succeeded`+draft；摘要无阿拉伯数字；无 blocking。 | `ac013-complete-r3.json` |
| AC-020 | **PASS** | 可发布草稿 → POST `/events` fixture → `intent=followup`；读 GET `/sessions` 的 brief 与 `source_event_ids`。 | charging：succeeded，brief 非空，source 指向本轮两事件，两项 `needs_confirmation`。budget：succeeded，brief 变化，含本轮新事件；无证据项仍待确认；有 Mock 确认依据的充电项 `resolved`。无私聊哨兵。无 `INVALID_MODEL_OUTPUT`。 | `ac020-family-charging-followup-r5.json`、`ac020-budget-followup-r5.json`、`t008-retest-r3-summary.json` |
| AC-022 | **PASS**（沿用 v3.0） | 本轮未重跑 CRM。 | 无回归迹象。 | v3.0 summary |
| AC-027 | **PASS**（沿用 v4.0） | 本轮未重跑。 | — | v4.0 |
| AC-028 | **PASS**（沿用 v2.0） | 本轮未改冲突路径。 | — | v2.0 `ac028-conflict.json` |
| AC-029 | **PASS**（沿用 v4.0） | 齐全案抽检无 `search_charging`。 | 工具差异与前一致。 | `ac013-complete-r3.json` |
| AC-035 | **PASS**（沿用 v3.0） | 本轮未改归属路径。 | — | v3.0 |
| AC-036 | **PASS**（沿用 v4.0） | 本轮未重跑问题数。 | — | v4.0 |
| AC-043 | **PASS**（外链沿用）+ 返回快照 **BLOCKED** | 未打开已发布报告再对照外链返回。 | 图/列表/`observed_at` 未验。 | — |

## technicalChecks（v5.0）

| 检查 | 结果 | 说明 |
|---|---|---|
| TC-03/17 | **PASS**（API-022，沿用）+ **BLOCKED**（真麦 UI） | 本轮未操作用户 Chrome。 |
| TC-04/09/14/15 | 草稿抽检 **PASS**；Unknown 沿用 **PASS**；跟进 **PASS** | 真模型跟进无工具空转失败。 |
| TC-05/18 | **PASS**（沿用）+ 返回快照 **BLOCKED** | 未做 Chrome 返回对照。 |
| TC-08/10 | TC-08 **PASS**（沿用）；TC-10 跟进可追溯 **PASS**；六案例浏览器 **BLOCKED** | 跟进来源为注入事件 ID，非 Capture/Fact。 |

## 本轮已修复

1. **AC-020 发布后跟进：已修复**  
   复现路径：齐全案出草稿并发布 → `POST /api/sessions/{id}/events` `family-charging-followup` → `POST .../runs intent=followup`。run `succeeded`，GET 会话 `followup.brief` 非空，`source_event_ids`=`59e0a2d5…`、`6a3837cf…`（本轮注入）。无证据项 `needs_confirmation`。  
   再注入 `budget-followup`：brief 改为金融首付比较 + 充电已有 Mock 确认依据；新事件 `b45f30fa…`、`2c1a0c55…` 进入 `source_event_ids`。未把家庭「私人内容测试哨兵」写入摘要。

## BLOCKED 缺口

| 项 | 缺口 | 恢复条件 |
|---|---|---|
| AC-004/006 真麦 UI | 未独占正式 Side Panel | 交接扩展 ID `ejbpocfjkdofijfgehnnhdnnhigkekdn`，用户允许麦克风 |
| AC-043 返回快照 | 未打开已发布报告对照外链返回 | 含充电模块的已发布报告：记录图/列表/`observed_at`，开外链后再开原报告 |
| 六主案例浏览器 | 未全量重跑 | 非本轮返工范围 |

## 经验候选（交编排器落盘，Tester 不写 experience.md）

- **已验证修复**：跟进单独收口，`source_event_ids` 只用本轮/累计 Mock 事件 ID，不能复用 `report.txt` 的 Capture/Fact source_ids。读 **GET `/sessions` 的 `followup.brief` + `source_event_ids`**，不能只看 run.result。无 `resolution_evidence` 不得 `resolved`。适用：本项目 `followup.txt` + 真 Qwen `intent=followup` + API-017 fixture。已用 charging/budget 两套 fixture 独立证实。
- **抽检未回退**：齐全案 `prepare_report` 仍能出草稿（AC-013）。
- **无需用本轮推翻**：v4.0 定性摘要去数字、无阻塞确认不挡草稿仍有效。

## 范围外

- 生产 8099 PID 35992 保持就绪，本轮未作为验收实例。
- Developer pytest / 自验 `t008-rework3-self-verify.json` 不计入本轮判定。

---

# 历史 v4.0（2026-09-20，返工2 FAIL）

| 字段 | 内容 |
|---|---|
| 作者 | Tess-Chrome 独立 Tester |
| 日期 | 2026-09-20 |
| 事项 | T-008 返工2 独立复验（AC-013 草稿收口；不沿用 Developer 自验） |
| 版本 | v4.0 |
| 总结果 | **FAIL**（AC-013 原缺陷已修复；已发布后 AC-020 跟进失败。同时存在 BLOCKED 项） |

**task_id=T-008。** 隔离 Uvicorn `127.0.0.1:18118/18119/18121` + 临时 SQLite；真实百炼 `qwen3.7-plus`、真实高德。未改 `.sdd/tasks.json`、PRD、tech-spec 或业务代码；未清空 `backend/data/`（364544 字节，前后一致）；未杀 8099（PID 35992，health ready）。隔离口已关闭。未操作 Side Panel。未提交 Git。Developer 自验 `t008-rework2-self-verify.json` 未作判定。

本文件保留 v3.0 / v2.0 / v1.0 历史，见下文。

## 本轮环境（v4.0）

- git `9b5d0d7` + 工作区未提交返工2。规范 `default`。`sdd_dispatch.py`：`execution_mode=automatic`，`gate_phase=passed`（T-006），T-008 `in_flight_or_queued`。
- 配置字段存在性：`bailian_api_key/base_url/asr_ws_url`、`amap_web_service_key` 均为 true；隔离 health `ready`，llm/asr/maps=`configured`。
- Capture：`tester-0.1.1-awd-white20.json`。未把 pytest / Mock 高德当真实 PASS。

## 原 FAIL 复验结论

| 原问题 | 本轮 | 说明 |
|---|---|---|
| 齐全案 `UNVERIFIED_SUMMARY_NUMBER` 无草稿 | **已修复** | `prepare_report` `succeeded`，有 draft；摘要无阿拉伯数字；金融模块有数字。 |
| 无车位查站后 `needs_confirmation` 无草稿 | **已修复** | 未确认中心也可出草稿并保留定位缺失；确认「望京(地铁站)」后查站 `ready` 仍能出草稿，不再空转确认。 |
| 查站关键词 / WS / Unknown 再提取 | **未回退** | 抽检成立，见下。 |

## 逐 AC（v4.0）

| AC | 结果 | 操作 | 实际 | 证据 |
|---|---|---|---|---|
| AC-004 | **PASS**（API-022，沿用 v3.0）+ UI **BLOCKED** | 本轮未重跑 WS；非返工2路径。 | v3.0 官方 uvicorn 握手 `ready`。真麦 UI 未验。 | v3.0 `ac004-ws-r1.json` |
| AC-005 | **PASS**（抽检） | 真模型提取；unknown 后再提交「还是不知道」。 | 第二次 `succeeded`，`error=null`，无 `INVALID_MODEL_OUTPUT`；`unknown_support` 含家充/试驾版本；文字保留。 | `ac005-unknown-r2.json` |
| AC-006 | **BLOCKED** | 未操作原生 Chrome 拒权 UI。 | 同 v3.0。 | — |
| AC-007 | **PASS**（抽检） | 确认「望京(地铁站)」后 `prepare_report` 真高德。 | `state=ready`，3 站（石化超充/滴滴/极氪），驾车路线 `ready`，静态图 `map_status=ready`，口径「高德中心点距离」。外链无 `key=`。未确认中心时 analyze 仍为 `ambiguous`（与 v3.0 一致）。 | `t008-retest-r2-confirm-center-summary.json` |
| AC-013 | **PASS** | 齐全案 + 无车位/确认中心两路 `prepare_report`。 | 齐全案 `succeeded`+draft，无 `UNVERIFIED_SUMMARY_NUMBER`，跳过 `search_charging`。无车位未确认中心：`succeeded`+draft，pending 保留定位。确认中心后查站成功仍 `succeeded`+draft。 | `ac013-complete-r2.json`、`ac013-no-parking-r2.json`、`ac013-confirm-center-prepare-r2.json` |
| AC-020 | **FAIL** | 本轮已发布草稿后注入 `family-charging-followup` / `budget-followup`。 | 充电 fixture：`failed` / `INVALID_MODEL_OUTPUT`，followup 空。预算 fixture：`succeeded` 但 brief 空、`source_event_ids=null`。无法证明摘要随产品事件变化且可追溯。 | `ac020-family-charging-followup-r2.json`、`ac020-budget-followup-r2.json` |
| AC-022 | **PASS**（沿用 v3.0 抽检） | 本轮未重跑 CRM。 | 非返工2路径，无回归迹象。 | v3.0 `t008-retest-r1-summary.json` |
| AC-027 | **PASS**（抽检） | 输入含无固定车位。 | 首轮含车位确认问；unknown 后再提交未循环必问同一 unknown。 | `ac005-unknown-r2.json` |
| AC-028 | **PASS**（未全量重跑） | 本轮未改冲突路径。 | 沿用 v2.0。 | v2.0 `ac028-conflict.json` |
| AC-029 | **PASS**（抽检） | 家充+车位 vs 无车位+望京。 | 齐全案无 `search_charging`；无车位调用 `search_charging`。确认中心后出站。 | `t008-retest-r2-summary.json`、`t008-retest-r2-confirm-center-summary.json` |
| AC-035 | **PASS**（沿用 v3.0） | 本轮未改归属路径。 | v3.0 试驾版本 unknown、未继承候选。 | v3.0 summary |
| AC-036 | **PASS**（抽检） | 一轮问题数。 | 首轮 3 问。 | `ac005-unknown-r2.json` |
| AC-043 | **PASS**（外链抽检）+ 返回快照 **BLOCKED** | 确认中心后的 `external_search`。未打开已发布报告再对照返回。 | URL 无 `key=`。返回后图/列表/`observed_at` 未验。 | `t008-retest-r2-confirm-center-summary.json` |

## technicalChecks（v4.0）

| 检查 | 结果 | 说明 |
|---|---|---|
| TC-03/17 | **PASS**（API-022，沿用）+ **BLOCKED**（真麦 UI） | 非本轮返工。 |
| TC-04/09/14/15 | 草稿/Unknown **PASS**；跟进 **FAIL** | 真模型工具→观察→草稿成立；Unknown 再提取成立。Mock 跟进未形成可追溯差异摘要。 |
| TC-05/18 | **PASS**（POI/路线/静态图）+ 返回快照 **BLOCKED** | 确认望京后列表/路线/图一致。Chrome 返回对照未验。 |
| TC-08/10 | TC-08 **PASS**（沿用）；TC-10 **FAIL** | 跟进注入后未得到差异化、可追溯摘要。六案例浏览器未跑。 |

## 本轮已修复 vs 仍 FAIL

1. **AC-013 草稿收口：已修复**  
   隔离服务齐全案：Capture + 月供 400000 分 +「小区车位已安装家充」+ 固定车位，`prepare_report` → `succeeded` / draft。摘要无阿拉伯数字（「英寸轮毂」为去数字残留）；数字在 finance mock 模块。  
   无车位确认「望京(地铁站)」后 `search_charging` `ready` 且仍出草稿，不再无阻塞停在 `needs_confirmation`。

2. **AC-020 跟进：本轮可发布后证实失败**  
   发布后注入 family-charging：run `failed` `INVALID_MODEL_OUTPUT`。budget-followup：`succeeded` 但 followup brief 空。  
   复现：任意本轮可发布草稿 → `POST /events` fixture → `intent=followup`。

## BLOCKED 缺口

| 项 | 缺口 | 恢复条件 |
|---|---|---|
| AC-004/006 真麦 UI | 未独占正式 Side Panel | 交接扩展 ID `ejbpocfjkdofijfgehnnhdnnhigkekdn`，用户允许麦克风 |
| AC-043 返回快照 | 未打开已发布报告对照外链返回 | 含充电模块的已发布报告：记录图/列表/`observed_at`，开外链后再开原报告 |

## 经验候选（交编排器，Tester 不落盘）

- **已验证修复**：定性摘要去数字后，`UNVERIFIED_SUMMARY_NUMBER` 不再整单失败；齐全案可出草稿；数字留在确定性金融模块。适用：本项目 `runtime.qualitative_summary` + 真 Qwen `prepare_report`。摘要可能留下「英寸轮毂」「约为元」等残片，不否定门禁结论。
- **已验证修复**：prepare 无阻塞时强制出草稿；无车位未确认中心时保留 pending，确认中心后仍可出草稿。
- **抽检未回退**：望京确认中心后关键词仍能出站/路线/静态图；Unknown 再提取仍成功。
- **功能未过、暂缓沉淀**：跟进 `INVALID_MODEL_OUTPUT` / 空 brief。v2.0「空依据不能证明顾虑已解决」仍未用有效跟进证明。

## 范围外

- 生产 8099 保持就绪，本轮未作为验收实例。
- Developer pytest 35 passed 不计入本轮判定。

---

# 历史 v3.0（2026-09-20，返工1 FAIL）

| 字段 | 内容 |
|---|---|
| 作者 | Tess-Chrome 独立 Tester |
| 日期 | 2026-09-20 |
| 事项 | T-008 返工1 独立复验（不沿用 Developer pytest 口头结论） |
| 版本 | v3.0 |
| 总结果 | **FAIL**（同时存在 BLOCKED 项；已证实缺陷优先） |

**task_id=T-008。** 隔离 Uvicorn `http://127.0.0.1:18108` + 临时 SQLite；真实百炼 LLM、真实高德、官方 uvicorn WebSocket 握手。未改 `.sdd/tasks.json`、PRD、tech-spec 或业务代码；未清空 `backend/data/`（生产库 364544 字节，前后一致）；未杀 8099（PID 35992 仍监听，health ready）；隔离口 18108 已关闭。未操作用户 Chrome / Side Panel。未提交 Git。

本文件保留 v2.0 / v1.0 历史，见下文。摘要：`docs/evidence/external-integration/t008-retest-r1-summary.json`。

## 本轮环境（v3.0）

- git `9b5d0d7` + 工作区未提交修复。规范 `default`。`sdd_dispatch.py`：`execution_mode=automatic`，`gate_phase=passed`（T-006），`tester_ready` 仅 T-008。
- 隔离配置字段存在性（不记值）：`bailian_api_key/base_url/asr_ws_url`、`amap_web_service_key` 均为 true；health `ready`，llm/asr/maps=`configured`。`requirements` 含 `uvicorn[standard]==0.53.0`。
- Capture 复用 `tester-0.1.1-awd-white20.json`。未把 TestClient / Mock 高德当真实 PASS。Developer 自验 pytest 未作为本轮判定依据。

## 原 FAIL 复验结论

| 原问题 | 本轮 | 说明 |
|---|---|---|
| 确认望京后 search_charging 空 | **已修复** | 确认「望京(地铁站)」后工具 `state=ready`，3 站、驾车路线、静态图 asset。关键词路径已能命中充电站。 |
| API-022 无法升级 | **协议已修复**；真麦 UI 仍 **BLOCKED** | 官方 uvicorn 隔离握手收到 `type=ready`。不是 Side Panel / 真麦克风 PASS。 |
| prepare 金融失败且两案都不查站 | **查站差异已修复**；**草稿仍失败** | 家充+车位跳过 `search_charging`；无车位调用并出站。齐全案 `UNVERIFIED_SUMMARY_NUMBER` 无草稿；无车位案查站成功后仍 `needs_confirmation` 无草稿。 |
| Unknown 后再提取 INVALID_MODEL_OUTPUT | **已修复** | 提交「还是不知道」`succeeded`，文字保留，`unknown_support` 说明家充/试驾版本补充能支持什么。 |

## 逐 AC（v3.0）

| AC | 结果 | 操作 | 实际 | 证据 |
|---|---|---|---|---|
| AC-004 | **PASS**（API-022 升级）+ UI **BLOCKED** | 隔离 uvicorn 创建 ASR 预留后 `websockets.connect`；未操作 Side Panel/麦。 | 预留 `state=created`；握手首包 `type=ready`；finish 前 revision/timeline 未变。真人边说字幕、停录改字、手动发送未验。 | `ac004-ws-r1.json` |
| AC-005 | **PASS** | 真模型提取无车位/望京/月供四千/公司充电不知道；确认 unknown 后再提交「还是不知道」。 | 首轮 3 问。第二次 `status=succeeded`，`error=null`，无 `INVALID_MODEL_OUTPUT`。输入保留。`unknown_support` 含家充与试驾版本说明。 | `ac005-unknown-r1.json` |
| AC-006 | **BLOCKED** | 未操作原生 Chrome 拒权 UI。 | 协议层 WS 已可升级；迟到覆盖/拒权页未验。 | 同 AC-004 |
| AC-007 | **PASS** | 确认区域后 `prepare_report` 确认望京地铁站中心，走产品 `search_charging`（真高德）。 | `region=望京(地铁站)`，`state=ready`，3 站（石化超充/滴滴/极氪），`route_status=ready` 且有驾车距离，`map_status=ready` 有 `map_asset_id`，距离口径「高德中心点距离」。外链无 `key=`。单独 analyze 未确认中心时停在 ambiguous（模型直接作答），不推翻确认中心后的列表。 | `ac007-prepare-charging-r1.json`、`t008-retest-r1-summary.json` |
| AC-013 | **FAIL** | 家充齐全与无车位两案 `prepare_report`。 | 金融工具可跑通。齐全案失败码 `UNVERIFIED_SUMMARY_NUMBER`，无草稿。无车位案已完成查站仍 `needs_confirmation`、无草稿。信息齐全时未完成报告收口。 | `ac029-skip-r1.json`、`ac007-prepare-charging-r1.json` |
| AC-020 | **BLOCKED** | 跟进需已发布报告。 | 本轮仍无草稿/发布，未注入 followup fixture。 | 同 AC-013 |
| AC-022 | **PASS**（抽检） | 真模型 CRM 提取与缺联系方式拦截。 | 完整文本有联系方式 `missing=[]`；缺联系方式 `missing=["contact"]`；无联系方式建档 HTTP 400 `VALIDATION_ERROR`。 | `t008-retest-r1-summary.json` cases.ac022 |
| AC-027 | **PASS**（抽检） | 输入含无固定车位。 | 首轮含 `请确认has_fixed_parking：客户没有固定车位`。unknown 后再提交未循环必问同一 unknown。 | `ac005-unknown-r1.json` |
| AC-028 | **PASS**（未全量重跑） | 沿用 v2.0 冲突确认证据；本轮未改冲突路径。 | 无新回归迹象。 | v2.0 `ac028-conflict.json` |
| AC-029 | **PASS**（工具差异） / 草稿见 AC-013 | 家充文案含「安装」+车位 vs 无车位+望京。 | 齐全案工具无 `search_charging`。无车位案调用 `search_charging` 且出站。差异成立。草稿未出，计入 AC-013。 | `ac029-skip-r1.json`、`ac007-prepare-charging-r1.json` |
| AC-035 | **PASS**（抽检） | 候选「长续航全轮驱动版」vs 试驾后驱版本不确定。 | `trial_vehicle.variant=null`；`trial_variant` 为 unknown；未继承候选版本。 | `t008-retest-r1-summary.json` ac035_036_spot |
| AC-036 | **PASS**（抽检） | 一轮问题数。 | 首轮 3 问；月供 required。未知项保留。 | 同上 |
| AC-043 | **BLOCKED**（返回快照） | 外链字段存在且无 key。 | 缺已发布 Report，未验证返回后图/列表/`observed_at` 不变。 | `ac007-prepare-charging-r1.json` external_search |

## technicalChecks（v3.0）

| 检查 | 结果 | 说明 |
|---|---|---|
| TC-03/17 | **PASS**（API-022）+ **BLOCKED**（真麦 UI） | 官方 uvicorn 可升级。Side Panel 边说字幕/停录改字未验。 |
| TC-04/09/14/15 | **FAIL**（草稿）+ Unknown **PASS** | 真模型会调工具；查站差异成立；Unknown 后再提取成功。prepare 收口仍失败。 |
| TC-05/18 | **PASS**（POI/路线/静态图）+ 返回快照 **BLOCKED** | 确认望京后列表/路线/图一致。Chrome 返回对照未验。 |
| TC-08/10 | TC-08 **PASS**；TC-10 / 六案例 **BLOCKED** | CRM 抽检通过。跟进与浏览器六案例未跑。 |

## 本轮仍 FAIL 的复现

1. **prepare 无草稿（AC-013）**  
   隔离服务：Capture 有效 + 确认月供 400000 分 + 家充「小区车位已安装家充」+ 固定车位 true，`POST .../runs intent=prepare_report`。金融工具成功后 run `failed` / `UNVERIFIED_SUMMARY_NUMBER`，session 无 draft。  
   无车位+望京确认中心后查站成功，prepare 仍 `needs_confirmation`、无 draft。  
   位置：`backend/src/services/agent/runtime.py` `qualitative_summary` / 报告收口。

## 经验候选（交编排器，Tester 不落盘）

- **已验证修复**：官方 `uvicorn[standard]` + websockets 后 API-022 可升级（隔离握手 `ready`）。适用：本项目 uvicorn 0.53 + FastAPI WS。不是 Side Panel PASS。
- **已验证修复**：周边词改为「特斯拉充电 / Tesla Supercharger / 超级充电站」后，确认望京可出站与路线/静态图。
- **已验证修复**：`InvalidModelOutput` 兜底 + `unknown_support` 后，「还是不知道」不再 `INVALID_MODEL_OUTPUT`。
- **已验证修复**：`charging_search_needed` / `_charge_flag` 含「安装」时家充+车位跳过查站，无车位查站。
- **功能未过、暂缓沉淀为有效修复**：prepare 收口被 `UNVERIFIED_SUMMARY_NUMBER` 打断；金融工具成功不等于能出草稿。
- v2.0 候选中「空依据不能证明顾虑已解决」本轮仍未跑跟进，不升级。

## 范围外

- 生产 8099 保持就绪，本轮未作为验收实例。
- `isMoneyFact` 源码仍存在于 `frontend/src/utils/display.ts`，未做视觉回归。

---

# 历史 v2.0（2026-09-20，完整真实验收 FAIL）

| 字段 | 内容 |
|---|---|
| 作者 | Tess-Chrome 独立 Tester |
| 日期 | 2026-09-20 |
| 事项 | T-008 真实 Qwen / ASR / 高德与场景验收（本轮补验） |
| 版本 | v2.0 |
| 总结果 | **FAIL**（同时存在 BLOCKED 项；已证实缺陷优先） |

本文件保留 v1.0 缺 Key 收口（全体 BLOCKED）历史，见文末。有限连通见 `docs/evidence/provider-connectivity/2026-09-20-connectivity.json`，不等于本轮完整 AC。

**task_id=T-008。** 本轮在隔离 SQLite 上对真实百炼 LLM、真实高德 Web 服务做了有界调用；未改 `.sdd/tasks.json`、PRD、tech-spec 或业务代码；未清空 `backend/data/`（生产库 364544 字节，前后一致）；未杀 8099（PID 17216 已不存在，端口当前无监听）；未提交 Git。

---

## 本轮环境

- git `9b5d0d7` + 工作区未提交变更（ASR 重试、Capture 金融字段、侧栏宽度等）。规范 `default`。`sdd_dispatch.py`：`execution_mode=automatic`，`gate_phase=passed`（T-006），`tester_ready` 含 T-008 / T-009。
- 生产 `http://127.0.0.1:8099` 本轮不可用。验收使用隔离 Uvicorn `http://127.0.0.1:18099`，配置从 `backend/.env` 读取字段存在性（不记录值）：`bailian_api_key/base_url/asr_ws_url` 与 `amap_web_service_key` 均为 true；health `status=ready`，llm/asr/maps=`configured`。
- 临时 QA 客户/会话在隔离库；Capture 复用 T-001 真实快照 `tester-0.1.1-awd-white20.json`。
- 浏览器：Cursor IDE browser 打开高德搜索外链。未操作用户 Chrome 窗口，未打开 `docs/project-console.html`，未操作正式 Side Panel（ID `ejbpocfjkdofijfgehnnhdnnhigkekdn`）。
- Mock 未冒充真实供应商 PASS。

## 逐 AC

| AC | 结果 | 操作 | 实际 | 证据 |
|---|---|---|---|---|
| AC-004 | **FAIL** + UI **BLOCKED** | 隔离服务 `POST /api/sessions/{id}/audio` 后连接 `API-022`；macOS `say` 生成 16k PCM。未操作 Side Panel/麦克风。 | 预留创建成功（state=created），finish 前未改 revision/timeline。WebSocket 升级失败：uvicorn 日志 `No supported WebSocket library detected`，握手 404。`backend/requirements.txt` 仅为 `uvicorn==0.53.0`，venv 无 websockets/wsproto。真人边说字幕、停录改字、手动发送 UI 未验。 | `docs/evidence/external-integration/t008-live-summary.json`、`ac004-asr-round3.json` |
| AC-005 | **FAIL** | 真实模型提取「无车位 / 望京 / 月供四千 / 公司充电不知道」；PATCH `home_charging=unknown` 后再提交「还是不知道」。 | 首轮提出具体确认问（月供/车位/区域）。Unknown 经 API-011 保留。第二次提取 `status=failed`，`INVALID_MODEL_OUTPUT`，未见「补充信息能支持什么结果」的成功说明。 | `docs/evidence/external-integration/ac-maps-and-extract.json`、`t008-live-summary.json` cases.extract_b |
| AC-006 | **BLOCKED** | 权限拒绝 UI 仅扩展 Side Panel；本轮未操作原生 Chrome。WS 无法升级，断线/迟到覆盖未实测。 | Composer 在扩展内展示「打开麦克风授权页」；Web 页无该入口。API-022 当前启动方式不能建立实时流。 | `frontend/src/components/Composer.tsx`；ASR 证据同上 |
| AC-007 | **FAIL** | 真实高德：区域检索、确认「望京(地铁站)」后走产品 `search_charging`；对照 `特斯拉充电` 周边检索。 | 区域检索 20 个同名候选（正确进入确认）。确认中心后工具 `state=no_results`、站点空、`map_status=missing`。同中心 `keywords=特斯拉充电` 返回 16 个超级充电站（含望京万象汇）；产品只用 Tesla/特斯拉再滤「充电」，命中的是门店/维修，被滤空。未得到列表与地图对应，也无驾车距离口径。中心静态图（无站点标记）可生成。 | `ac007-amap-direct.json`、`ac007-confirmed-charging.json`、`amap-static-wangjing.png`、`t008-live-summary-3.json` |
| AC-013 | **FAIL** | `intent=analyze`「请查询望京充电站」；`prepare_report` 家充齐全 / 无车位两案。 | analyze 真实调用 `search_charging`，观察多地歧义后说明需确认中心（工具→观察→下一步成立）。prepare_report 多次 `calculate_finance` BusinessError，停在 `needs_confirmation`，无草稿，未完成必要检查。 | `ac013-analyze-charging.json`、`ac029-skip-tools.json`、`t008-live-summary-2.json` |
| AC-020 | **BLOCKED** | 跟进需已发布报告后注入 fixture。 | 本轮 prepare 未产出可发布草稿，未执行 API-017 + followup。产品有 `family-charging-followup` / `budget-followup` fixture，未用真实模型跑通差异摘要。 | `t008-live-summary.json` cases.ac020=[] |
| AC-022 | **PASS** | 真实模型 `POST /api/customers/extract`：含称呼+手机+邮箱；仅称呼无联系方式；缺联系方式建档；确认后建档。 | 完整文本提出 `QA甲` 及联系方式，historical_facts=2，missing=[]。缺联系方式 `missing=["contact"]`。无联系方式建档 HTTP 400 `VALIDATION_ERROR`。确认后 201，列表可见。提取本身不创建客户。 | `docs/evidence/external-integration/ac022-crm.json` |
| AC-027 | **PASS** | 输入含「没有固定车位」；确认后将家充标 unknown。 | 首轮 3 问中含 `请确认has_fixed_parking：客户没有固定车位`（与公司/补能相关线索进入提取）。unknown 保留。未见成功路径上对同一 unknown 项循环追问（第二次提取失败，故循环抑制未单独用成功回合证明）。 | `ac-maps-and-extract.json` |
| AC-028 | **PASS** | CRM 历史「月供五千」建档；会话 C1 确认 400000 分；C2 提交「现在说月供八千」。 | C2 出现 required 确认「八千和五千不一样」。确认后 C2=800000，C1 仍 400000 且 fact id 不同，未改写历史会话。无草稿故未打到发布 409，但关键值确认前未发布金融结论。 | `docs/evidence/external-integration/ac028-conflict.json` |
| AC-029 | **FAIL** | 案例 A：已有家充/固定车位、不需查站；案例 B：无车位+望京。比较 `prepare_report` 工具名。 | 两案 prepare 均未调用 `search_charging`（A 跳过充电/能源；B 同样只打金融）。未体现「无车位应查站、有家充可跳过」的差异。显式 analyze 才会调充电工具，不能替代 prepare 案例差异。 | `t008-live-summary.json` ac029_skip vs maps_b |
| AC-035 | **PASS** | 候选 Capture 版本「长续航全轮驱动版」；文本「实际试驾后轮驱动，版本不太确定」。 | `trial_vehicle=null`；`trial_variant` 为 unknown；未把候选版本写入试驾事实。 | `t008-live-summary.json` extract_b |
| AC-036 | **PASS** | 一次提取；`skip_optional_questions`。 | 一轮问题数=3（上限）。月供为 required。skip_optional 后仍可继续 prepare。未知项（家充/试驾版本）保留。 | `t008-live-summary.json` extract_b |
| AC-043 | **PASS**（快照返回 **BLOCKED**） | 构造 `search_link`；IDE 浏览器新标签打开。缺区域会话充电模块无外链。 | URL `https://uri.amap.com/search`，keyword=`望京地铁站 特斯拉充电站`，city=`北京`，`src=tess-chrome`，无 key/身份/CRM。落地 `ditu.amap.com` 搜索框为该中文词、城市北京。缺区域模块无 `external_search`。无已发布 Report，未验证返回后图/列表/来源时间不变。 | `ac007-amap-direct.json`、`ac043-browser.json` |

## technicalChecks

| 检查 | 结果 | 说明 |
|---|---|---|
| TC-03/17 真麦克风字幕、停录改字手动发送、时延/拒权/迟到 | **FAIL**（WS）+ **BLOCKED**（Side Panel/麦） | 官方启动依赖的 uvicorn 无 WS 库，API-022 不能升级。真人 Side Panel 未操作。创建 ASR 预留不写业务消息。 |
| TC-04/09/14/15 真模型工具观察、差异化、Unknown/冲突 | **FAIL** | 真模型会调工具并处理歧义观察；prepare 金融工具反复失败、两案充电选择无差异；Unknown 后再次提取失败。冲突确认见 AC-028。 |
| TC-05/18 真高德 POI/路线/静态图与 Chrome 外链 | **FAIL**（站点/路线）+ 外链 **PASS** | 真 POI 与中心静态图可用。确认中心后产品充电检索空列表，无路线。外链中文关键词在 Chrome/IDE 浏览器打开且无密钥。返回报告快照未验。 |
| TC-08/10 CRM 预览与跟进/六案例 | TC-08 **PASS**（API）；TC-10 / 六案例 **BLOCKED** | 真实 CRM 提取+缺项拦截通过。跟进与完整六主案例浏览器记录未完成。 |

## FAIL 复现

1. **充电列表空（AC-007）**  
   隔离服务确认 `region=望京地铁站`、`city=北京`，再确认候选「望京(地铁站)」，调用 `search_charging`。得到 `no_results`。同坐标用高德 `keywords=特斯拉充电` 可列出超级充电站。修复方向：周边检索关键词需能命中充电站类 POI（或放宽证据规则），再拉路线与带编号静态图。  
   位置：`backend/src/adapters/amap.py` `stations()`；`backend/src/tools/registry.py` `charging()`。

2. **API-022 无法升级（AC-004）**  
   按 `scripts/run-demo.sh` 同类命令启动 uvicorn 后连接 `/ws/sessions/{sid}/audio/{asr_id}`。日志：`Unsupported upgrade request` / `No supported WebSocket library detected`。  
   修复方向：依赖改为 `uvicorn[standard]` 或显式加入 `websockets`/`wsproto`，再复验实时字幕。不要把协议单测当成 Side Panel 通过。

3. **prepare_report 不能收口（AC-013/029）**  
   已有有效 Capture 与确认预算时 `POST .../runs intent=prepare_report`。真实模型多次 `calculate_finance` 失败，run 停在 `needs_confirmation`，无 draft。家充齐全与无车位两案都未调用 `search_charging`。  
   位置：`backend/src/services/agent/runtime.py` 工具循环；金融参数校验。

4. **Unknown 后再次提取失败（AC-005）**  
   将 `home_charging` 标 unknown 后再次 `POST /inputs`。run `failed` / `INVALID_MODEL_OUTPUT`，已提交文字保留。需模型输出契约或修复重试对用户可见。

## BLOCKED 缺口与恢复条件

| 项 | 缺口 | 恢复条件 |
|---|---|---|
| AC-004/006 真麦克风 UI | 未操作正式 Chrome Side Panel；不与用户窗口争用 | 交接可独占的已安装扩展 ID `ejbpocfjkdofijfgehnnhdnnhigkekdn`；用户允许麦克风；修复 WS 依赖后复验边说字幕、停录改字、手动发送、拒权页、迟到不覆盖 |
| AC-020 | 无已发布报告，未注入 Mock 互动 | prepare 能产出草稿并发布后，分别注入 `family-charging-followup` 与 `budget-followup`，核对摘要差异、来源 id、无私人哨兵 |
| AC-043 返回快照 | 无 Report 链接 | 含充电模块的已发布报告：记录图/列表/`observed_at`，打开外链后再打开原报告对照 |
| 生产 8099 | PID 17216 不在，端口未监听 | 由编排器按 `scripts/run-demo.sh` 恢复正式 dist；Tester 不杀端口、不清库 |

## 经验候选（交编排器，Tester 不落盘）

- 地图凭据脱敏覆盖 HTTP 库日志：本轮未在证据中写出 key；高德 URL 已断言无 `key=`。
- ASR 时长上限先收尾：本轮未跑到时长上限；WS 尚未连通。
- 空依据不能证明顾虑已解决：跟进未跑，不升级 PASS。
- 麦克风授权失败与 ASR 预留回收：本轮未测 Side Panel 拒权；HTTP 预留创建成功。
- 新候选：官方 `uvicorn==0.53.0` 无 WS 额外依赖时 API-022 不能升级。
- 新候选：`search_charging` 用 Tesla/特斯拉关键词会丢掉「特斯拉充电」类超级充电站。

## 范围外

- 生产 8099 宕掉需编排器恢复，不是本任务代码回归结论。
- `calculate_finance` 真实模型参数反复失败，影响草稿/发布/跟进，建议单独排。

---

# 历史 v1.0（2026-09-20，缺 Key 收口，全体 BLOCKED）

| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-008 真实供应商与场景验收缺口独立核对 |
| 版本 | v1.0 |

**结果：BLOCKED。** 本轮没有调用真实 Qwen、实时 ASR 或高德服务，没有新增浏览器证据。已有协议、确定性计算和本地 HTTP 证据有效，但不足以确认真实供应商业务路径；未发现新的、已经证实的实现缺陷。

当时健康接口 `capabilities={llm:missing,asr:missing,maps:missing}`。旧逐 AC 完整结果均为 BLOCKED，局部证据见上文 E1–E7 索引；不能替代 v2.0 真实验证。
