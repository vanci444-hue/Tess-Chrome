# 项目经验

存放位置：`<active_project_path>/.sdd/experience.md`。仅由编排器在修复复验后判断、去重并更新；Developer/Tester 返回建议与证据。开始任务时按关键词检索相关标题，无命中就继续，不读取全部历史。

流程依据：`<harness_root>/harness-core/protocols/experience-loop.md`。经验不覆盖当前项目契约与所选规范；未复验、原因推测、一次性问题留在错误记录，不为每次报错增加条目。

## 条目格式（说明，不是已发生的经验）

实际记录时使用有辨识度的标题，填写：

- 关键词与适用条件：已知的技术栈、版本或触发场景。
- 现象与已证实根因；有效修复；下次如何避免。
- 来源任务或独立 Bugfix 描述；复验日期；证据的项目相对路径和具体章节，交付时返回实际绝对路径。
- 同类复发时更新原条目，说明旧经验未能避免问题的已核实原因，补充新的验证证据；失效结论标明并保留旧来源。

有跨项目价值时在原条目附简短全局候选；经用户授权，由编排器更新 `<harness_root>/memory/harness-experience.md` 并回链对应标题。全局记录不是自动生效的强制规则，不自动修改 Skill 或技术规范。不记录密钥、敏感原始数据或完整日志。


## Tesla 中国 Model Y：选中态与金额口径

- 关键词与适用条件：Model Y design、radio checked、金融弹窗、月供、车漆优惠；适配器 tesla-cn-modely-dom/0.1.1。
- 已证实：输入控件本身可为隐藏样式，应检查 checked 并读取关联可见 label；不能以隐藏 input 判未选中。贷款状态底部先展示月供后展示车辆价格，必须锚定车辆价格标签。实际月供文本可为“¥3,060/月”，车速单位为“公里/小时”。
- 修复：金融费率数值和费率口径从同一个匹配提取；配件仅在实际存在且可读的配件复选框组内确认未选，不能因无 checked 直接猜空数组。选配标价可能有优惠，不以标价简单求和判总价冲突；首付与贷款本金仍校验闭合。
- 证据：T-001，2026-09-20 独立 Tester 复验真实白20与白19两套配置、旧快照不变、关闭金融缺失不继承；见 `.sdd/test-reports/test-T-001.md` 和 `docs/evidence/capture-spike/`。六项解析回归通过。站点结构后续可能变化，复用时需核对。

## 报告安全投影保留业务字段标识

- 关键词与适用条件：CapturedField.key、ReportModule、递归隐私过滤。
- 已证实根因：将通用字段名 key 视为凭据删除，会连带删除车型字段标识；开放模块data结构无法自动发现这一损坏。
- 有效修复：分离业务JSON字段过滤与URL query凭据过滤；发布后仍可按字段key读取配置与价格。
- 预防：投影验证须同时断言敏感数据被排除、必要业务字段仍存在；不能只做禁止字符串检查。
- 证据：T003开发期修复及2026-09-20独立Tester复核，.sdd/test-reports/test-T-003.md。其他摘要数值/国际联系方式缺陷仍在返工，不由本条经验推定通过。

## 追加式事实必须保留完整替代关系

- 关键词与适用条件：前端契约Mock、supersedes、预算连续更正、Unknown。
- 已证实根因：确认时删除中间冲突事实并丢失其祖先替代关系，旧confirmed预算会重新进入当前投影。
- 修复：保留所有历史节点，只追加新确认；提交完整祖先替代引用；提取、展示与报告复用currentFacts/reportFacts投影。
- 证据：T002返工1，2026-09-20独立Chrome复验4000→8001→Unknown及4项回归通过，.sdd/test-reports/test-T-002.md。仅证明本次前端状态层；全链真实接口另验。

## 摘要数字保护必须保留事实归属

- 关键词与适用条件：报告轻量审核、金额交换、摘要字段。
- 根因：仅比较数字集合不能发现月供和预算互换。
- 当前有效修复：按摘要字段、条目位置、完整含数字事实句保护，改变事实句须调整输入重新生成；普通无数字文字允许编辑。这是MVP保守限制，不声称能理解任意自然语言真假。
- 证据：T003返工1独立17项检查通过，.sdd/test-reports/test-T-003.md，2026-09-20。

