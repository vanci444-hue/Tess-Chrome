| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | 实时转写初始化失败与重试锁定的独立定向验收 |
| 版本 | v1.0 |

## 结论

PASS（本轮 ASR 初始化、取消、重试与权限恢复入口的自动契约范围）。T-010 整体及真人语音识别准确率不在此 PASS 内；真实麦克风允许后的逐字转写仍待用户配合。未修改业务代码、tasks、真实数据库或密钥。所有服务测试使用临时隔离 SQLite 与 FakeProvider，不访问真实供应商。

编排器提供的原故障：Side Panel 未弹权限即 NotAllowedError，先创建的 ASR 记录停在 created，随后点击返回 AUDIO_ACTIVE。用户确认没有授权提示。当前实现将本地权限及 Worklet 初始化放在 create 之前，并只取消属于原 session/asr ID 的未连接预留。

## 验收依据与范围

PRD AC-004、006、025、042；tech-spec API-009、022；当前 T-010 音频 technicalChecks。dispatcher errors=[]，旧 T-006 门禁仍显示 awaiting_user；本次仅按编排器记录的用户自动修复授权验现有故障，不代填门禁。已有经验“ASR时长上限先收尾，重启不续接音频”保持适用边界。

| 检查 | 结果 | 实际证据 |
|---|---|---|
| 权限拒绝不分配 ASR，保留手工文字，显示恢复状态 | PASS | hook 注入 NotAllowedError；create 调用数为 0，phase=failed，permissionDenied=true，原文字不变 |
| Worklet/AudioContext 初始化失败释放媒体 | PASS | Worklet 失败 stop=1、close=1、create=0；独立补测 constructor 抛错 stop=1、create=0 |
| 权限未返回时取消；初始化期间卸载 | PASS | 迟到 stream 停止，不 create；独立补测 pending Worklet 卸载后 stop/close 各一次，无 create |
| create 迟到，取消/卸载/手改不得串会话 | PASS | finish、独立 unmount、独立 edit 三路径都按原 s + 对应 asr ID 取消，无 WebSocket 创建；手改后的文字不被覆盖 |
| 重复开始及连接错误可重试 | PASS | 活跃中重复 start 仅一次 create；WS error 后原预留定向取消，媒体停止，显式再次 start 可分配 |
| HTTP 取消归属、幂等与并发保护 | PASS | 跨 session 404 后原锁仍存在；created 取消为 discarded，重复取消 200，新分配 201；真 FakeProvider WS streaming 中取消 409且流继续 |
| 不抢占活跃状态 | PASS | 独立参数化 connecting/streaming/finishing：DELETE 均409，DB原状态不变，再次分配仍409，不打开上游 |
| DELETE CORS | PASS | 允许 Origin OPTIONS 返回200，allow-methods 含DELETE；不受信 Origin 403且无 allow-origin |
| 授权辅助页无业务调用 | PASS（自动/静态） | VM 分别执行允许、拒绝、pagehide后迟到授权；允许/迟到均 stop=1；拒绝可重试。脚本只操作媒体和DOM，无 fetch、WS、存储、ASR或业务发送；dist两个文件与源逐字一致 |
| 不自动发送、手改/迟到保护、PCM协议 | PASS（本地协议） | 既有14前端测试及24后端ASR/schema检查；服务正常finish后 Fact/SalesInput/TimelineMessage数量0，手改冻结及旧generation忽略，PCM16k mono、finish边界通过 |
| 真人允许后持续转写、尾句、语音准确性 | 未验 | 本次独立Tester不操作Chrome/真人麦克风；由编排器与用户继续实测 |

## 实际执行

- 项目根：`.venv/bin/python -m pytest backend/tests/adapters/test_asr.py backend/tests/core/test_asr_schema.py --timeout=30 -q --disable-warnings` → **24 passed**。
- frontend：`node scripts/test-asr-lifecycle.mjs` → **5 lifecycle cases passed**。
- frontend：`npm test` → **14 passed**。
- 独立补充：复用 lifecycle harness、追加 constructor failure / worklet-unmount / create-unmount / pending-edit 共4场景，Node assert 全通过；未修改现有脚本。
- 独立隔离 pytest：3个活跃状态保护通过；DELETE CORS及不受信来源检查通过。临时测试文件与DB在退出后清理。
- 授权页独立 VM：允许/拒绝/离页后迟到共3情形，assert通过；产物与源一致。
- Developer 的 typecheck/lint/build、定向 mypy 成功证据已交接，本轮未机械重复全部构建。

验收脚本调整记录：一次 Node eval 顶层 await 包装错误，改为 async wrapper 后通过。独立 CORS 负例初写预期400，实际为本机边界既定403；定向核对 main.py 的 INVALID_ORIGIN 返回403后按既有契约复验通过。这两项均为验收脚本问题，未修改产品或放宽业务约束。

## 本轮版本指纹

| 路径 | SHA256 |
|---|---|
| frontend/src/hooks/useRealtimeAsr.ts | 87ee25ba4ba28ead0626e5f9214437fac9423ee96a384d2dc2281c88579c143f |
| frontend/src/components/Composer.tsx | 87c31ec072405b47e5d6e5fa70dea49785de0cd28fb1c734226a724ad4f209e9 |
| frontend/src/services/audio.ts | 6290c947d8d5e51b351a32650c53aacafb086b36738902798b9ace7b0278f990 |
| frontend/public/microphone-permission.html | ff3db29667e9acdaca7c70be9f19f3c6439b074692af183619b453a6834a963f |
| frontend/public/microphone-permission.js | 91d8dc7a235dd85b74ff597664f845237569f08a5265f502744424463f54f3cb |
| backend/src/services/asr.py | 071e14422b74da96ab7e9254f76c1a87ad1f92b8271ddad28b3642bc3895803b |
| backend/src/api/routes/audio.py | bd7bd81d33d76b743f541ea722a1556b69888d8cdf452a204af932ce7f178aa9 |
| backend/src/main.py | 20a8743591a6e88627c499782e0ec42ee05018d46a4c5c28494ff0ad4e46a864 |

## 编排器补充的实际浏览器证据

以下由 root 实际操作并于本轮消息交接，非本 Tester 重复执行：已重启8099、reload正式扩展；原会话连续两次点实时转写，均显示权限拒绝与授权页入口，无 AUDIO_ACTIVE；只读数据库两条旧记录为 failed，无新增 created；授权入口打开同扩展 microphone-permission.html，允许按钮和隐私说明可见。用户尚需自行允许，不能将此证据写成真人ASR通过。

## 根因与经验候选核对

- 已验证：先完成本地媒体初始化再预留连接，可以在权限/Worklet失败时避免服务端锁泄漏；取消与卸载的迟到分配按原归属定向释放；HTTP不得抢占已连接状态。建议由编排器在项目经验记录此生命周期规则。
- 已有现场证据：该用户此Chrome Side Panel首授权未弹且返回NotAllowedError。不能将其泛化为所有Chrome/所有扩展侧栏必然无法弹权限，也不能据此断言操作系统权限正常。
- 尚未验证：独立授权页允许后侧栏真实麦克风能否持续识别及真实语音准确性。无需因此否定本轮自动恢复契约通过，但不得宣称完整AC-004或T-010通过。
