| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-003 后端本地基础独立验收 |
| 版本 | v1.1 |

**当前总结果：PASS（T-003 后端本地基础，返工 1 复验）。** 原金额归属交换与国际联系方式投影缺陷均已修复；17 项定向检查通过。以下保留初轮失败事实，末节为最新复验依据。此结果不替代 T-007/008 完整业务与真实供应商验收。

## 范围与环境

- Tester：backend_test；项目 `/Users/zhaojiaqi/Documents/evanSDDKit/Projects_Repo/tess-chrome`。
- dispatcher 独立回读：automatic，tester_ready=[T-003]，errors=[]；T-003 无直接业务 AC，按四项 technicalChecks 验收。完整业务 AC 仍由后续联调负责。
- 项目 Python 3.12 .venv、FastAPI TestClient、真实 SQLAlchemy/SQLite 临时库；本轮不操作 Chrome、不调用供应商、不启动长期服务。
- 被验 reports.py SHA256：`97df1709b7112b28d277e208324707c70c1125b47ae3fdb401400fb88b6b4687`。
- 使用 T-001 实际官网两套 Capture JSON；这里只验证后端存储，不重复宣称本轮进行了真实网页采集。
- 原默认业务库只读核对：customers/sessions/captures/reports 均 0；测试未写默认库。

## 初轮逐项结果（历史记录）

| technicalCheck | 结果 | 实际验证及证据 |
|---|---|---|
| TC-08：身份软查重、多会话、历史与 CRM 隔离 | PASS | 联系方式重复 409，明确 override 可建独立客户；同名不同联系不合并；第二会话无旧候选；历史预算以 historical 返回且不直接作为本次事实；CRM 预览幂等且不提前建客户。core 对应 3 项用例；CRM 路由与存储不写 Capture。 |
| TC-02/07：不可变快照、上限、revision/stale、原子幂等发布及重启 | PASS（基础持久化） | 真快照金额 32150000/31350000 分独立保留；第 4 个候选 409；只读价格修改 400；并发同 key 与新 key 重试均同报告/单卡；身份修改后旧 JSON 与来源时间不变；新 app 读取同 SQLite 内容一致；预算变更使 artifact/draft stale。独立注入卡片持久化失败后无孤立报告，原 key 重试成功且只建单卡。 |
| TC-11/12：信封、Host/Origin、loopback、投影、健康状态 | FAIL（投影）；其余 PASS | 恶意 Host/Origin/无 Origin 写入均 403；坏输入 400；CRM 未配置 503；PyCore success/error/request_id 正确；Key 缺失返回 degraded/missing；Settings 拒绝 0.0.0.0；asset 越界路径 404。国际电话号码在报告正文中保留，见 F-002。 |
| 关键冲突/过期拒发布；辅助缺失可明确发布 | FAIL（数字编辑保护）；冲突/缺失路径 PASS | 冲突金额/事实禁止发布；明确 supersedes 后保留旧事实并可发布；旧草稿 409；无地图等辅助模块以 missing 发布。简单数字更改确实 400，但金额互换绕过只读限制，见 F-001。 |

## 可复现缺陷

### F-001：摘要金额归属互换仍被接受

- 依据：tech-spec「API-014—016 审核、发布与图表」直接编辑只能调整措辞，数字应来自事实和确定性计算；API-014 数字篡改返回 400 READONLY_RESULT。
- 路径：创建客户/会话，导入真实白色 20 英寸快照，用 ReportService.save_draft 保存摘要 `月供4027元，预算4000元`；PATCH 草稿为 `月供4000元，预算4027元`。
- 预期：400 READONLY_RESULT；实际：200，错误金额归属进入可发布草稿。
- 定向复核：`backend/src/services/reports.py:175`—176 对所有数字提取后排序比较，丢失金额顺序及语义归属。原自验只覆盖更换某个数字，未覆盖相同数字集合换归属。
- 修复方向：保护数字及所对应的业务字段/结论；不能仅比较数字集合。允许纯措辞编辑时也不能改变金额含义。
- 证据：`test_t003_independent.py::test_amount_assignment_cannot_be_swapped_in_summary`。

### F-002：被身份接口接受的国际联系方式出现在报告正文

- 依据：TC-11 safe report projection；PRD AC-033、统一契约要求报告不含客户联系方式；号码契约接受明确国家区号。
- 路径：使用虚构保留测试号码 `+12025550123` 建档，生成包含“后续通过该号码联系确认后排体验”的待确认摘要，再发布、GET report。
- 预期：联系方式移除/隐藏；实际：201 发布成功、200 回读中仍含完整测试号码。
- 定向复核：`backend/src/services/reports.py:46`—48 只屏蔽邮箱及中国大陆手机号格式，未覆盖身份规范接受的其他号码。
- 修复方向：投影使用已知客户联系方式做精确隐藏并兼容规范化表现；避免扩大正则误吞车辆金额等数值。草稿、发布和称呼使用一致安全边界。
- 证据：`test_t003_independent.py::test_accepted_international_contact_hidden_from_report`；所用号码不是用户个人数据。