## 联系方式输入与报告过滤保持同一范围

- 关键词与适用条件：国际手机号、已知客户身份、公开Report。
- 根因：身份允许国际号码，报告只用中国手机号正则，产生漏过滤。
- 修复：以客户规范化联系方式匹配分隔符和国际前缀形式，草稿生成、审核修改、发布三入口统一过滤，保留车辆金额与业务key。
- 证据：T003返工1，国际号六种格式及三个入口独立复验通过，.sdd/test-reports/test-T-003.md，2026-09-20。

## 金融末期舍入需在首付约束内继续求解

- 条件：Decimal按分舍入、期末吸收差额、月供硬上限。
- 根因及修复：仅试最低首付可能因最后一期差额假判无解；在合法首付区间有限搜索，并核对每期与末期。
- 证据：T004独立10000分/60期/101分上限算例，3999分首付、前59期100分、末期101分；test-T-004.md，2026-09-20。仅支持当前贷款规则及已测边界。

## 地图凭据脱敏覆盖HTTP库日志

- 条件：httpx INFO记录带query-key的高德请求URL。
- 修复：在该logger源头脱敏；用合成marker捕获真实日志同时断言秘密消失与REDACTED存在，不只检查业务logger。
- 证据：T004独立test-T-004.md，2026-09-20；不扩展成任意SDK全局脱敏保证。

## ASR时长上限先收尾，重启不续接音频

- 条件：客户端与服务端同时计时，PCM仍有在途片段，断连或应用重启。
- 修复：上限通知后有界接收在途片段，排空再finish；finish幂等；终态保存后通知客户端；启动时结束未终态ASR记录，不重放或自动重连，也不写业务输入。
- 证据：T004独立协议和schema检查，test-T-004.md，2026-09-20；不证明真语音准确率或真实麦克风行为。

## 空依据不能证明顾虑已解决

- 根因：all([])为真导致没有事件也放过已解决结论。
- 修复：先要求非空、可追溯确认来源，再核对逐项明确依据；无事件中性摘要仍可。
- 证据：T005返工1独立复验test-T-005.md，2026-09-20；未穷举任意自然语言同义表述。

## Unknown不抑制后来新关键值的确认

- 条件：旧预算Unknown，销售后来主动补充金额。
- 修复：Unknown只停止旧可选追问；新金额仍required，确认引用旧Unknown和新proposed完整替代，历史保留。
- 证据：T005返工1独立复验，三条历史保留而当前仅一个confirmed值，test-T-005.md，2026-09-20。

## 报告按候选及产品选择最新结果

- 关键词：artifact、双候选金融、Missing到Ready、固定报告。
- 根因：仅按模块类型去重会丢第二候选，保留首次产物会遮掉较新计算。
- 修复：先限定当前会话和revision、显式artifact_ids，再按候选/产品维度取最新；不同维度同时保留。
- 验证：T007独立真实HTTP与3项反例，覆盖多产品、显式IDs及stale/foreign排除；2026-09-20，.sdd/test-reports/test-T-007.md。

## 跨会话历史事实仅作参考

- 关键词：历史事实、确认引用、Unknown、会话归属。
- 根因：历史事实可覆盖本次值，提交旧会话fact_id会触发归属拒绝。
- 修复：本次值及Unknown优先；采用历史时创建本会话新事实，不提交跨会话确认引用。
- 验证：T007前端事实函数及真实HTTP独立验证；2026-09-20，.sdd/test-reports/test-T-007.md。


## 麦克风授权失败与ASR预留回收

- 关键词：Chrome SidePanel、NotAllowedError、AUDIO_ACTIVE、getUserMedia、created、迟到分配。
- 适用：侧栏首次麦克风授权、媒体初始化及异步取消。真实侧栏首次权限拒绝无弹窗，旧流程先分配ASR使created残留，重试被锁。
- 修复：媒体与Worklet成功后才申请预留；取消或卸载后的迟到create按原会话和原ASR ID释放，仅created可取消，拒绝抢占connecting/streaming/finishing。独立扩展授权页请求权限后立即停轨，不上传音频，不自动提交文字。
- 防复发：覆盖权限拒绝、构造器失败、Worklet/create迟到、同会话活跃锁及跨Origin取消；真实授权及转写另验。
- 来源：T010 ASR bugfix，2026-09-20；.sdd/bug_fix/asr-start-retry.md。自动恢复契约独立PASS，root实际侧栏重试无AUDIO_ACTIVE且授权页可达；真人转写仍待用户。


