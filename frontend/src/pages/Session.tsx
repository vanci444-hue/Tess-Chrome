import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useBlocker } from "react-router";
import { tess } from "../services/tess";
import { captureCurrent } from "../services/capture";
import { ApiError, contractMock, reportUrl } from "../services/api";
import { useDraftText, draftKey } from "../hooks/useDraftText";
import { useSession } from "../hooks/useSession";
import { useRealtimeAsr } from "../hooks/useRealtimeAsr";
import { PageHeader, Loading, ErrorNotice } from "../components/Shared";
import CaptureCard from "../components/CaptureCard";
import ContextCard from "../components/ContextCard";
import ReviewCard from "../components/ReviewCard";
import IdentityEditor from "../components/IdentityEditor";
import Composer from "../components/Composer";
import { followupFixtures } from "../mocks/fixtures";
import type { FactChange } from "../types/api";
import { date, display } from "../utils/display";
export default function SessionRoute() {
  const { sessionId = "" } = useParams();
  return <Session key={sessionId} id={sessionId} />;
}
function Session({ id }: { id: string }) {
  const { data: s, error, setError, run, refresh, track } = useSession(id),
    [text, setText] = useDraftText(id),
    [busy, setBusy] = useState(false),
    [captureBusy, setCaptureBusy] = useState(false),
    [fixture, setFixture] = useState(followupFixtures[0].id),
    [showFollowup, setShowFollowup] = useState(false);
  const navigate = useNavigate();
  const audio = useRealtimeAsr({
    sessionId: id,
    revision: s?.revision || 1,
    text,
    onText: setText,
  });
  const blocker = useBlocker(audio.active);
  const [leaveAfterFinish, setLeaveAfterFinish] = useState(false);
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
  async function capture() {
    if (captureBusy) return;
    if (active.length >= 3) {
      setError("已有 3 个候选，请先移除一个，再 Capture。");
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
      setError((e as Error).message);
      if (e instanceof ApiError && e.code === "CONFLICT")
        await refresh().catch(() => {});
    } finally {
      setCaptureBusy(false);
    }
  }
  async function send() {
    const submitted = text;
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
      // Clear only the accepted submission, never new text typed during a slow response.
      if (localStorage.getItem(draftKey(id)) === submitted) setText("");
      audio.markSent();
      await track(r.run_id);
    });
  }
  async function start(intent: "prepare_report" | "analyze" | "followup") {
    await action(async () => {
      const r = await tess.run(id, session.revision, intent);
      await track(r.run_id);
    });
  }
  async function confirm(changes: FactChange[], skip: boolean) {
    setBusy(true);
    setError("");
    try {
      await tess.context(id, session.revision, changes, skip);
      const next = await refresh();
      if (skip) {
        const r = await tess.run(id, next.revision, "prepare_report");
        await track(r.run_id);
      }
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setBusy(false);
    }
  }
  async function continueRun() {
    const p = session.pending_run;
    if (!p) return;
    await action(async () => {
      const intent = p.effective_intent;
      const r =
        intent === "prepare_report" ||
        intent === "analyze" ||
        intent === "followup"
          ? await tess.run(id, session.revision, intent, p.run_id)
          : await tess.message(id, {
              text: "继续",
              source: "sales_text",
              expected_revision: session.revision,
              continue_run_id: p.run_id,
            });
      await track(r.run_id);
    });
  }
  return (
    <>
      <PageHeader title={s.customer.nickname}>
        <Link
          className="text-button"
          to={`/customers/${s.customer.id}/history/${id}`}
        >
          历史报告
        </Link>
      </PageHeader>
      <div className="session-bar">
        <span>{s.customer.contact_mask}</span>
        <button
          className="text-button"
          disabled={working || audio.active}
          onClick={() =>
            void action(async () => {
              const next = await tess.newSession(s.customer.id);
              navigate(`/sessions/${next.id}`);
            })
          }
        >
          ＋ 新建试驾
        </button>
      </div>
      <div className="scroll-area conversation">
        <IdentityEditor
          key={s.customer.revision}
          customer={s.customer}
          onSaved={refresh}
        />
        <div className="row between">
          <div>
            <p className="eyebrow">CURRENT OPTIONS</p>
            <h2>
              当前候选 <span className="muted">{active.length}/3</span>
            </h2>
          </div>
          <button
            className="secondary compact"
            disabled={captureBusy || working}
            onClick={() => void capture()}
          >
            {captureBusy
              ? "读取官网中…"
              : contractMock
                ? "＋ Mock Capture"
                : "＋ Capture"}
          </button>
        </div>
        {active.length === 0 && (
          <div className="notice">
            <p>在 Tesla 中国 Model Y 官网完成选配后，点击 Capture。</p>
            <a
              href="https://www.tesla.cn/modely/design#overview"
              target="_blank"
              rel="noreferrer"
            >
              打开 Model Y 配置器 ↗
            </a>
          </div>
        )}
        {active.length >= 3 && (
          <p className="micro muted">
            已保留 3 个候选。新增前请明确移除一个，不会覆盖原方案。
          </p>
        )}
        {active.map((c, i) => (
          <CaptureCard
            key={c.id}
            capture={c}
            index={i}
            ownerName={s.customer.nickname}
            busy={working || captureBusy}
            onRemove={() =>
              void action(() =>
                tess.updateCapture(id, c.id, s.revision, { active: false }),
              )
            }
            onPreference={(v) =>
              void action(() =>
                tess.updateCapture(id, c.id, s.revision, {
                  preference: v || null,
                }),
              )
            }
          />
        ))}
        <ContextCard
          facts={s.facts}
          questions={s.questions}
          busy={working}
          onConfirm={confirm}
        />
        <div className="conversation-divider">本次试驾复盘</div>
        {s.timeline.length === 0 && (
          <div className="assistant-message">
            <span className="tess-mark">t.</span>
            <div>
              <p>先说说这次试驾。</p>
              <p className="muted">
                实际试驾了哪个版本？客户已经明确了什么，还有哪些事没拿定主意？
              </p>
            </div>
          </div>
        )}
        {s.timeline.map((m) =>
          m.type === "report_card" ? (
            <a
              key={m.id}
              className="report-card"
              href={
                s.reports.find((r) => r.report_id === m.content.report_id)
                  ?.url || reportUrl(m.content.report_id!)
              }
              target="_blank"
              rel="noreferrer"
            >
              <span className="eyebrow">TEST DRIVE REPORT ↗</span>
              <h3>{m.content.title || "本次试驾报告"}</h3>
              <p>{date(m.content.published_at || m.created_at)}</p>
              <span>打开完整报告</span>
            </a>
          ) : (
            <div
              key={m.id}
              className={`message ${m.role === "sales" ? "sales-message" : "assistant-message"}`}
            >
              {m.role !== "sales" && <span className="tess-mark">t.</span>}
              <p>{m.content.text || "请在确认卡中核对本次信息。"}</p>
            </div>
          ),
        )}
        {run && (
          <div className="run-summary">
            <p className="eyebrow">执行记录</p>
            {run.events.map((e) => (
              <p key={e.seq}>{e.label}</p>
            ))}
            {run.error && <ErrorNotice message={run.error.message} />}
            <span className="muted micro">
              {(
                {
                  queued: "已接收，等待处理",
                  running: "正在处理",
                  needs_confirmation: "等待确认",
                  succeeded: "本轮完成",
                  failed: "本轮失败",
                  interrupted: "执行中断",
                } as Record<string, string>
              )[run.status] || run.status}
            </span>
          </div>
        )}
        {s.active_run && (
          <p role="status" className="notice">
            正在处理本次会话。可以切换客户，结果仍归属 {s.customer.nickname}。
          </p>
        )}
        {s.pending_run?.continuation.can_continue && (
          <button disabled={working} onClick={() => void continueRun()}>
            继续原任务
          </button>
        )}
        {s.draft && (
          <ReviewCard session={s} onRefresh={refresh} onError={setError} />
        )}
        <ErrorNotice message={error} />
        <div className="row wrap session-actions">
          <button
            disabled={working || captureBusy || !active.length}
            onClick={() => void start("prepare_report")}
          >
            {s.draft?.stale ? "重新准备报告" : "准备试驾报告"}
          </button>
          <button
            className="text-button"
            onClick={() => setShowFollowup(!showFollowup)}
          >
            后续动态 · Mock
          </button>
        </div>
        {showFollowup && (
          <section className="followup-card">
            <span className="tag warning">Mock 互动</span>
            <p className="muted micro">
              仅产品相关摘要，不展示家庭私人聊天，不推断购买意愿。
            </p>
            <select
              aria-label="模拟互动场景"
              value={fixture}
              onChange={(e) => setFixture(e.target.value)}
            >
              {followupFixtures.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>
            <button
              disabled={working || !s.reports.length}
              onClick={() =>
                void action(() => tess.events(id, s.revision, fixture))
              }
            >
              载入模拟互动
            </button>
            <button
              disabled={working || !s.reports.length}
              onClick={() => void start("followup")}
            >
              生成跟进建议
            </button>
            {s.followup && (
              <div>
                <p>{display(s.followup.brief)}</p>
                <small className="muted">
                  来源事件：{display(s.followup.source_event_ids)}
                </small>
              </div>
            )}
            {!s.reports.length && (
              <p className="muted micro">先发布本次报告，再演示后续互动。</p>
            )}
          </section>
        )}
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
      <Composer
        text={text}
        onChange={audio.edit}
        onSend={() => void send()}
        busy={working}
        audio={audio}
      />
    </>
  );
}
