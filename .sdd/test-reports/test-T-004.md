| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-004 服务 Adapter、确定性工具与实时 ASR 后端协议独立验收 |
| 版本 | v1.0 |

## 结果

**PASS（T-004 技术范围；外部传输使用可控替身，不代表真实供应商服务已验收）。**

任务 `acceptanceCriteria=[]`；本轮按五项 technicalChecks 验证。真实 ASR 识别质量、真实高德响应与静态图、真实百炼模型能力归 T-008，本轮未调用真实供应商、未使用或打印真实 Key。前端采音、人工编辑和导航行为不在本次后端协议验收范围。

调度器返回 `tester_ready=[T-004,T-005]`、`errors=[]`，执行模式 automatic，T-003 已通过。本轮仅增加独立测试和本报告，未修改业务代码或任务状态。所有数据库均来自 pytest `tmp_path`，没有启动/修改演示服务或使用业务库。

## 实际执行

工作目录：`Projects_Repo/tess-chrome`；项目 `.venv` Python 3.12，带 pytest-timeout。

- `.venv/bin/python -m pytest backend/tests/adapters backend/tests/tools backend/tests/core/test_asr_schema.py --timeout=120 -q`：**36 passed，2.64s**（添加 Tester 用例之前的冻结开发范围）。
- `.venv/bin/python -m pytest backend/tests/adapters/test_t004_independent.py backend/tests/tools/test_t004_location.py --timeout=120 -q`：7 项通过；地点附加用例初始夹具引用不存在的会话，被外键正确拒绝。补齐临时外会话后单独复验地点用例 **1 passed，0.35s**，合计 **8 个独立补充场景通过**。
- Tester 的超时用例首次遗漏了模拟 base URL，收到预期的 `LLM_NOT_CONFIGURED`；补齐仅指向 `example.test` 的 MockTransport 配置后得到 `LLM_TIMEOUT`，请求计数为 1。两项均为测试夹具修正，无业务改动。
- 范围内 ruff：`All checks passed!`；mypy（adapters、tools、audio route、ASR service）：`Success: no issues found in 9 source files`。
- 定向检查全部外部 httpx/aiohttp 客户端均 `trust_env=False`；ASR 路径未发现音频文件写入；地图资产写入在会话/revision 检查之后。

## 逐项结果

| 检查 | 场景与实际结果 | 证据 | 判定 |
|---|---|---|---|
| TC-06 金融与能源 | 真实 Capture 的车价单位 CNY_fen 正确读取；32150000 分、首付 7990000 分、60 期得本金 24160000 分，普通月供 402667 分、末期 402647 分，总分期等于本金；独立逐月账本核对等额本息、融资费用不重复计入。费用缺失、优惠与车价冲突、未知费率口径拒算，无解不放宽条件。计算前后原 Capture 不变，Mock 金融不标官方。 | `test_calculations.py` 全 6 项、`test_registry.py::test_real_capture_fen_and_source_label`、`test_t004_independent.py::test_independent_payment_oracle` | PASS |
| TC-06 末期硬约束 | 车价 10000 分、产品最低首付比例 .3971、60 期、月供上限 101 分：得到最低可行首付 3999 分、普通月供 100 分、末期 101 分，不误判无解。 | `test_calculations.py::test_rounding_cap_can_increase_down_payment_instead_of_false_no_solution` | PASS |
| TC-06 能源来源 | 全部 7 项假设保留；20000 km/年、5 年、15 kWh/100km、1.5 元/kWh、10 L/100km、8 元/L 算出年电费 450000 分、燃油费 1600000 分、5 年差额 5750000 分；缺参数拒算，限制周期防无界数组。报告模块标 estimate，来源写明“未核验为销售已确认事实”，仅能源成本。 | `test_calculations.py::test_energy_independent_arithmetic_and_all_assumptions`、`test_t004_location.py` | PASS |
| TC-05 地点与距离 | 同名地点保留全部候选；确认前拒用 ID，已被 supersedes 替代的旧确认和其他会话候选拒用；当前已确认地点可继续。GCJ-02 坐标保留，充电设施证据过滤 Tesla 体验店，数字距离排序、去重、排除半径外站点。驾车结果 2560 米/540 秒与中心点距离分开。 | `test_providers.py` 地图场景、`test_registry.py::test_ambiguous_confirmed_ref_required_partial_map`、`test_t004_location.py`、`test_t004_independent.py::test_map_route_marker_correspondence_and_payload_size` | PASS |
| TC-05 部分失败 / Missing | 路线失败保留站点与中心点距离、驾驶时间为 null；静态图失败保留列表且 map_asset_id=null；缺 Key 显式未配置，不生成示例站点。未知知识主题为 missing，无伪造来源。 | `test_registry.py`、`test_providers.py::test_missing_configuration_never_generates_mock_success`、`test_t004_location.py` | PASS |
| TC-17 ASR 生命周期 | HTTP 分配幂等、单次 ID、TTL、会话归属、Origin 拦截；配置必须等 session.updated 才完成，session.created 不算 ready；PCM/16000/server_vad，append 后 session.finish，不发 commit。重复 partial、迟到 partial 不重复最终句；停止、finish、断开、discard 后 Fact/SalesInput/Timeline 均保持零记录。 | `test_asr.py`、`test_t004_independent.py` 配置确认/资源清理/缺配置场景 | PASS |
| TC-17 有界失败与尾段 | 奇数字节 PCM 返回协议错误并 close1008；上游阻塞超出 2 秒缓冲报背压；收尾超时报 ASR_FINISH_TIMEOUT。时长上限先 incomplete=false 提示，允许窗口内在途 PCM，finish 幂等，收到 partial→final→finished。客户端断开/放弃释放上游，保存 ASR 终态且无音频文件。正常 finished 在通知客户端前已持久化（代码检查与最终库值相符）。 | `test_asr.py` 背压/超时/时长用例、`test_t004_independent.py` 断连与放弃用例、`services/asr.py` | PASS |
| 密钥、地图资产与链接 | httpx INFO 使用合成 marker Key 抓日志，URL 已替换 REDACTED；外链固定高德搜索白名单，仅地点查询参数，无 Key/center，电话型参数拒绝。静态图检查 MIME/文件头/大小，编号 1 与同一站点坐标对应；Asset 归属当前 session、来源不含 Key，输出本地 asset_id。 | `test_providers.py::test_httpx_info_log_redacts_query_key`、地图外链测试、`test_registry.py` 资产断言、`test_t004_independent.py` 编号/大小断言 | PASS |
| ASR schema / 重启 | 旧表原位加 nullable language，rootpage 不变、原记录不丢；新表保留 zh；重复初始化不重复列、不刷新终态时间。created/connecting/streaming/finishing 重启后 failed/ASR_INTERRUPTED，finished/failed/discarded 保持原状态，SalesInput/Fact 不改。 | `backend/tests/core/test_asr_schema.py` 16 个参数化场景 | PASS |

