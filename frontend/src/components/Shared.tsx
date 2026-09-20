import { useState, type ReactNode, useEffect } from "react";
import { Link, useNavigate } from "react-router";
import { api, contractMock } from "../services/api";
import { Icon } from "./Icon";
import { ensureJiaSession } from "../mocks/demoScenes";
import { prepareFinanceScene } from "../mocks/demoFinance";
import { prepareKnowledgeScene } from "../mocks/knowledgeCopilot";
import { prepareDecisionScene } from "../mocks/decisionContext";
import { prepareReportScene } from "../mocks/reportScene";

export function ResetDemoButton({ className = "text-button" }: { className?: string }) {
  const [resetting, setResetting] = useState(false);
  async function resetDemo() {
    if (
      resetting ||
      !window.confirm(
        "刷新 Demo 将清空本机全部演示客户、试驾会话、候选方案和报告；原报告链接将失效。API 配置保留。确认清空并重新开始？",
      )
    )
      return;
    setResetting(true);
    try {
      if (!contractMock)
        await api.post("/demo/reset", { confirmation: "RESET_DEMO" });
      for (const key of Object.keys(localStorage)) {
        if (
          key.startsWith("tess.unsent.v1.") ||
          key.startsWith("tess.publish.") ||
          key.startsWith("tess.demo.draft.v1.") ||
          key.startsWith("tess.demo.report.html.") ||
          (contractMock && key === "tess-contract-mock-v2")
        )
          localStorage.removeItem(key);
      }
      window.location.replace(
        `${window.location.pathname}${window.location.search}#/`,
      );
      window.location.reload();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "刷新失败，请重试");
      setResetting(false);
    }
  }
  return (
    <button
      className={className}
      type="button"
      disabled={resetting}
      onClick={resetDemo}
      aria-label="刷新 Demo"
      title="刷新 Demo"
    >
      <Icon name="refresh" size={16} />
    </button>
  );
}

const SCENE_HOVER: Record<number, string> = {
  1: "预录入",
  2: "Capture",
  3: "金融",
  4: "Knowledge",
  5: "语音",
  6: "导出报告",
};

export function Brand() {
  const navigate = useNavigate();
  const [opening, setOpening] = useState(false);

  async function openScene2() {
    if (opening) return;
    setOpening(true);
    try {
      const id = await ensureJiaSession();
      navigate(`/sessions/${id}`);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "无法打开场景 2");
    } finally {
      setOpening(false);
    }
  }

  async function openScene3() {
    if (opening) return;
    setOpening(true);
    try {
      const id = await ensureJiaSession();
      await prepareFinanceScene(id);
      navigate(`/sessions/${id}`, {
        state: { financeSceneAt: Date.now() },
        replace: false,
      });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "无法打开场景 3");
    } finally {
      setOpening(false);
    }
  }

  async function openScene4() {
    if (opening) return;
    setOpening(true);
    try {
      const id = await ensureJiaSession();
      await prepareKnowledgeScene(id);
      navigate(`/sessions/${id}`, {
        state: { knowledgeSceneAt: Date.now() },
        replace: false,
      });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "无法打开场景 4");
    } finally {
      setOpening(false);
    }
  }

  async function openScene5() {
    if (opening) return;
    setOpening(true);
    try {
      const id = await ensureJiaSession();
      await prepareDecisionScene(id);
      navigate(`/sessions/${id}`, {
        state: { decisionSceneAt: Date.now() },
        replace: false,
      });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "无法打开场景 5");
    } finally {
      setOpening(false);
    }
  }

  async function openScene6() {
    if (opening) return;
    setOpening(true);
    try {
      const id = await ensureJiaSession();
      await prepareReportScene(id);
      navigate(`/sessions/${id}`, {
        state: { reportSceneAt: Date.now() },
        replace: false,
      });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "无法打开场景 6");
    } finally {
      setOpening(false);
    }
  }

  return (
    <div className="brand-row">
      <Link className="wordmark" to="/" aria-label="Tess">
        Tess
      </Link>
      <div className="brand-tools">
        <ResetDemoButton className="demo-reset-icon" />
        {[1, 2, 3, 4, 5, 6].map((n) => {
          const label = SCENE_HOVER[n];
          if (n === 1) {
            return (
              <Link
                key={n}
                className="brand-tool-num"
                to="/"
                aria-label={label}
                data-tip={label}
              >
                {n}
              </Link>
            );
          }
          if (n === 2) {
            return (
              <button
                key={n}
                type="button"
                className="brand-tool-num"
                aria-label={label}
                data-tip={label}
                disabled={opening}
                onClick={() => void openScene2()}
              >
                {n}
              </button>
            );
          }
          if (n === 3) {
            return (
              <button
                key={n}
                type="button"
                className="brand-tool-num"
                aria-label={label}
                data-tip={label}
                disabled={opening}
                onClick={() => void openScene3()}
              >
                {n}
              </button>
            );
          }
          if (n === 4) {
            return (
              <button
                key={n}
                type="button"
                className="brand-tool-num"
                aria-label={label}
                data-tip={label}
                disabled={opening}
                onClick={() => void openScene4()}
              >
                {n}
              </button>
            );
          }
          if (n === 5) {
            return (
              <button
                key={n}
                type="button"
                className="brand-tool-num"
                aria-label={label}
                data-tip={label}
                disabled={opening}
                onClick={() => void openScene5()}
              >
                {n}
              </button>
            );
          }
          if (n === 6) {
            return (
              <button
                key={n}
                type="button"
                className="brand-tool-num"
                aria-label={label}
                data-tip={label}
                disabled={opening}
                onClick={() => void openScene6()}
              >
                {n}
              </button>
            );
          }
          return (
            <button
              key={n}
              type="button"
              className="brand-tool-num"
              aria-label={label}
              data-tip={label}
            >
              {n}
            </button>
          );
        })}
      </div>
      <div className="advisor">
        <span className="avatar">A</span>
        <span>
          Alex <small>销售顾问 · Demo</small>
        </span>
      </div>
    </div>
  );
}
export function PageHeader({
  title,
  subtitle,
  back = "/",
  children,
}: {
  title: string;
  subtitle?: string;
  back?: string;
  children?: ReactNode;
}) {
  return (
    <header className={subtitle ? "page-header with-sub" : "page-header"}>
      <Link className="icon-button" to={back} aria-label="返回">
        <Icon name="back" size={20} />
      </Link>
      <div className="page-header-copy">
        <h1>{title}</h1>
        {subtitle ? <p className="page-header-sub">{subtitle}</p> : null}
      </div>
      {children}
    </header>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return message ? (
    <div role="alert" className="notice error">
      {message}
      {retry && (
        <button className="text-button" onClick={retry}>
          重试
        </button>
      )}
    </div>
  ) : null;
}
export function Toast({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(onDismiss, 3200);
    return () => window.clearTimeout(timer);
  }, [message, onDismiss]);
  return message ? (
    <div className="plugin-toast" role="status">
      {message}
    </div>
  ) : null;
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-mark">t.</div>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      正在读取本机记录…
    </div>
  );
}
export function ModeBanner() {
  return null;
}
export function SourceTag({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`tag ${tone}`}>{children}</span>;
}
