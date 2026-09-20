import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams, useBlocker, useLocation } from "react-router";
import { tess } from "../services/tess";
import { captureCurrent } from "../services/capture";
import { ApiError, contractMock } from "../services/api";
import { useDraftText, draftKey } from "../hooks/useDraftText";
import { useSession } from "../hooks/useSession";
import { useRealtimeAsr } from "../hooks/useRealtimeAsr";
import { PageHeader, Loading, ErrorNotice, Toast } from "../components/Shared";
import { Icon } from "../components/Icon";
import CaptureCard from "../components/CaptureCard";
import Composer from "../components/Composer";
import {
  FinanceConclusion,
  KnowledgeToolBubble,
  PlanningBubble,
  ProcessTrail,
  ReplyBubble,
  StageBubble,
  ThinkingBubble,
  ToolBubble,
} from "../components/FinancePlanReply";
import {
  FINANCE_INPUT_A,
  FINANCE_INPUT_B1,
  FINANCE_INPUT_B2,
  FINANCE_INPUT_B3,
  buildFinanceCaseA,
  buildTrialCapture,
  isFinanceInputA,
  isFinanceInputB1,
  isFinanceInputB2,
  isFinanceInputB3,
  sleep,
  type FinanceCaseAResult,
  type FinancePlanOption,
  type FinanceToolCall,
} from "../mocks/demoFinance";
import { CASE_B_SCRIPT, buildFinanceCaseBResult } from "../mocks/caseBScript";
import {
  KNOWLEDGE_INPUT,
  KNOWLEDGE_SCRIPT,
  isKnowledgeInput,
  type KnowledgeSource,
  type KnowledgeToolCall,
} from "../mocks/knowledgeCopilot";
import { saveAppliedPlan } from "../mocks/sessionPlans";
import type { Capture } from "../types/api";

type DemoBubble =
  | { id: string; kind: "sales"; text: string }
  | { id: string; kind: "thinking"; label: string }
  | {
      id: string;
      kind: "stage";
      label: string;
      title?: string;
      lines?: string[];
    }
  | {
      id: string;
      kind: "planning";
      steps: string[];
      loading?: boolean;
      loadingText?: string;
    }
  | { id: string; kind: "tool"; call: FinanceToolCall }
  | { id: string; kind: "kb_tool"; call: KnowledgeToolCall }
  | {
      id: string;
      kind: "conclusion";
      result: FinanceCaseAResult;
    }
  | {
      id: string;
      kind: "reply";
      text: string;
      sources?: KnowledgeSource[];
    }
  | {
      id: string;
      kind: "trial_card";
      capture: Capture;
      optionNumber: number;
      versionTag: string;
      note: string;
    };

function isProcessBubble(bubble: DemoBubble) {
  return (
    bubble.kind === "thinking" ||
    bubble.kind === "stage" ||
    bubble.kind === "planning" ||
    bubble.kind === "tool" ||
    bubble.kind === "kb_tool"
  );
}

function isTerminalBubble(bubble: DemoBubble) {
  return (
    bubble.kind === "conclusion" ||
    bubble.kind === "reply" ||
    bubble.kind === "trial_card"
  );
}

function renderProcessBubble(bubble: DemoBubble) {
  if (bubble.kind === "thinking") {
    return <ThinkingBubble key={bubble.id} label={bubble.label} />;
  }
  if (bubble.kind === "stage") {
    return (
      <StageBubble
        key={bubble.id}
        label={bubble.label}
        title={bubble.title}
        lines={bubble.lines}
      />
    );
  }
  if (bubble.kind === "planning") {
    return (
      <PlanningBubble
        key={bubble.id}
        steps={bubble.steps}
        loading={bubble.loading}
        loadingText={bubble.loadingText}
      />
    );
  }
  if (bubble.kind === "tool") {
    return <ToolBubble key={bubble.id} call={bubble.call} />;
  }
  if (bubble.kind === "kb_tool") {
    return <KnowledgeToolBubble key={bubble.id} call={bubble.call} />;
  }
  return null;
}

