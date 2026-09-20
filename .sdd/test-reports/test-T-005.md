| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-005 统一入口与有界 Agent 独立协议验收 |
| 版本 | v1.1 |

**当前总结果：PASS（T-005 协议回放阶段，返工 1 复验）。** 原无依据“顾虑已解决”、Unknown 屏蔽新关键金额确认两项缺陷已修复；14 项定向检查通过。以下保留初轮失败事实，末节为最新依据。真实 Qwen 未调用，本报告只评价依赖注入的协议回放与真实本地运行器/数据库。

## 范围与实例

- 项目：`/Users/zhaojiaqi/Documents/evanSDDKit/Projects_Repo/tess-chrome`；Tester backend_test。
- dispatcher：automatic，tester_ready 含 T-005，errors=[]；T-003 passed；T-005 无独立业务 AC，验收四项 technicalChecks。
- 项目 Python 3.12 .venv、pytest-timeout、FastAPI TestClient、隔离临时 SQLite。`create_app(config, extra_routers=(router,))` + `install_agent(app, provider=ReplayProvider)`；本轮没有网络模型/ASR/高德请求，不操作 Chrome。
- runtime.py SHA256：`3079f5872a33a0ee2628d71f290cde38d3d512b00fd308dd9ed9981fd617d6ac`。
- submissions.py SHA256：`e46251497fb97ff8debb23fade44aff193d9537cb32c9d91c9c91fd8e774efe4`。
- context.py SHA256：`d036da2303be376ecc6c74bac9f1dc10d33e9fb39f37394ada168a34a2bd4dc1`。

## 初轮 technicalChecks（历史记录）

| 项目 | 判定 | 操作与实际结果 |
|---|---|---|
| TC-14：先202、同run路由，入口意图与发布边界 | PASS（协议回放） | 挂起 provider 时已返回202，只有一条Input/销售Timeline且同run继续；QA不建草稿；按钮跳过分类；补事实/自然语言追问/歧义/草稿编辑/跟进各走对应结果；API014返回202；生成只有draft，无report或report_card。缺Key保留手动原文，run failed而非伪造成功。 |
| TC-15/16：终止、续接、并发、revision与限额 | PASS（协议回放） | needs_confirmation后active_run为空；原子单child与同key复用，第二答案409；旧修订处理变inputs_changed；API011确认不自动调用模型；无关QA不消费待答；独立检查finished_at非空、tasks为空、上限明确继续创建新child保留qa目标，父run不复活。 |
| TC-09：<=3、Unknown、停止可选、关键金额、试驾归属 | FAIL（F-002）；其余PASS | 每轮最多3问；已Unknown的相同可选问题不再问；停止可选后继续；普通关键金额仍要求确认；实际试驾版本未知不会继承候选；独立三代supersedes后模型仅看到最新预算，DB历史3条保留。旧Unknown后新金额的required问题被错误过滤，见F-002。 |
| 工具观察、失败分支、跟进安全 | FAIL（F-001）；其余PASS | 非法shell工具失败观察送回模型，下一轮改调用官方知识工具并保存真实artifact；无工具需求可跳过，不固定全套；白名单外私人事件不进模型；有事件却无resolution_evidence时“已解决”被拒；国际联系方式在模型输入隐藏。完全无事件/依据时却接受“已解决”，见F-001。 |

## F-001：空依据集合放过“顾虑已解决”

- 对应：T-005 第四项、PRD REQ-007/AC-034；“有答案/完成查询不等于解决，无明确反馈或确认依据不得标已解决”。
- 最短复现：新客户空会话，无事实与事件；POST `/api/sessions/{id}/runs` intent=followup；注入工具回合无工具、最终 `{status:ready, summary:客户充电顾虑已解决}`。
- 预期：拒绝无依据结论（当前同类行为应 failed / UNSUPPORTED_FOLLOWUP_CLAIM）；实际：run succeeded，followup.brief.summary 保留“已解决”，items为空。
- 定向复核：`services/agent/runtime.py:545`—547 使用 `all(...)` 判断所引事件依据；无事件时 `all([])` 为真，未拒绝。
- 修复方向：解决结论必须至少引用一个有效确认依据，再判断引用依据覆盖；不能用空集合证明。无事件的中性“暂无新产品动态”仍应允许。
- 独立证据：`test_t005_independent.py::test_no_evidence_cannot_resolve_followup`。

## F-002：旧 Unknown 屏蔽新金额的强制确认

