/**
 * 场景 5 · 销售补充 Decision Context
 * 轨迹：意图 → 路由 →（首轮 Plan）→ Decision Context Tool → 回复
 * 接场景 3 尾态（保留 Option 1/2）；风控通过静默
 */

import { prepareFinanceScene } from "./demoFinance";

export type DecisionSlot = {
  key: string;
  label: string;
  value: string;
};

export type DecisionContextToolCall = {
  id: string;
  title: string;
  action: string;
  ok: boolean;
  note: string;
  gaps?: string[];
};

function normalizeInput(text: string) {
  return text.replace(/\s+/g, "").replace(/[。．.!?！？]/g, "");
}

/** 第 0 步 · 销售第一段 */
export const DECISION_INPUT_0 = `试驾完了，他刚才那套白色长续航明显更对胃口，坐进去也说视野和空间可以。月供还是卡着，家充能不能装他也没底。太太今天没来，微信里老问后排坐着累不累、接小孩方不方便。金融那两版我对着 Option 算给他看了，超充过半掉功率也讲清楚了，这两块他点头了。还悬的是小区桩和回去跟家里拍板。白色和现在这套轮毂他不太肯让，后驱还是上长续航还能再磨。`;

/** 第 2 步 · 销售补充第 1 轮 */
export const DECISION_INPUT_1 = `长续航他更想留，真要砍预算多半拿后驱来换，不过他还没说死。太太那边接送更要紧，后排硬不硬是加分，不是否决。`;

/** 第 4 步 · 销售补充第 2 轮 */
export const DECISION_INPUT_2 = `没正经查过，就是自己猜小区可能不好装，让我别写死。算待核实就行。`;

/** 第 6 步 · 口头确认 */
export const DECISION_CONFIRM = `没有了，就这些。`;

export function isDecisionInput0(text: string) {
  return normalizeInput(text) === normalizeInput(DECISION_INPUT_0);
}
export function isDecisionInput1(text: string) {
  return normalizeInput(text) === normalizeInput(DECISION_INPUT_1);
}
export function isDecisionInput2(text: string) {
  return normalizeInput(text) === normalizeInput(DECISION_INPUT_2);
}
export function isDecisionConfirm(text: string) {
  return normalizeInput(text) === normalizeInput(DECISION_CONFIRM);
}

const SLOTS_DRAFT: DecisionSlot[] = [
  {
    key: "like",
    label: "最喜欢",
    value: "白色长续航这套；座舱视野和空间感受不错",
  },
  {
    key: "worry",
    label: "最担心",
    value: "月供压力；小区能否装家充",
  },
  {
    key: "family",
    label: "家庭关注",
    value: "后排舒适；接送是否方便（配偶侧，本人未到场）",
  },
  {
    key: "resolved",
    label: "已解决",
    value: "金融方案已对照候选讲清；超充中后段掉功率已解释，客户表示理解",
  },
  {
    key: "open",
    label: "未解决",
    value: "小区装桩可行性；与家人最终拍板",
  },
  {
    key: "must",
    label: "Must-have",
    value: "白色；当前轮毂意向",
  },
  {
    key: "flex",
    label: "可妥协",
    value: "后驱 vs 长续航仍可谈（具体倾向未明）",
  },
];

const SLOTS_AFTER_R1: DecisionSlot[] = SLOTS_DRAFT.map((slot) => {
  if (slot.key === "flex") {
    return {
      ...slot,
      value: "优先保长续航；预算紧时可用后驱换空间（尚未最终承诺）",
    };
  }
  if (slot.key === "family") {
    return {
      ...slot,
      value: "接送便利优先；后排舒适为加分项，非否决项",
    };
  }
  return slot;
});

const SLOTS_FINAL: DecisionSlot[] = [
  {
    key: "like",
    label: "最喜欢",
    value: "白色长续航；座舱视野与空间",
  },
  {
    key: "worry",
    label: "最担心",
    value: "月供；家充安装不确定性",
  },
  {
    key: "family",
    label: "家庭关注",
    value: "接送便利优先；后排舒适为加分",
  },
  {
    key: "resolved",
    label: "已解决",
    value: "金融方案已讲清；超充掉功率已解释并获理解",
  },
  {
    key: "open",
    label: "未解决",
    value: "小区装桩待核实；家庭最终拍板",
  },
  {
    key: "must",
    label: "Must-have",
    value: "白色；当前轮毂意向",
  },
  {
    key: "flex",
    label: "可妥协",
    value: "优先保长续航；预算紧时可用后驱换",
  },
];

/** 场景 5 完结态 · 已确认入库的七格（场景 6 初始展示） */
export const CONFIRMED_DECISION_SLOTS: DecisionSlot[] = SLOTS_FINAL;

