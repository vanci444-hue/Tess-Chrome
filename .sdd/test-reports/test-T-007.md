| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-007 本机接口、报告持久化与业务契约独立验收 |
| 版本 | v1.0 |

**结果：PASS（本地 API / 数据契约阶段）。** 正式工厂的真实 Uvicorn HTTP 链路、隔离数据、计算、发布及重启验证通过。模型为显式协议替身，采集输入为 T-001 真实官网快照；未把本结果称作真实模型或浏览器完整业务通过。

## 环境与授权

- Tester：backend_test。项目 `/Users/zhaojiaqi/Documents/evanSDDKit/Projects_Repo/tess-chrome`；Python 3.12 .venv、pytest-timeout、FastAPI/SQLAlchemy/SQLite、Node。
- 已核验 `docs/evidence/local-integration/frozen-sha256.json` 全部 18 项文件一致；完整指纹直接引用该文件，未重建业务代码。
- dispatcher errors=[]，但通用前端门禁 awaiting_user；本轮依用户明确委托独立验收并继续全部开发及 tasks.execution_authorization 例外执行，不伪造用户亲验或 Key 配置。T-007 当前 acceptanceCriteria=[]；完整原业务 AC 已交 T-010。
- 真实 HTTP 使用正式 create_demo_app、127.0.0.1:8003、pytest tmp_path 数据库；启动与关闭的是测试自有 Uvicorn。保留生产 8099 服务，仅只读检查；默认 customers/sessions/captures/reports 仍全部 0。

## 逐项 technicalChecks

| 检查 | 结果 | 独立证据 |
|---|---|---|
| 两客户/复访会话隔离、三候选、revision、幂等、重启与来源 | PASS（接口/数据） | 正式 Uvicorn 导入白色20/19英寸两份真实fixture→确认→Agent协议回放调用本地工具→草稿审核→发布→重复发布同ID单卡→关闭并新建服务→旧JSON、来源时间不变。修改预算后草稿stale、发布409；另客户/同客新会话不获得旧候选；跨会话修改候选404；第4候选409且旧数组未改。 |
| Origin、隐私与插件通信契约 | PASS（静态/HTTP部分） | 未知网页Origin、未知扩展Origin、恶意Host拒绝403；正式扩展Origin允许写入隔离客户；报告无测试邮箱。正式manifest权限/CSP/固定公钥ID及后端白名单一致；实际 Chrome 安装与权限执行未验，归T010。 |
| 独立复算金融/能源、报告图表数据及无Key | PASS（确定性/渲染契约） | 双候选金融同时保留；A最新48期取代其旧60期，B60期保留；Mock来源不升级官方。独立使用333333分月供、48期：本金15999984分，首付16150016分，普通及末期月供均333333分。另以12345km、4年、电耗17.4、电价1.35、油耗8.6、油价7.8独立Decimal复算，报告最终saving_fen一致。无地图Key返回Missing；无模型Key保存原始已提交文字并failed；ASR缺配置503。SSR验证金额单位、能源假设、图表SVG、缺失不补0。 |
| 原AC001真实来源 | PASS（来源回归） | 只复用T001真实官网JSON；构建capture.js与已验extension/capture.js字节一致，SHA为98dc7661…0187b。未使用Mock官网、未重做真实采集；AC001完整浏览器责任仍在T010。 |
| API与浏览器证据分开 | PASS | 本报告逐项标注方法及未验项，不以HTTP或SSR代表页面交互/视觉/麦克风。 |
| Settings、配置键、固定扩展ID和静态入口 | PASS | Settings全部51字段在.env.example及本地.env有对应键，本地无示例未列键；MAP_IMAGE_WIDTH/HEIGHT/MAX_BYTES/PAGE_SIZE均存在，只输出键覆盖状态。manifest公钥推导ejbpocfjkdofijfgehnnhdnnhigkekdn，与identity和ALLOWED_EXTENSION_ORIGIN一致；frontend/dist路径可用。8099根页面、引用资源及health返回正确，capabilities全missing。 |

## 实际执行

```sh
.venv/bin/python -m pytest backend/tests/integration --timeout=120 -q --disable-warnings --tb=short --show-capture=no
# 4 passed，2.06s；包括真实 Uvicorn HTTP 启停/重启。
.venv/bin/python -m pytest .sdd/test-reports/test_t007_independent.py --timeout=120 -q --disable-warnings --tb=short --show-capture=no
# 初始独立2项：2 passed，0.98s。
.venv/bin/python -m pytest .sdd/test-reports/test_t007_independent.py --timeout=120 -q --disable-warnings --tb=short --show-capture=no -k calculations
# 新增独立复算项：1 passed，0.73s；未重复已过2项。
cd frontend
node --experimental-strip-types --test src/utils/facts.test.ts
# 4 passed。
npm run test:report
# PASS report SSR；不是浏览器视觉。
```

另通过内联只读检查完成18文件SHA、51配置字段、公钥→扩展ID、Capture字节一致、8099 HTTP入口/静态资源/健康和默认库计数断言。未输出配置密钥。开发者同版100后端、类型/lint/build、启动器占端口安全退出证据沿用交接记录，未无目的全量重跑。

## 已验证修复与经验建议

**按候选/产品/时间选取报告产物，不能只按模块类型去重。** 原实现可能丢第二候选或展示旧计算。独立测试在同revision创建A-p1旧/新、A-p2、B-p1，加更新的stale、错revision、其他会话记录，默认结果精确为A-p1新、A-p2、B-p1；显式artifact_ids选择旧A-p1和A-p2时准确尊重选择。既有集成复验Missing→Ready及显式选择旧Missing也通过。可沉淀范围为当前本机报告artifact选择；时间相同的ID次序不代表业务语义新旧，未扩展声称通用分布式排序。

**跨会话历史只作参考，采用时新建本次事实。** 原API006末尾历史值可能覆盖本次Unknown，且把历史fact_id/supersedes提交当前会话会404。前端currentFacts/confirmationReferences四项测试通过；独立真实HTTP确认跨会话旧ID被拒，本次无旧引用创建Unknown成功，原会话400000分未变化，另一客户facts为空。前端采用历史时fact_id为空、supersedes为空；本次Unknown优先于历史值。根因和当前修复已验证，可由编排器去重沉淀，未验证真实点击呈现。

## 明确未验

- T010：正式插件在Chrome加载、实际权限、侧栏操作与360/420/480布局、桌面Report视觉、新标签跳转、真实地图外链等完整用户路径。沿用已有Chrome工具失败记录，不重复操作/安装。
- T008：真实Qwen响应、麦克风与实时ASR、真实高德POI/地图/外链数据。当前Key均Missing，协议替身和SSR不替代真实验证。
- T001已验真实官网Capture，不代表正式全功能扩展已在Chrome独立完成全链路验收。

本轮未发现需返工缺陷；仅写测试报告与独立证据脚本，未改业务、任务状态或经验库。测试8003已关闭；生产8099保留。
