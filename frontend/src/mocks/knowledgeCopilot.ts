/**
 * 场景 4 · Knowledge Copilot
 * 轨迹：意图 → 路由 → Knowledge Base Tool → 短答 + 来源
 * （单意图不进 Plan；风控通过静默）
 */

import { tess } from "../services/tess";
import { clearAppliedPlans } from "./sessionPlans";

export type KnowledgeSource = {
  id: string;
  title: string;
  url: string;
  snippet: string;
};

export type KnowledgeToolCall = {
  id: string;
  title: string;
  query: string;
  hits: KnowledgeSource[];
  ok: boolean;
  note: string;
};

/** 销售转述工程师客户的原话 */
export const KNOWLEDGE_INPUT =
  "客户问超充为什么过半就掉功率，是桩的问题还是车？";

function normalizeInput(text: string) {
  return text.replace(/\s+/g, "").replace(/[。．.!?！？]/g, "");
}

export function isKnowledgeInput(text: string) {
  return normalizeInput(text) === normalizeInput(KNOWLEDGE_INPUT);
}

const SOURCE_BATTERY: KnowledgeSource = {
  id: "kb-hv-battery",
  title: "高压电池信息",
  url: "https://www.tesla.cn/ownersmanual/modely/zh_cn/GUID-7FE78D73-0A17-47C4-B21B-54F641FFAEF4.html",
  snippet:
    "当电池温度过低、电量接近充满以及电池状况因使用和老化变化时，充电率将下降。频繁直流快充后峰值充电率可能稍有下降。",
};

const SOURCE_CHARGE: KnowledgeSource = {
  id: "kb-charging",
  title: "充电说明",
  url: "https://www.tesla.cn/ownersmanual/modely/zh_cn/GUID-BEE08D47-0CE0-4BDD-83F2-9854FB3D578F.html",
  snippet:
    "通常，较低的充电状态会使充电速度较快。导航至超级充电站并等待高压电池温度预设；相邻充电桩可能共享电源。",
};

export const KNOWLEDGE_SCRIPT = {
  intent: {
    title: "产品知识 · 充电 / 电池",
    lines: ["超充过半掉功率——区分车端限功率与桩侧问题"],
  },
  router: {
    title: "→ 官方知识库检索",
  },
  /** query 改写结果体现在工具入参 */
  tools: (): KnowledgeToolCall[] => [
    {
      id: "kb-search-1",
      title: "Knowledge Base · search",
      query: "超充 功率下降 电量接近充满 电池温度",
      hits: [SOURCE_BATTERY, SOURCE_CHARGE],
      ok: true,
      note: "命中 2 条官方文档",
    },
  ],
  reply: `多半是车在管电池，不一定是桩坏了。

电越充越满，电池就越不能继续大功率硬灌——跟手机快充前半截很快、后面变慢是一个道理。手册也写了：电量低时通常充得更快，接近满电时充电功率会降下来。

只有一种情况更像桩：刚插上、电还很低，功率就明显上不去，或者旁边有车同充、触屏还有告警。那才优先看桩是不是在分流、有没有故障。

想充得快点，尽量电量低一点再超充，或者导航到超充站让车先把电池温度准备好。`,
  sources: [SOURCE_BATTERY, SOURCE_CHARGE],
} as const;

/** 进入场景 4：清掉候选，空会话，只做 Ask Tess */
export async function prepareKnowledgeScene(sessionId: string) {
  clearAppliedPlans(sessionId);
  const detail = await tess.session(sessionId);
  let revision = detail.revision;
  for (const capture of detail.captures.filter((item) => item.active)) {
    const updated = await tess.updateCapture(sessionId, capture.id, revision, {
      active: false,
    });
    revision = updated.revision;
  }
}