export const DECISION_SCRIPT = {
  round0: {
    intent: {
      title: "销售补录决策语境",
      lines: ["非客户问答、非金融试算——整理 Explicit 决策语境"],
    },
    router: {
      title: "→ Plan · 决策语境收口",
      lines: ["抽取七格 → 对照缺口 → 生成追问"],
    },
    planSteps: ["抽取七格草稿", "对照缺口", "生成追问"],
    tool: (): DecisionContextToolCall => ({
      id: "dc-extract-1",
      title: "Decision Context · 结构化抽取",
      action: "extract",
      ok: true,
      note: "已填 7 格",
      gaps: ["可妥协倾向未明", "家庭关注优先级未明"],
    }),
    slots: SLOTS_DRAFT,
    intro: "先按你刚才说的整理了一版：",
    followup: `还差两点说清楚：

1. 后驱和长续航，他更可能让哪一边？
2. 太太那边，更在意后排舒适，还是接送方便？`,
  },
  round1: {
    intent: {
      title: "补充决策语境",
      lines: ["回答追问 · 合并补丁"],
    },
    router: {
      title: "→ Decision Context Tool（合并补丁）",
    },
    tool: (): DecisionContextToolCall => ({
      id: "dc-merge-1",
      title: "Decision Context · 合并更新",
      action: "merge",
      ok: true,
      note: "已更新：可妥协、家庭关注",
      gaps: ["装桩信息来源未明"],
    }),
    updates: [
      {
        key: "flex",
        label: "可妥协",
        value: "优先保长续航；预算紧时可用后驱换空间（尚未最终承诺）",
      },
      {
        key: "family",
        label: "家庭关注",
        value: "接送便利优先；后排舒适为加分项，非否决项",
      },
    ] satisfies DecisionSlot[],
    slots: SLOTS_AFTER_R1,
    intro: "已更新：",
    followup: `再确认一件事：
小区装桩——他是完全没查过，还是已经问过物业/邻居、只是结果不确定？`,
  },
  round2: {
    intent: {
      title: "补齐未解决项",
      lines: ["准备收口"],
    },
    router: {
      title: "→ Decision Context Tool（定稿）",
    },
    tool: (): DecisionContextToolCall => ({
      id: "dc-finalize-1",
      title: "Decision Context · 定稿",
      action: "finalize",
      ok: true,
      note: "缺口已清；待销售口头确认",
    }),
    slots: SLOTS_FINAL,
    intro: "那目前是这些：",
    followup: "确认就这些信息吗？你还有什么补充吗？",
  },
  confirm: {
    intent: {
      title: "确认决策语境入库",
      lines: ["销售口头确认 · 无补充"],
    },
    router: {
      title: "→ 写入 Context（Confirmed）",
    },
    tool: (): DecisionContextToolCall => ({
      id: "dc-write-1",
      title: "Context Write · 决策语境",
      action: "write_confirmed",
      ok: true,
      note: "confirmed · 7 项已写入",
    }),
    reply: "好，已记下。",
  },
} as const;

/** 场景 6 继承：销售输入 + Tess 回复的完整补录对话 */
export function buildScene5CompleteThread(): Array<
  | { id: string; kind: "sales"; text: string }
  | {
      id: string;
      kind: "dc_reply";
      intro?: string;
      slots?: DecisionSlot[];
      followup?: string;
      compact?: boolean;
    }
  | { id: string; kind: "reply"; text: string }
> {
  const id = () => crypto.randomUUID();
  return [
    { id: id(), kind: "sales", text: DECISION_INPUT_0 },
    {
      id: id(),
      kind: "dc_reply",
      intro: DECISION_SCRIPT.round0.intro,
      slots: [...DECISION_SCRIPT.round0.slots],
      followup: DECISION_SCRIPT.round0.followup,
    },
    { id: id(), kind: "sales", text: DECISION_INPUT_1 },
    {
      id: id(),
      kind: "dc_reply",
      intro: DECISION_SCRIPT.round1.intro,
      slots: [...DECISION_SCRIPT.round1.updates],
      followup: DECISION_SCRIPT.round1.followup,
      compact: true,
    },
    { id: id(), kind: "sales", text: DECISION_INPUT_2 },
    {
      id: id(),
      kind: "dc_reply",
      intro: DECISION_SCRIPT.round2.intro,
      slots: [...DECISION_SCRIPT.round2.slots],
      followup: DECISION_SCRIPT.round2.followup,
    },
    { id: id(), kind: "sales", text: DECISION_CONFIRM },
    {
      id: id(),
      kind: "reply",
      text: DECISION_SCRIPT.confirm.reply,
    },
    {
      id: id(),
      kind: "dc_reply",
      intro: "已确认入库：",
      slots: [...CONFIRMED_DECISION_SLOTS],
      compact: true,
    },
    {
      id: id(),
      kind: "reply",
      text: "决策语境已确认。客户离场后，可直接生成试驾报告——生成环节不再追问。",
    },
  ];
}

/** 进入场景 5：复用场景 3 种子（Option 1/2），清会话线程由前端处理 */
export async function prepareDecisionScene(sessionId: string) {
  await prepareFinanceScene(sessionId);
}
