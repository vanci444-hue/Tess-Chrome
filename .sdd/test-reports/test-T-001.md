| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-001 真实官网 Capture 独立可行性验收 |
| 版本 | v1.0 |
| 结果 | PASS（前端 Capture spike，真实官网）；real_supported |

本任务 acceptanceCriteria 为空，按四项 technicalChecks 验收；完整业务 AC-001—003、025、037 仍由 T-007 验收。本结果不代表完整项目或真实 ASR/地图/模型已通过。

## 环境及范围

- 实际 Chrome 已安装扩展 ID `ppchdkpblgbelpjcpkgkgifpnmenampm`，manifest 0.1.1；导出适配器 `tesla-cn-modely-dom/0.1.1`。
- 目标 `https://www.tesla.cn/modely/design#overview`，真实网页，无 Mock 官网。界面中销售身份明确标 Mock。
- Tester 独占 native Chrome，使用 cua_repl getApp、AX 与截图交叉检查。未访问其他标签内容、未下单、未改账号。
- 测试使用本机演示身份及独立会话 `tester-capture-02`，不接 CRM 或后端。
- 调度脚本返回 errors=[]、tester_ready=[T-001]，automatic。业务代码未修改。

## 技术检查结果

| 检查 | 结果 | 实际证据 |
|---|---|---|
| 原生 Side Panel、精确站点范围及有限读取 | PASS | 实际官网右侧展示 extension sidepanel.html；service-worker 与 capture 双重限制 HTTPS、www.tesla.cn、/modely/design、top frame；定向读取源码无 Cookie、token、网络上传或全量 window 对象读取。host permission 按 Chrome 实际机制覆盖 host，执行时 path 再过滤。 |
| 两套配置真实变化、金融只读可见字段 | PASS | 独立将全驱白20轮毂切到19轮毂，官网与新抓取一致，见下表。关闭金融面板抓取时无金融字段，提示展开后重新 Capture；没有继承上一份月供。 |
| URL、时间、原文证据、500ms指纹、旧快照、JSON | PASS | 两份独立下载JSON均包含 source_url/captured_at/raw_text/evidence；readiness=ready，first_fingerprint=second_fingerprint=page_fingerprint。切换后旧卡仍321500/690/4027。导出不含演示联系方式、会话身份。 |
| 有证据可行性结论及真实/Mock区分 | PASS | real_supported。真实捕获闭环已成立，无需启用备用 Mock 官网；原网页配置数据并非固定 fixture。 |

## 独立逐字段对照

金额单位在 JSON 中为 CNY_fen，以下按元显示。两个完整快照均由 Tester 点击 Capture、下载并用脚本断言来源/版本/指纹。

| 字段 | 全驱白20（03:34:56） | 全驱白19（03:36:10） |
|---|---|---|
| 版本 | 长续航全轮驱动版 | 长续航全轮驱动版 |
| 外观 | 珍珠白（多涂层） | 珍珠白（多涂层） |
| 轮毂 | 20 英寸螺旋风暴 | 19 英寸交互风暴 |
| 内饰 / 座位 / 辅助驾驶 | 深色 / 五座 / 基础 | 深色 / 五座 / 基础 |
| 配件 | 未勾选，无额外选配 | 未勾选，无额外选配 |
| 当前车辆总价 | 321500 | 313500 |
| CLTC / 最高速 / 加速 | 690km / 201kmh / 4.3s | 750km / 201kmh / 4.3s |
| 交付窗口 | 5–7周 | 5–7周 |
| 金融产品 | 限时0息贷款方案 | 限时0息贷款方案 |
| 首付 / 本金 | 79900 / 241600 | 79900 / 233600 |
| 期限 / 月供 / 年化费率 | 60月 / 4027 / 0% | 60月 / 3894 / 0% |

官网存在限时车漆福利，所以不把车型标价与所有选配标价简单相加当总价；读取官网实际车辆价格。首付+本金与车辆价格均严格一致。字段值与当时网页相符，不代表未来价格。

## 可复查证据

- `/Users/zhaojiaqi/Downloads/tess-capture-2026-09-19T19-34-56.593Z.json`，SHA256 `77d4def94f4139580d17493277e5a1d4c17269812df1724636c0001c293ec8ab`。
- `/Users/zhaojiaqi/Downloads/tess-capture-2026-09-19T19-36-10.833Z.json`，SHA256 `510e5e0d9747b593d3b537b1d1843b5cd0e78cb74c4ddf2cb272c605e7227f3f`。
- 原编排器证据 `docs/evidence/capture-spike/raw-0.1.0.json` 与 `raw-0.1.1-awd-white20.json` 仅辅助：原会话3份旧记录仍保留，含后驱灰19总价263500。旧0.1.0缺项未因升级被静默改写。本次通过主要依据独立0.1.1操作。
- CUA 工具记录包含两次真实金融截图、官网选中态AX、Capture新增卡及下载完成记录。截图仅在工具记录内，未保存成项目PNG。
- `node --test extension/tests/capture.test.cjs`：6/6 PASS，退出0。覆盖总价与月供区分、配置变化不改旧投影、金融缺失、金额精度、真实诊断回放及配件未选/缺失区别；它不替代真实UI验收。
- 文件SHA256：capture.js `98dc7661ebbd35de59ae99c1ea04ff90c0c70ae8f6776fef7778f8971430187b`；sidepanel.js `ad305888ad3005cac35ddc907bcb24854c45c9072d94894eed2e087a818fd102`；service-worker.js `d17cff4d55446a2524d53d1722894e0f13e33a5068bc3b4b717ceb9df7ba1985`。

## 后续边界与改进

- 3/3时Capture按钮已禁用，尝试点击没有新增或覆盖；但页面未显示“请先移除一个”的行动提示。该业务文案在T-002/T-007正式AC-003必须补验。
- 金融未展开时有明确warning，但卡片仍写“字段完整”（当前含义为核心配置完整）。正式界面建议改为“车辆配置完整，金融待读取”，避免歧义。
- 更新中拒绝保存的实现已读，未在本轮主动制造真实DOM更新竞态；错误页面拒绝的精确host/path代码已核对，未另开错误页实操。这些全业务异常由T-007补验，不把静态核对写成真实UI通过。
- 本轮只独立变化轮毂；跨版本与颜色变化参考编排器真实证据，完整车型组合覆盖未进行。已证明当前两套完整选配读取，不承诺Tesla未来DOM不变。
- 原月供及配件缺项修复已由0.1.1真实UI和JSON核验；不能由此推断其他车型所有字段都完整。
- 全项目仍须正式客户归属、报告持久化、实时ASR、高德及模型集成验收。