## 执行证据

项目根执行：

```sh
.venv/bin/python -m pytest backend/tests/core --timeout=120 -q
# exit 0；12 passed，1.39s
.venv/bin/python -m pytest .sdd/test-reports/test_t003_independent.py --timeout=120 -q --disable-warnings --tb=short
# exit 1；2 failed, 3 passed，0.82s
```

独立新增 5 项边界检查：金额互换 FAIL、国际联系方式 FAIL、发布中途失败事务回滚及重试 PASS、CRM 等待时仍可手填建客户 PASS、非 loopback 配置拒绝 PASS。测试仅临时库；未改业务代码或任务状态。开发者同版 ruff/mypy/pip check 交接证据沿用，未机械重复。

## 经验核验与未验项

- `CapturedField.key` 保留修复：已在真实快照发布后按 key 读取金额及 variant，修复有效；可沉淀“敏感键投影需区分业务字段标识与 URL 凭据参数”。
- CRM 锁范围修复：独立模拟慢 extractor 期间另一个线程手动建客户在 2 秒上限内完成，且 extractor 断言全局写锁未持有；修复有效，可沉淀“外部等待不持业务全局写锁”。模拟 extractor 仅用于验证锁，不代表真实模型通过。
- 摘要数字修复：简单改值已有效，但存在 F-001，暂不作为完整已验证修复沉淀。
- 真实百炼/ASR/高德、Agent 工作流、浏览器完整业务链、最终 Report 视觉均不属于本次基础任务，未验；缺 Key 不记为本任务代码失败。

由编排器维护任务状态并派发定向修复，Tester 不修改任务账本。

## 返工 1 独立复验

- 2026-09-20；dispatcher tester_ready 包含 T-003，errors=[]，任务冻结 testing。
- 新 reports.py SHA256：`c380c1302831b586f27ad2e8e359ddf1b3cf6569bbc00a1e275e7f4d1f7e5a40`，与开发者交接一致。
- 独立 Tester 原复现脚本未修改；只复验两个原缺陷及同一模块直接影响路径。

```sh
.venv/bin/python -m pytest .sdd/test-reports/test_t003_independent.py backend/tests/core/test_core.py --timeout=120 -q --disable-warnings --tb=short -k 'amount_assignment or international or summary or chinese_amount or numeric_statement or publish_snapshot or revision_stale'
# exit 0；17 passed, 12 deselected，1.76s
```

| 复验项 | 结果 | 实际证据 |
|---|---|---|
| F-001 原金额归属互换 | PASS | 原独立测试现在得到 HTTP 400；交换金额、交换角色、移动 summary 字段/条目、中文数字归属变化均拒绝，原稿及 draft_revision 不变。 |
| 无数字的正常措辞调整 | PASS | 可更新不含数字的 comparing/pending 文案；数字事实句保持原文时允许更新。 |
| F-002 原国际号码泄露 | PASS | 原独立测试公开报告中不再含完整国际号码；另验空格、连接符、括号、00 前缀及纯数字形式，在 build/update/publish 三阶段均隐藏。 |
| 官方字段与数字保留 | PASS | CapturedField.key 保留，vehicle_price 32150000 分及月供4027元仍可读，没有用宽泛数字删除误伤金额。 |
| 不可变发布与 stale | PASS | 双击幂等、单报告卡、身份修改不改旧报告、重建 app 后旧内容不变；预算变更仍令旧草稿拒绝发布。 |

**当前四项 technicalChecks 均 PASS。** 初轮未涉及业务改动的身份、多会话、事务回滚、CRM 非阻塞、Host/Origin 与健康状态证据仍适用；本轮验证修复直接影响路径，没有重复跑无关模块。Chrome 和外部服务未参与本轮，未验边界不变。

经验建议：

- 金额保护根因已证实：排序数字集合无法表达语义归属。当前修复冻结 summary 字段、条目位置和完整含数字句，明确错误提示要求重新生成；这是本 Demo 的保守实现，不是通用语义等价校验。含数字句的措辞也不能直接改，后续界面应展示该限制。
- 联系方式投影根因已证实：入站号码格式比出站过滤范围更广。现以规范化身份值过滤其展示变体，并在草稿、审核、发布复用；车型字段和金额不被误删。可沉淀“输入允许的身份格式必须覆盖到输出安全投影”。
- 先前 CapturedField.key 与 CRM 锁范围经验仍有效，由编排器统一去重落盘；Tester 未修改经验库或任务状态。