- 对应：T-005 TC-09、REQ-002/AC-028；停止循环追问不意味着新金额可以跳过二次确认。
- 最短复现：本会话 monthly_budget 已为 unknown；销售新发送“客户刚补充现在月供四千”；提取返回 monthly_budget=400000分、证据原文“现在月供四千”。
- 预期：新金额以 proposed 保存并出现 required 确认问题，run needs_confirmation；旧 Unknown 保留至销售明确确认替代。
- 实际：新 proposed 金额写入，但run succeeded，questions为空，没有关键确认入口。
- 定向复核：`runtime.py:312` 正确创建required；`runtime.py:347`—348 只要同key存在unknown就无条件continue，连新金额required一起过滤；`ask` 无可见问题时直接succeeded。
- 修复方向：区分对旧未知项的可选循环追问与新输入/新冲突的关键确认；新金额确认应携带旧Unknown与新proposed来源，在明确supersedes后收敛。
- 独立证据：`test_t005_independent.py::test_new_budget_after_unknown_still_requires_confirmation`。

## 命令与结果

```sh
.venv/bin/python -m pytest backend/tests/agent --timeout=120 -q --disable-warnings --tb=short
# exit 0；22 passed，2.47s
.venv/bin/python -m pytest .sdd/test-reports/test_t005_independent.py --timeout=120 -q --disable-warnings --tb=short --show-capture=no
# exit 1；2 failed, 2 passed，0.90s
```

独立新增PASS：限额结束后finished_at/worker释放及显式child继续；supersedes三代只将最新预算送入模型。原22项与独立用例均以模型替身回放，不能证明真实模型意图准确率、工具选择质量或大陆网络服务可用性。

## 经验与未验范围

- 当前两项缺陷只记录事实，尚未修复，不沉淀为有效经验。
- 既有联系方式投影修复在Agent上下文和CRM国际号提取回放中有效；真实CRM模型抽取仍未验。
- Qwen真实模型、真实语音/地图、最终浏览器业务链由T-007/008负责；本轮不将缺Key判为代码FAIL，也不宣称真实Agent闭环已通过。
- 未修改业务代码、tasks、其他Agent文件；编排器负责返工与状态。

## 返工 1 独立复验

- 2026-09-20；dispatcher tester_ready 包含 T-005，errors=[]；任务冻结 testing。
- 新 runtime.py SHA256：`349c759f0769470cad609870bfb232c207872b461a2a2b8c0df36a7f98c46e6a`，与交接一致。
- 原 Tester 独立复现脚本未修改。复验两个原失败及直接影响的 Unknown、supersedes、可选停止、跟进证据与正常空摘要路径。

```sh
.venv/bin/python -m pytest .sdd/test-reports/test_t005_independent.py backend/tests/agent/test_agent.py --timeout=120 -q --disable-warnings --tb=short --show-capture=no -k 'no_evidence or new_budget or unknown or followup or resolution or superseded'
# exit 0；14 passed, 18 deselected，1.94s
```

| 复验项 | 结果 | 实际证据 |
|---|---|---|
| F-001 原空依据“已解决” | PASS | 原独立用例现在得到 failed / UNSUPPORTED_FOLLOWUP_CLAIM。无事件和空白证据均不能证成；有明确已引用事件证据才生成 resolved。 |
| 合法跟进不被误挡 | PASS | 无事件的“暂无新的产品动态”中性摘要正常 succeeded；引用 confirmed resolved_concerns Fact 及非空 evidence_note 可通过，返回明确 fact ID；白名单私人内容过滤仍通过。 |
| F-002 原 Unknown 后新预算 | PASS | 原独立用例现在 needs_confirmation，并有required问题。可选问题已停止也不能压掉新预算关键确认。 |
| 确认与历史保留 | PASS | required 问题引用旧Unknown与新proposed；API011确认后完整supersedes两者，旧Unknown、新proposed、最终confirmed三条均保留，当前值只剩400000分。三代替代链模型上下文仍只取最新值。 |
| 不重复可选未知追问 | PASS | 旧Unknown对应的重复可选问题仍不重问；普通三问上限与原预算确认child流程继续通过。 |

**当前四项 technicalChecks 均 PASS（协议回放）。** 初轮统一入口、终止释放、并发单消费、限额child和工具失败观察证据仍适用；本轮没有改这些行为。真实供应商、浏览器链路与模型质量仍未验，不将本结果升级为真实 Agent 全链路通过。

经验核实建议：

- “空集合不能证明业务完成”：根因及修复已实测。解决状态必须先有非空、可追溯的来源，再核对每条明确依据；适用于本项目跟进结论校验，不代表任意自然语言同义表达都已穷尽。
- “Unknown 抑制可选重复，不抑制新事实关键确认”：根因及修复已实测。旧未知记录与新金额必须一起进入确认来源，销售明确supersedes后才收敛；历史不能清掉或自动覆写。
- Tester 仅提出建议，由编排器去重落盘；没有改任务状态或经验库。
