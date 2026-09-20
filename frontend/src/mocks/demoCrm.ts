/** 客户甲演示 CRM。复制按钮写入剪贴板，确认页用规则摘要，不调用模型。 */

export const DEMO_CRM_TEXT = `【客户】张先生
手机 138-2219-0647（微信同号，上次备注里写成13822190647）
邮箱：qiming.zhang@outlook.com  //行政邮箱，别往公司群发

——系统字段——
来源：展厅自然到店 / 复购介绍
意向车：Model Y（已预约试驾，不是 Model S）
跟进销售：Alex
预约：今天 15:30 北京朝阳合生汇 Tesla 中心 · 试驾 Model Y（客户说可能会晚一点）
标签：已建档,已预约试驾,家庭决策

——跟进记录（销售随手记，别改格式）——
9/12 电话没接，晚上微信回了，问长续航和后驱差多少，我说先试再定。
9/18 到店看了白色21寸，人不多，自己在配置器里点了半天。配偶没来，说回去和家里对一下月供。
备注2：客户原话「月供最好压在3000以内，首付大概能出10万，但现在这套配置挺喜欢的，能留就留」。首付他说的是能凑出来的现金，不含置换，置换还没问。
家里有固定车位，小区能不能装家充他不太清楚，让我别写死。
试驾车是后驱，他想买的不一定是后驱，别把试驾感受直接套到候选上。
有个同事9/19留了句：客户问过后排坐垫硬不硬，未闭环。
不要给客户发金融测算截图到朋友圈。联系人备注里还有一句「女儿上小学，接送半径大概望京附近」，具体小区没给。`;

export type CrmProfile = {
  nickname: string;
  phone: string;
  email: string;
  appointment: {
    when: string;
    store: string;
    vehicle: string;
  } | null;
  points: string[];
};

export const JIA_PROFILE: CrmProfile = {
  nickname: "张先生",
  phone: "13822190647",
  email: "qiming.zhang@outlook.com",
  appointment: {
    when: "今天 15:30",
    store: "北京朝阳合生汇 Tesla 中心",
    vehicle: "Model Y",
  },
  points: [
    "月供希望控制在 3000 元以内，首付大约 10 万，想尽量保留现在这套配置",
    "配偶未到场；试驾的是后驱，购买版本还没定",
    "有固定车位，小区能否安装家充不清楚",
    "接送半径大约在望京附近",
  ],
};

function digits(phone: string) {
  return phone.replace(/\D/g, "");
}

/** 规则整理，不请求大模型。命中客户甲特征句时用预置摘要。 */
export function profileFromCrm(text: string): CrmProfile | null {
  const raw = text.trim();
  if (!raw) return null;
  if (
    raw.includes("张先生") ||
    raw.includes("qiming.zhang@outlook.com") ||
    raw.includes("13822190647") ||
    raw.includes("138-2219-0647")
  ) {
    return JIA_PROFILE;
  }
  const phoneMatch = raw.match(/(\+?86[-\s]?)?1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}/);
  const emailMatch = raw.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  const nameMatch =
    raw.match(/【客户】\s*([^\n]+)/) ||
    raw.match(/客户[：:]\s*([^\n，,（(]+)/) ||
    raw.match(/姓名[：:]\s*([^\n，,]+)/);
  const nickname = (nameMatch?.[1] || "").replace(/（.+）|\(.+\)/g, "").trim();
  const phone = phoneMatch ? digits(phoneMatch[0]).replace(/^86/, "") : "";
  const email = emailMatch?.[0] || "";
  if (!nickname || (!phone && !email)) return null;
  const points = raw
    .split(/\n+/)
    .map((line) => line.replace(/^[-—\s]+/, "").trim())
    .filter(
      (line) =>
        line.length > 8 &&
        !line.includes(nickname) &&
        !line.includes(phone) &&
        !line.includes(email),
    )
    .slice(0, 5);
  return { nickname, phone, email, appointment: null, points };
}