## 充电周边检索不要裸搜品牌名

- 关键词：高德 around、特斯拉充电、search_charging、门店过滤。
- 现象：关键词 Tesla/特斯拉命中门店与维修，再滤「充电」后为空。
- 修复：周边词直接用「特斯拉充电」「Tesla Supercharger」「超级充电站」，仍过滤非充电 POI，不填假站。
- 验证：T-008 独立 Tester v3.0，确认望京后 3 站+路线+静态图；`.sdd/test-reports/test-T-008.md` v3.0，`docs/evidence/external-integration/ac007-prepare-charging-r1.json`。
- 2026-09-20。

## 官方 uvicorn 启动必须带 WebSocket 库

- 关键词：uvicorn[standard]、websockets、API-022、No supported WebSocket library。
- 现象：仅 `uvicorn==0.53.0` 时 `/ws/sessions/.../audio/...` 无法升级，404。
- 修复：依赖声明 `uvicorn[standard]` 并装入项目 venv；协议握手有 `type=ready` 才算升级。不等于 Side Panel/真麦通过。
- 验证：T-008 Tester v3.0 `ac004-ws-r1.json`。2026-09-20。

## Unknown 再提取必须用本次原文，失败不能整段丢输入

- 关键词：INVALID_MODEL_OUTPUT、evidence_quote、unknown_support、supplement_facts。
- 现象：home_charging 已 unknown 后再提交「还是不知道」，引用不在本次原文导致整 run 失败。
- 修复：跳过非本次原文引用；已 unknown 不重提；契约失败兜底并返回 unknown_support；已提交文字保留。
- 验证：T-008 Tester v3.0 `ac005-unknown-r1.json`。2026-09-20。


## prepare 定性摘要数字不能整单失败

- 关键词：UNVERIFIED_SUMMARY_NUMBER、qualitative_summary、prepare_report、report_summary。
- 现象：真模型把月供/候选价写入 comparing/confirmed 后整 run failed，已成功金融/地图产物被丢掉。
- 修复：数字只留确定性模块；定性摘要去数字或再 Finish 一次；仍含数字则剥离后保存草稿。摘要可能残留「英寸轮毂」等残片。
- 验证：T-008 独立 Tester v4.0，齐全案 succeeded 有 draft；`.sdd/test-reports/test-T-008.md`，`docs/evidence/external-integration/ac013-complete-r2.json`。2026-09-20。

## prepare 无阻塞确认不能挡住草稿

- 关键词：needs_confirmation、search_charging ready、optional questions。
- 现象：无车位确认望京并查站成功后仍 needs_confirmation、无 draft。
- 修复：prepare 无 blocking issue 且地点非未确认歧义时强制出草稿，可选问写入 pending。
- 验证：T-008 Tester v4.0，`t008-retest-r2-confirm-center-summary.json`。2026-09-20。


## 发布后跟进必须单独收口并读会话对象

- 关键词：intent=followup、AC-020、source_event_ids、followup.brief、INVALID_MODEL_OUTPUT。
- 现象：跟进复用报告提取的 Capture/Fact source_ids 导致契约失败整 run 挂掉；或 run 成功但 GET /sessions 的 brief 空、事件 ID 对不上本轮注入。
- 修复：跟进不走充电/金融工具；source_ids 只用 Mock 事件 ID；契约失败用中性简报兜底；把 brief（非空字符串）和 source_event_ids 写入 session.followup。验收读 GET /sessions，不读 run.result。无 resolution_evidence 不得 resolved。
- 验证：T-008 Tester v5.0，`.sdd/test-reports/test-T-008.md`，`docs/evidence/external-integration/ac020-family-charging-followup-r5.json`、`ac020-budget-followup-r5.json`。2026-09-20。
