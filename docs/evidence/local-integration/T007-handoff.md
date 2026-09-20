| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T007 正式装配、本机 HTTP 持久化联调与启动交接 |
| 版本 | v1.0 |

本记录为开发自验，不替代独立 Tester 或真实浏览器验收。

## 当前可运行入口

在项目根目录运行 `scripts/build-demo.sh`，随后运行 `scripts/run-demo.sh`；macOS 可双击 `启动Tess.command`。依赖仅安装至项目 `.venv`、`frontend/node_modules`，不会安装外部 PyCore 包。脚本不会结束占用端口的进程。服务仅绑定 `127.0.0.1:8099`。

正式服务已通过脚本启动并保留，终端会话 ID 为 52907。访问 `http://127.0.0.1:8099` 可看到销售界面，固定报告使用同域 `/reports/{id}`。默认数据库未创建测试客户或测试报告；当前 LLM、ASR、Maps 均为 Missing，健康接口准确标记 degraded。

Chrome 加载目录为 `frontend/dist`，正式扩展 ID 为 `ejbpocfjkdofijfgehnnhdnnhigkekdn`。ID 由 `frontend/extension-identity.json` 中公开公钥固定；没有保存私钥。后端 `.env` 仅将已知 spike 来源替换为正式 ID、补入缺省参数，保留其他现有值。该机制依据 [Chrome 官方 manifest key 文档](https://developer.chrome.com/docs/extensions/reference/manifest/key)。未操作 Chrome profile、未声称正式扩展已安装成功。

## 实现与发现的修复

- `backend/src/main.py` 新增 `create_demo_app`，一次装配 runs/audio/Agent/CRM/draft editor 和生命周期。全局生产 app 使用完整工厂；基础 `create_app` 保留模块测试兼容。`/`、`/index.html`、`/reports/{id}`、`/assets` 对应正式构建。
- `backend/src/services/reports.py` 修复按模块类型去重导致第二候选金融结果丢失、早期结果覆盖新结果。现在先限定显式 artifact IDs，再按候选和金融产品取最新当前 revision 结果；地图、能源取最新，家庭按 topic。来源 ID 去重，快照仍不可变。
- `frontend/src/utils/facts.ts`、`ContextCard.tsx` 修复 API006 追加的历史事实覆盖本次同字段事实，以及把跨会话 fact_id/supersedes 送入确认接口导致 404 的问题。历史采用时创建本次新事实，不修改旧会话；本次 Unknown 也优先于历史值。新增测试覆盖引用边界与 Unknown。
- `ReviewCard.tsx` 将中文数字与服务端相同的只读规则同步；`services/api.ts`、`services/tess.ts` 让同步 CRM 提取等待覆盖后端默认模型超时，其他请求仍使用短超时。
- 正式构建复制经过真实官网验证的 Capture 脚本，SHA256 仍为 `98dc7661ebbd35de59ae99c1ea04ff90c0c70ae8f6776fef7778f8971430187b`。未修改 spike、未制作 Mock 官网。

## 复验命令与证据

均在项目根目录执行，前端命令进入 `frontend`。所有 Python 测试使用隔离临时数据库，不清空默认库。

| 检查 | 命令 / 证据 | 结果 |
|---|---|---|
| 后端完整回归 | `.venv/bin/pytest backend/tests --timeout=120 -q`；`backend-tests.txt` | 100 passed |
| 新增正式装配 HTTP 联调 | `.venv/bin/pytest backend/tests/integration --timeout=120 -q` | 4 passed，包含在上行 |
| 既有独立回归 | `.venv/bin/pytest .sdd/test-reports/test_t003_independent.py .sdd/test-reports/test_t005_independent.py --timeout=120 -q`；`independent-regression.txt` | 9 passed |
| Python 质量 | `.venv/bin/ruff check backend/src backend/tests/integration`；`.venv/bin/mypy backend/src`；`.venv/bin/pip check` | PASS，41 源文件 |
| 前端 | `npm run type-check`、`npm run lint`、`npm test`、`npm run test:report`、`npm run build` | PASS，14 测试 + Report SSR |
| ASR 真实 hook 协议回放 | 在 frontend 执行 `node ../.sdd/test-reports/t006-audio-protocol.cjs`；`audio-protocol.txt` | PASS；非真实麦克风 |
| 启动脚本完整构建 | `scripts/build-demo.sh`；`build.txt` | PASS |
| 8099 生产 HTTP | `startup.json` | root、静态资源、health、正式 API 路由 PASS |
| 端口已占用处理 | 再运行 `scripts/run-demo.sh`；`port-occupied.txt` | 明确失败退出 1，不结束现有服务 |
| 配置 / 构建 | `.env.example` 包含所有 Settings 字段；manifest ID、Capture 文件摘要一致；`bash -n` 三个启动脚本 | PASS |

`backend/tests/integration/test_local_http.py` 第一个用例实际启动 Uvicorn 8003，并通过 httpx 进行建档、两份真实 T001 Capture 数据入库、确认上下文、Agent 工具执行、审核、发布、重启、历史查询。测试显式注入协议 Provider；金融规则仍标 Mock，能源标 Estimate，高德无 Key 明确 Missing，模型和地图均未真实调用。测试结束关闭自己创建的 8003 服务，SQLite 与上传目录归 pytest tmp_path 管理。

覆盖结果包含：双候选同时保留；同候选 60→48 期最新试算；金额与末期月供上限；能源 5 年节约 4,600,000 分；原始 Capture 字段及来源时刻；重复发布同 ID 单卡；跨会话引用拒绝；输入变化草稿 stale；固定链接重启后内容不变；Unknown 后新金额仍需强确认；续跑幂等与 lineage；迟到模型结果不覆盖新 revision；Missing→Ready；显式 artifact_ids 优先；缺 Key 时保留已提交文字、ASR 返回缺配置。

## 未验与交接边界

真实 Qwen、真实 ASR、真实高德调用未验：项目未配置对应 Key，不将协议回放描述为实测。真实麦克风、正式插件在 Chrome 中的安装及全链路视觉操作留 T008/T010；沿用主流程已确认的 Chrome 工具不可用结论，不重复安装浏览器工具。真实官网 Capture 本身已由 T001 独立验证，本轮复用该采集证据作接口联调。

建议沉淀：报告产物不能仅按模块类型去重，必须考虑候选/产品维度和来源 revision；跨会话历史参考不应携带其他会话的事实 ID 发起原地修改。由 Tester 核实后交编排器决定是否落经验库。
