| 字段 | 内容 |
|---|---|
| 作者 | Evan |
| 日期 | 2026-09-20 |
| 事项 | T-006 Report与录音客户端实现/协议独立验收 |
| 版本 | v1.0 |
| 结果 | PASS（实现与本地协议阶段；浏览器及供应商仍未验） |

## 验收范围

T-006为前端实现与协议阶段，acceptanceCriteria=[]，按当前四项technicalChecks验收。dispatcher返回errors=[]，tester_ready包含T-006；任务testing、源码冻结。复用T-002已验稳定证据，本轮只检查Report/audio新增及直接影响路径。未操作Chrome、麦克风、百炼或高德；未访问真实客户或凭证。完整尺寸与用户操作由T-010，真实供应商由T-008负责。本PASS不是完整业务、视觉或ASR识别通过，也不是用户已亲验或Key已配置。

## 逐技术检查

| 检查 | 结果 | 实际方法与证据 |
|---|---|---|
| TC1 Report首屏三问、同源图表与缺失状态 | PASS（代码/转换/SSR） | Report源码三问优先于模块；Options/Finance/Energy图表和正文消费同一fields/solutions/series，金额统一分→元；13项逻辑测试及Report SSR独立通过。参数缺少两组不画比较，缺数不转0。能源显示年里程/电耗/电价/油耗/油价/周期及假设来源，仅能源差额。 |
| TC2 侧栏状态、静态业务按钮、地图例外 | PASS（实现范围） | CSS窄屏/独立滚动/固定输入和录音导航状态实现已核对；Report业务按钮disabled，地图独立target=_blank、noopener noreferrer；safeMapUrl约束https/uri.amap.com/search和参数白名单，未知区域不生成。缺地图保留已有站点与距离、显示失败/无结果/歧义。实际360/420/480与1024/1440视觉仍T-010未验。 |
| TC3 AudioWorklet/PCM/手动发送/迟到/导航/释放 | PASS（本地协议） | 48k与44.1k重采样为16k PCM16LE、100ms3200bytes、跨128采样块保留状态；实际hook源码在受控React/WebAudio/WS替身中验证ready门禁、PCM→flush→finish→尾final→finished顺序、停录保留文字不调用业务API、编辑/放弃保护、时长上限drain、已发generation拒迟到、卸载释放。导航弹窗与阻塞/结束/放弃源码核对，实际权限与采音仍未验。 |
| TC4 构建产物与冻结Capture复用 | PASS（本地产物） | 同冻结版本type-check/lint/build通过采用开发交接证据；独立核对dist MV3、CSP仅self脚本、入口/worker/本地Worklet存在、无CDN脚本、无供应商Key变量或Key模式内嵌，Capture字节与0.1.1源一致。实际安装仍T-010。 |

## 独立执行与可复现命令

工作目录为`frontend/`：

- `npm test`：13/13 PASS，退出0。包括PCM、字幕替换/错session/旧generation/手改锁定/Unknown替代链/缺数/地图白名单。
- `npm run test:report`：PASS，退出0。SSR断言金融分元换算、能源46000与全部假设、无假地图/零、静态按钮、地图失败站点保留、中性车辆缺图状态。SSR不等于浏览器布局。
- `node ../.sdd/test-reports/t006-audio-protocol.cjs`：PASS，退出0。此独立脚本加载实际`useRealtimeAsr.ts`并使用确定性React hooks/WebAudio/WS替身，无网络或实际录音。可验证状态回调与资源释放，不验证真实React渲染时序/权限/浏览器采样。
- 独立Python产物断言：manifest_version=3；CSP=`script-src 'self'; object-src 'none'`；index与service worker文件存在；脚本URL全部本地；Worklet产物含registerProcessor；dist/capture.js与extension/capture.js字节相同；发行JS未嵌入供应商配置变量或常见密钥模式。无敏感值输出。

## 关键数据与失败行为证据

- financial SSR月供`¥4,025`来自分值，不出现错误的`¥402,500`；预算未知不画虚构预算线。金融Mock明确标记而非官方资格承诺。
- 能源SSR五年46000元，年里程20000km，文案明确不含购车、保险、保养和折旧；图和表共用过滤后的同一series。
- 地图无asset时不产生img，不补示意站点；已查询到站点而静态图失败的模块仍展示站点及1.8km，包含明确Missing提示。
- 地图URL只允许keyword/city/view/src/callnative，不接受额外key参数或其他host。前端不生成客户身份或联系方式参数；安全值最终依赖服务端固定报告投影，完整隐私/真实高德链路留T-007/T-008/T-010。
- ReportContent按report/session键重建状态，load有alive保护；不会沿用上一个Report的map/error/data状态。实际跨报告浏览器切换留T-010。
- ReviewCard含数字的事实句只读，非数字总结可修改；实际发布校验仍依赖后端并由集成验收负责。
- 录音hook只调用createAudio与音频WS，业务message仅由Session手动send；Composer在active期间禁用发送与快捷键。停止等待尾段不会自动建业务消息。
- AudioWorklet将多个输入声道平均到mono；2秒64000bytes背压上限；停止先flush，再发finish，避免末段丢失。客户端时长上限与ASR_DURATION_LIMIT(incomplete=false)进入收尾，错误才fail。
- 导航使用useBlocker，结束并保留等待active=false后离开；放弃还原既有人工文本，beforeunload有提示。dispose提高generation并停track、断source/node、关AudioContext与WS；已接收文字以session draft留存。

## 文件指纹

- `dist/capture.js`：`98dc7661ebbd35de59ae99c1ea04ff90c0c70ae8f6776fef7778f8971430187b`
- `src/hooks/useRealtimeAsr.ts`：`4688b5830a6bd00e7df682edab8c3cfbac3769b8d679065ef5d9c4c333217447`
- `src/components/ReportModules.tsx`：`6578b15ebe05a9ec641590d357a2fae5904b91638bcbb88bca3c6233e3db7949`
- `src/components/ReportCharts.tsx`：`9e0f9bbea8cc7db48c2008554ae766d9ec36b1754338dcc86945eb45280ca00e`
- `src/pages/Report.tsx`：`2bb1121e1edcb75456df3d3b518fe698182570bf5099bf0a56e0042a5413080f`

## 保留未验项与经验边界

真实Chrome安装/布局、麦克风允许和拒绝、AudioContext平台兼容、断流导航及真正关闭侧栏、中文首尾字时延未验；真实百炼识别与真实高德查询未验。缺环境并未改写为成功。前端和后端真实协议联调仍须T-007/T-008/T-010完成。

开发提出的ASR_DURATION_LIMIT应drain而不是fail、discard保留人工更正、缺图保留站点，均由本地协议/SSR直接测试支持；可以作为本项目实现经验，尚不能声称真实供应商和浏览器已经验证。本轮未发现必要技术项失败，不更改业务代码或任务状态。
