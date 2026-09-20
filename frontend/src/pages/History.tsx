import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { tess } from "../services/tess";
import type { ReportSummary, SessionSummary } from "../types/api";
import { PageHeader, ErrorNotice, Empty } from "../components/Shared";
import { date } from "../utils/display";
export default function History() {
  const { customerId = "", sessionId = "" } = useParams();
  const [reports, setReports] = useState<ReportSummary[]>([]),
    [sessions, setSessions] = useState<SessionSummary[]>([]),
    [error, setError] = useState(""),
    [cursor, setCursor] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([tess.reports(customerId), tess.sessions(customerId)])
      .then(([r, s]) => {
        if (alive) {
          setReports(r.items);
          setCursor(r.next_cursor);
          setSessions(s.items);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [customerId]);
  return (
    <>
      <PageHeader title="历史报告" back={`/sessions/${sessionId}`} />
      <div className="scroll-area">
        <p className="muted">
          同一客户历次试驾的已发布报告。原链接保留原内容。
        </p>
        <ErrorNotice message={error} />
        {reports.map((r) => (
          <a
            className="report-card"
            key={r.report_id}
            href={r.url}
            target="_blank"
            rel="noreferrer"
          >
            <span className="eyebrow">TEST DRIVE REPORT ↗</span>
            <h3>{r.title}</h3>
            <p>
              {date(r.published_at)} · {r.session_title}
            </p>
            <span>打开完整报告</span>
          </a>
        ))}
        {!reports.length && !error && (
          <Empty title="还没有已发布报告">
            审核本次复盘后，报告会保存在这里。
          </Empty>
        )}
        {cursor && (
          <button
            onClick={() =>
              void tess
                .reports(customerId, cursor)
                .then((r) => {
                  setReports((old) => [...old, ...r.items]);
                  setCursor(r.next_cursor);
                })
                .catch((e) => setError(e.message))
            }
          >
            加载更多报告
          </button>
        )}
        <section className="section-separator">
          <h2>历次试驾会话</h2>
          {sessions.map((s) => (
            <Link className="session-row" key={s.id} to={`/sessions/${s.id}`}>
              <strong>{s.title}</strong>
              <small>
                {date(s.created_at)} ·{" "}
                {s.latest_report_id ? "已发布报告" : "复盘中"}
              </small>
            </Link>
          ))}
        </section>
      </div>
    </>
  );
}