LLM Adapter 额外核对：标准 model/messages/tool_calls 契约，缺配置拒绝，超时无自动重试且错误不含供应商原始正文。见 `test_providers.py::test_llm_exact_model_standard_tool_calls_no_retry`、`test_t004_independent.py::test_llm_timeout_is_single_attempt_and_safe_error`。

## 修复经验核对

- **已验证，可建议沉淀**：金融硬约束必须核对末期舍入；指定 10000 分算例确认为 3999/100/101，当前修复消除了该案例的假无解。不据此声称已穷举所有贷款规则。
- **已验证，可建议沉淀**：高德 URL 的 Key 还会经过 httpx INFO 日志；使用合成 marker 的真实日志捕获验证了 `QueryKeyRedactor` 的脱敏效果。仅适用于当前 httpx logger 与 query-key 形式，不扩张成任意 SDK 全局脱敏保证。
- **已验证，可建议沉淀**：时长上限先通知、保留有限在途窗口、排空后 finish；原场景完成 partial/final/finished，重复 finish 不失败。这里证明协议状态与尾段次序，不证明真实网络/语音准确率。
- **已验证**：旧 SQLite 增量列与启动时结束遗留 ASR 活动记录，保持业务输入和事实不变。原业务状态不可被“恢复录音”覆盖。

上述仅提交建议，由编排器决定去重与写入经验库。

## 版本证据与未验范围

关键 SHA-256：

| 文件 | SHA-256 |
|---|---|
| backend/src/tools/finance.py | c729ddcb9197ba4593c7d36df1afb74f314401ca68a1debb3a53f0135b7ee1a2 |
| backend/src/tools/registry.py | 0f586f93250a279353b9cc186f1196c6b833d93c758fd674f2bdbaf675bfe2a9 |
| backend/src/services/asr.py | 0579a0398851ead6fd4bb14e645c92c2fe4d85b9db0517b0cd8166cfdfed5a76 |
| backend/src/adapters/asr.py | e3697d9576e2fd62d74015a58a0c7b4b488379b2a3d0a7cea7e586e29ae9a3fc |
| backend/src/adapters/amap.py | f352b155715237a35636a262b59be53ed828684bc00f3510c2da5012ababfd4c |
| backend/src/adapters/base.py | b69960f41786b49dd46030ab738722721fe658ef869c73b3b8f96a3028a4e701 |
| backend/src/db/session.py | 6b36f866853a51f5e50fe18ae97b5966904686c7d298cc011a36e461f9e1dd7d |

真实服务 Key 未配置，T-008 对应真实 AC 尚未验收；不能将本报告用于宣称 AC-004/007 等真实服务场景已 PASS。真实浏览器麦克风授权、AudioWorklet、手工输入防晚到覆盖、真实地图外页点击另由前端/集成任务承担。现有 PyCore/Pydantic/Starlette 弃用警告不影响上述断言，未为此修改框架依赖。