export default function SessionRoute() {
  const { sessionId = "" } = useParams();
  return <Session key={sessionId} id={sessionId} />;
}

function Session({ id }: { id: string }) {
  const location = useLocation();
  const { data: s, error, setError, refresh, track } = useSession(id),
    [text, setText] = useDraftText(id),
    [busy, setBusy] = useState(false),
    [captureBusy, setCaptureBusy] = useState(false),
    [toast, setToast] = useState(""),
    [demoThread, setDemoThread] = useState<DemoBubble[]>([]),
    [demoMode, setDemoMode] = useState<"finance" | "knowledge" | null>(null);
  const threadEnd = useRef<HTMLDivElement>(null);
  const audio = useRealtimeAsr({
    sessionId: id,
    revision: s?.revision || 1,
    text,
    onText: setText,
  });
  const blocker = useBlocker(audio.active);
  const [leaveAfterFinish, setLeaveAfterFinish] = useState(false);
  const locationState = location.state as {
    financeSceneAt?: number;
    knowledgeSceneAt?: number;
  } | null;
  const financeSceneAt = locationState?.financeSceneAt;
  const knowledgeSceneAt = locationState?.knowledgeSceneAt;

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [demoThread, busy]);

  useEffect(() => {
    if (!financeSceneAt) return;
    setDemoMode("finance");
    setDemoThread([]);
    setToast("");
    void refresh().catch(() => {});
  }, [financeSceneAt, refresh]);

  useEffect(() => {
    if (!knowledgeSceneAt) return;
    setDemoMode("knowledge");
    setDemoThread([]);
    setToast("");
    void refresh().catch(() => {});
  }, [knowledgeSceneAt, refresh]);

  useEffect(() => {
    if (leaveAfterFinish && !audio.active && blocker.state === "blocked") {
      setLeaveAfterFinish(false);
      blocker.proceed();
    }
  }, [leaveAfterFinish, audio.active, blocker]);

  async function action(fn: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && e.code === "CONFLICT")
        await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  }

  if (!s)
    return (
      <>
        <PageHeader title="本次试驾" />
        <ErrorNotice message={error} />
        {!error && <Loading />}
      </>
    );

  const session = s,
    active = s.captures.filter((c) => c.active),
    working = busy || !!s.active_run;

  async function playFinancePipeline(args: {
    intentTitle: string;
    intentLines: string[];
    routerTitle: string;
    routerLines?: string[];
    planSteps?: string[];
    tools: FinanceToolCall[];
    skipPlan?: boolean;
  }) {
    const thinkingId = crypto.randomUUID();
    setDemoThread((prev) => [
      ...prev,
      { id: thinkingId, kind: "thinking", label: "意图识别中…" },
    ]);
    await sleep(550);
    setDemoThread((prev) => [
      ...prev.filter((item) => item.id !== thinkingId),
      {
        id: crypto.randomUUID(),
        kind: "stage",
        label: "意图",
        title: args.intentTitle,
        lines: args.intentLines,
      },
    ]);
    await sleep(400);
    setDemoThread((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        kind: "stage",
        label: "路由",
        title: args.routerTitle,
        lines: args.routerLines,
      },
    ]);
    await sleep(400);

    if (!args.skipPlan && args.planSteps?.length) {
      const planId = crypto.randomUUID();
      setDemoThread((prev) => [
        ...prev,
        {
          id: planId,
          kind: "planning",
          steps: args.planSteps!,
          loading: true,
          loadingText: "正在进入 Plan…",
        },
      ]);
      await sleep(800);
      setDemoThread((prev) =>
        prev.map((item) =>
          item.id === planId && item.kind === "planning"
            ? { ...item, loading: false }
            : item,
        ),
      );
      await sleep(350);
    }

    for (const call of args.tools) {
      const loadingId = crypto.randomUUID();
      setDemoThread((prev) => [
        ...prev,
        {
          id: loadingId,
          kind: "thinking",
          label: `调用 ${call.title}…`,
        },
      ]);
      await sleep(500);
      setDemoThread((prev) => [
        ...prev.filter((item) => item.id !== loadingId),
        { id: crypto.randomUUID(), kind: "tool", call },
      ]);
      await sleep(280);
    }
    await sleep(300);
  }

  async function runFinanceCaseA(submitted: string) {
    const target = active[0];
    const result = buildFinanceCaseA(target, 0);
    setDemoThread((prev) => [
      ...prev,
      { id: crypto.randomUUID(), kind: "sales", text: submitted },
    ]);
    setBusy(true);
    try {
      await playFinancePipeline({
        intentTitle: "金融规划 · Option 1 约束试算",
        intentLines: result.understand,
        routerTitle: "→ Plan · 约束决策",
        routerLines: ["进入方案规划后再调用 Finance Tool"],
        planSteps: result.planSteps,
        tools: result.tools,
      });
      setDemoThread((prev) => [
        ...prev,
        { id: crypto.randomUUID(), kind: "conclusion", result },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function runFinanceCaseB1(submitted: string) {
    const round = CASE_B_SCRIPT.round1;
    setDemoThread((prev) => [
      ...prev,
      { id: crypto.randomUUID(), kind: "sales", text: submitted },
    ]);
    setBusy(true);
    try {
      await playFinancePipeline({
        intentTitle: "金融规划 · Option 2（约束未钉死）",
        intentLines: [...round.understand],
        routerTitle: "→ Finance Tool",
        routerLines: ["先试算再澄清，本轮不进入改配 Plan"],
        skipPlan: true,
        tools: round.tools(),
      });
      setDemoThread((prev) => [
        ...prev,
        { id: crypto.randomUUID(), kind: "reply", text: round.reply },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function runFinanceCaseB2(submitted: string) {
    const round = CASE_B_SCRIPT.round2;
    const result = buildFinanceCaseBResult(active[1] || active[0]);
    setDemoThread((prev) => [
      ...prev,
      { id: crypto.randomUUID(), kind: "sales", text: submitted },
    ]);
    setBusy(true);
    try {
      await playFinancePipeline({
        intentTitle: "金融规划 · Option 2 硬约束",
        intentLines: [...round.understand],
        routerTitle: "→ Plan · 约束决策",
        routerLines: ["硬约束已钉死，进入方案对照 Plan"],
        planSteps: [...round.planSteps],
        tools: round.tools(),
      });
      setDemoThread((prev) => [
        ...prev,
        { id: crypto.randomUUID(), kind: "conclusion", result },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function commitOptionPlan(
    optionNumber: number,
    plan: FinancePlanOption,
    note: string,
  ) {
    const source = active[optionNumber - 1] || active[0];
    const versionTag = "V1";
    const trial = buildTrialCapture(source, plan, versionTag);
    saveAppliedPlan(id, {
      id: crypto.randomUUID(),
      optionNumber,
      versionTag,
      planId: plan.id,
      note,
      capture: trial,
      appliedAt: new Date().toISOString(),
    });
    setDemoThread((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        kind: "trial_card",
        capture: trial,
        optionNumber,
        versionTag,
        note,
      },
    ]);
  }

  async function runFinanceCaseB3(submitted: string) {
    const round = CASE_B_SCRIPT.round3;
    setDemoThread((prev) => [
      ...prev,
      { id: crypto.randomUUID(), kind: "sales", text: submitted },
    ]);
    setBusy(true);
    try {
      const thinkingId = crypto.randomUUID();
      setDemoThread((prev) => [
        ...prev,
        { id: thinkingId, kind: "thinking", label: "正在更新 Option 2…" },
      ]);
      await sleep(700);
      setDemoThread((prev) => prev.filter((item) => item.id !== thinkingId));
      commitOptionPlan(2, round.plan, round.note);
    } finally {
      setBusy(false);
    }
  }

  async function runKnowledgeCase(submitted: string) {
    const script = KNOWLEDGE_SCRIPT;
    setDemoThread((prev) => [
      ...prev,
      { id: crypto.randomUUID(), kind: "sales", text: submitted },
    ]);
    setBusy(true);
    try {
      const thinkingId = crypto.randomUUID();
      setDemoThread((prev) => [
        ...prev,
        { id: thinkingId, kind: "thinking", label: "意图识别中…" },
      ]);
      await sleep(550);
      setDemoThread((prev) => [
        ...prev.filter((item) => item.id !== thinkingId),
        {
          id: crypto.randomUUID(),
          kind: "stage",
          label: "意图",
          title: script.intent.title,
          lines: [...script.intent.lines],
        },
      ]);
      await sleep(400);
      setDemoThread((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          kind: "stage",
          label: "路由",
          title: script.router.title,
        },
      ]);
      await sleep(400);

      for (const call of script.tools()) {
        const loadingId = crypto.randomUUID();
        setDemoThread((prev) => [
          ...prev,
          {
            id: loadingId,
            kind: "thinking",
            label: `调用 ${call.title}…`,
          },
        ]);
        await sleep(500);
        setDemoThread((prev) => [
          ...prev.filter((item) => item.id !== loadingId),
          { id: crypto.randomUUID(), kind: "kb_tool", call },
        ]);
        await sleep(280);
      }

      await sleep(300);
      setDemoThread((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          kind: "reply",
          text: script.reply,
          sources: [...script.sources],
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function capture() {
    if (captureBusy) return;
    if (active.length >= 3) {
      setToast("最多抓取 3 个。要换方案，先去掉一个再 Capture。");
      return;
    }
    setCaptureBusy(true);
    setError("");
    const owner = id,
      revision = session.revision;
    try {
      const payload = await captureCurrent();
      await tess.capture(owner, revision, payload);
      await refresh();
    } catch (e) {
      const limit =
        e instanceof ApiError &&
        (e.code === "CANDIDATE_LIMIT" || /三个候选|3 个候选/.test(e.message));
      if (limit) setToast("最多抓取 3 个。要换方案，先去掉一个再 Capture。");
      else setError((e as Error).message);
      if (e instanceof ApiError && e.code === "CONFLICT")
        await refresh().catch(() => {});
    } finally {
      setCaptureBusy(false);
    }
  }

  async function recaptureFinance(captureId: string) {
    if (captureBusy) return;
    setCaptureBusy(true);
    setError("");
    try {
      const latest = await tess.session(id);
      let revision = latest.revision;
      const live = latest.captures.filter((item) => item.active);
      if (live.length >= 3) {
        const updated = await tess.updateCapture(id, captureId, revision, {
          active: false,
        });
        revision = updated.revision;
      }
      const payload = await captureCurrent();
      const created = await tess.capture(id, revision, payload);
      revision = created.revision;
      if (live.some((item) => item.id === captureId && live.length < 3)) {
        await tess.updateCapture(id, captureId, revision, { active: false });
      }
      await refresh();
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && e.code === "CONFLICT")
        await refresh().catch(() => {});
    } finally {
      setCaptureBusy(false);
    }
  }

  async function send() {
    const submitted = text.trim();
    if (!submitted || working) return;
    const clearDraft = () => {
      if (localStorage.getItem(draftKey(id)) === text) setText("");
      audio.markSent();
    };
    if (isFinanceInputA(submitted)) {
      clearDraft();
      await runFinanceCaseA(submitted);
      return;
    }
    if (isFinanceInputB1(submitted)) {
      clearDraft();
      await runFinanceCaseB1(submitted);
      return;
    }
    if (isFinanceInputB2(submitted)) {
      clearDraft();
      await runFinanceCaseB2(submitted);
      return;
    }
    if (isFinanceInputB3(submitted)) {
      clearDraft();
      await runFinanceCaseB3(submitted);
      return;
    }
    if (isKnowledgeInput(submitted)) {
      clearDraft();
      await runKnowledgeCase(submitted);
      return;
    }
    await action(async () => {
      const asrSessionId = audio.freezeForSend();
      const pending = session.pending_run;
      const r = await tess.message(id, {
        text: submitted,
        source: asrSessionId ? "asr_corrected" : "sales_text",
        asr_session_id: asrSessionId,
        expected_revision: session.revision,
        ...(pending?.questions.length
          ? {
              reply_to_run_id: pending.run_id,
              reply_to_question_ids: pending.questions
                .filter((q) => !q.state || q.state === "open")
                .map((q) => q.id),
            }
          : {}),
      });
      if (localStorage.getItem(draftKey(id)) === submitted) setText("");
      audio.markSent();
      await track(r.run_id);
    });
  }

  function fillDemoInput(script: string) {
    audio.edit(script);
  }

  function applyFinancePlan(actionId: "apply_a" | "apply_b") {
    const last = [...demoThread]
      .reverse()
      .find((item) => item.kind === "conclusion");
    if (!last || last.kind !== "conclusion") return;
    const plan =
      actionId === "apply_a" ? last.result.optionA : last.result.optionB;
    if (!plan.ok && actionId === "apply_b") {
      setToast("方案 B 当前不满足硬约束，请先选方案 A，或放宽预算后再试。");
      return;
    }
    const matched = last.result.optionLabel.match(/Option\s*(\d+)/i);
    const optionNumber = matched ? Number(matched[1]) : 1;
    commitOptionPlan(
      optionNumber,
      plan,
      `已按方案 ${plan.id} 更新 ${last.result.optionLabel} · V1。`,
    );
  }

  function renderDemoThread() {
    const nodes: ReactNode[] = [];
    let i = 0;
    while (i < demoThread.length) {
      const bubble = demoThread[i];
      if (bubble.kind === "sales") {
        nodes.push(
          <div className="chat-row sales" key={bubble.id}>
            <div className="chat-meta">销售 · Alex</div>
            <div className="chat-bubble sales">{bubble.text}</div>
          </div>,
        );
        i += 1;
        continue;
      }

      if (isProcessBubble(bubble)) {
        const start = i;
        const batch: DemoBubble[] = [];
        while (i < demoThread.length && isProcessBubble(demoThread[i])) {
          batch.push(demoThread[i]);
          i += 1;
        }
        const done = demoThread.slice(i).some(isTerminalBubble);
        const groupId =
          [...demoThread.slice(0, start)]
            .reverse()
            .find((item) => item.kind === "sales")?.id ||
          demoThread[start].id;
        nodes.push(
          <ProcessTrail key={`process-${groupId}`} done={done}>
            {batch.map((item) => renderProcessBubble(item))}
          </ProcessTrail>,
        );
        continue;
      }

      if (bubble.kind === "conclusion") {
        nodes.push(
          <FinanceConclusion
            key={bubble.id}
            result={bubble.result}
            onAction={applyFinancePlan}
          />,
        );
        i += 1;
        continue;
      }

      if (bubble.kind === "reply") {
        nodes.push(
          <ReplyBubble
            key={bubble.id}
            text={bubble.text}
            sources={bubble.sources}
          />,
        );
        i += 1;
        continue;
      }

      nodes.push(
        <div className="chat-row assistant" key={bubble.id}>
          <div className="chat-meta">Tess</div>
          <div className="chat-bubble assistant trial">
            <p>{bubble.note}</p>
            <CaptureCard
              capture={bubble.capture}
              index={0}
              optionNumber={bubble.optionNumber}
              versionTag={bubble.versionTag}
              readOnly
              busy={false}
              onRemove={() => {}}
              onConfirmFinance={async () => {
                setToast("已按当前 Mock 金融数据写回这张卡。");
              }}
            />
          </div>
        </div>,
      );
      i += 1;
    }
    return nodes;
  }

  return (
    <>
      <Toast message={toast} onDismiss={() => setToast("")} />
      <PageHeader title={s.customer.nickname} subtitle={s.customer.contact_mask}>
        <div className="page-header-actions">
          <Link
            className="quiet-icon-link"
            to={`/sessions/${id}/plans`}
            aria-label="已生成方案"
            title="已生成方案"
          >
            <Icon name="plans" size={18} />
          </Link>
          <Link
            className="quiet-icon-link"
            to={`/customers/${s.customer.id}/history/${id}`}
            aria-label="历史报告"
            title="历史报告"
          >
            <Icon name="history" size={18} />
          </Link>
        </div>
      </PageHeader>
      <div className="scroll-area conversation">
        <div className="row between">
          <div>
            <p className="eyebrow">CURRENT OPTIONS</p>
            <h2>当前候选</h2>
          </div>
          <button
            className="secondary compact"
            disabled={captureBusy || working}
            onClick={() => void capture()}
          >
            {captureBusy ? (
              "读取官网中…"
            ) : (
              <>
                <Icon name="plus" size={16} />
                {contractMock ? "Mock Capture" : "Capture"}
              </>
            )}
          </button>
        </div>
        {active.length === 0 && (
          <div className="notice">
            <p>在 Tesla 中国 Model Y 官网完成选配后，点击 Capture。</p>
            <a href="https://www.tesla.cn/" target="_blank" rel="noreferrer">
              进入特斯拉中国官网 ↗
            </a>
          </div>
        )}
        {active.map((c, i) => (
          <CaptureCard
            key={c.id}
            capture={c}
            index={i}
            optionNumber={i + 1}
            busy={working || captureBusy}
            onRemove={() =>
              void action(() =>
                tess.updateCapture(id, c.id, s.revision, { active: false }),
              )
            }
            onConfirmFinance={() => recaptureFinance(c.id)}
          />
        ))}

        {demoThread.length > 0 && (
          <div className="demo-thread">
            {renderDemoThread()}
            <div ref={threadEnd} />
          </div>
        )}
        <ErrorNotice message={error} />
      </div>
      {blocker.state === "blocked" && (
        <div className="modal-backdrop">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="recording-leave-title"
            className="navigation-dialog"
          >
            <h2 id="recording-leave-title">本次录音尚未结束</h2>
            <p>结束后保留文字在当前客户的输入框；不会自动发送。</p>
            <button
              className="primary full"
              disabled={leaveAfterFinish}
              onClick={() => {
                setLeaveAfterFinish(true);
                audio.finish();
              }}
            >
              {leaveAfterFinish
                ? "正在收尾，文字保留后离开…"
                : "结束并保留后离开"}
            </button>
            <button
              className="full"
              onClick={() => {
                audio.discard();
                setLeaveAfterFinish(false);
                blocker.proceed();
              }}
            >
              放弃本段并离开
            </button>
            <button
              className="text-button full"
              onClick={() => {
                setLeaveAfterFinish(false);
                blocker.reset();
              }}
            >
              留在当前会话
            </button>
          </section>
        </div>
      )}
      <div className="composer-host">
        <div className="demo-input-scripts">
          {demoMode === "knowledge" ? (
            <button
              type="button"
              className="demo-input-script"
              onClick={() => fillDemoInput(KNOWLEDGE_INPUT)}
            >
              复制知识提问
            </button>
          ) : (
            <>
              <button
                type="button"
                className="demo-input-script"
                onClick={() => fillDemoInput(FINANCE_INPUT_A)}
              >
                复制 A · Option 1
              </button>
              <button
                type="button"
                className="demo-input-script"
                onClick={() => fillDemoInput(FINANCE_INPUT_B1)}
              >
                复制 B1 · Option 2
              </button>
              <button
                type="button"
                className="demo-input-script"
                onClick={() => fillDemoInput(FINANCE_INPUT_B2)}
              >
                复制 B2
              </button>
              <button
                type="button"
                className="demo-input-script"
                onClick={() => fillDemoInput(FINANCE_INPUT_B3)}
              >
                复制 B3
              </button>
            </>
          )}
        </div>
        <Composer
          text={text}
          onChange={audio.edit}
          onSend={() => void send()}
          busy={working}
          audio={audio}
        />
      </div>
    </>
  );
}
