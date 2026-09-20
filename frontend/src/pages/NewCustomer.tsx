import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { tess } from "../services/tess";
import { PageHeader, ErrorNotice } from "../components/Shared";
import { profileFromCrm } from "../mocks/demoCrm";

export default function NewCustomer() {
  const navigate = useNavigate();
  const crm = String((useLocation().state as { crm?: string } | null)?.crm || "");
  const profile = useMemo(() => profileFromCrm(crm), [crm]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function create() {
    if (!profile || busy) return;
    setBusy(true);
    setError("");
    try {
      const c = await tess.createCustomer({
        nickname: profile.nickname,
        phone: profile.phone || null,
        email: profile.email || null,
        allow_duplicate: true,
        identity_confirmed: true,
      });
      const s = await tess.newSession(c.id);
      navigate(`/sessions/${s.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!profile) {
    return (
      <>
        <PageHeader title="确认客户资料" />
        <div className="scroll-area">
          <p className="muted">请先在首页粘贴客户资料。</p>
          <Link className="button primary compact" to="/">
            返回首页
          </Link>
        </div>
      </>
    );
  }

  const ride = profile.appointment;

  return (
    <>
      <PageHeader title="确认客户资料" />
      <div className="scroll-area form-stack">
        <p className="muted">已从粘贴内容整理出本次接待要用的资料，请确认。</p>
        {ride && (
          <aside className="visit-callout">
            <p className="visit-callout-label">预约试驾</p>
            <p className="visit-callout-main">
              {ride.when} 到{ride.store}
            </p>
            <p className="visit-callout-car">试驾 {ride.vehicle}</p>
          </aside>
        )}
        <dl className="profile-summary">
          <div>
            <dt>称呼</dt>
            <dd>{profile.nickname}</dd>
          </div>
          <div>
            <dt>电话</dt>
            <dd>{profile.phone || "未提供"}</dd>
          </div>
          <div>
            <dt>邮箱</dt>
            <dd>{profile.email || "未提供"}</dd>
          </div>
        </dl>
        {profile.points.length > 0 && (
          <section className="profile-points">
            <h2>重点信息</h2>
            <ul>
              {profile.points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          </section>
        )}
        <ErrorNotice message={error} />
        <button
          className="primary"
          type="button"
          disabled={busy}
          onClick={() => void create()}
        >
          {busy ? "正在处理…" : "确认"}
        </button>
      </div>
    </>
  );
}
