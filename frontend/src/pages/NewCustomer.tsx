import { useState } from "react";
import { useNavigate } from "react-router";
import { tess } from "../services/tess";
import { ApiError } from "../services/api";
import type { CustomerSummary, Extraction } from "../types/api";
import { PageHeader, ErrorNotice } from "../components/Shared";
export default function NewCustomer() {
  const navigate = useNavigate();
  const [nickname, setNickname] = useState(""),
    [phone, setPhone] = useState(""),
    [email, setEmail] = useState(""),
    [crm, setCrm] = useState(""),
    [extraction, setExtraction] = useState<Extraction | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [confirmed, setConfirmed] = useState(false),
    [duplicates, setDuplicates] = useState<CustomerSummary[]>([]);
  async function extract() {
    setBusy(true);
    setError("");
    try {
      const r = await tess.extract(crm);
      setExtraction(r);
      setNickname(r.proposed.nickname || "");
      setPhone(r.proposed.phone || "");
      setEmail(r.proposed.email || "");
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function create(allow = false) {
    setBusy(true);
    setError("");
    try {
      const c = await tess.createCustomer({
        nickname: nickname.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        allow_duplicate: allow,
        identity_confirmed: confirmed,
        ...(extraction ? { extraction_id: extraction.extraction_id } : {}),
      });
      const s = await tess.newSession(c.id);
      navigate(`/sessions/${s.id}`);
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && e.metadata.reason === "DUPLICATE_CONTACT")
        setDuplicates(
          (e.metadata.candidates ||
            e.metadata.duplicates ||
            []) as CustomerSummary[],
        );
    } finally {
      setBusy(false);
    }
  }
  async function existing(c: CustomerSummary) {
    setBusy(true);
    try {
      const list = await tess.sessions(c.id);
      if (list.items[0]) navigate(`/sessions/${list.items[0].id}`);
      else {
        const s = await tess.newSession(c.id);
        navigate(`/sessions/${s.id}`);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader title="新增客户" />
      <form
        className="scroll-area form-stack"
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
      >
        <p className="muted">先确认称呼与联系方式。本次复盘只属于这位客户。</p>
        <label>
          客户称呼 <span className="required">*</span>
          <input
            required
            maxLength={80}
            value={nickname}
            onChange={(e) => {
              setNickname(e.target.value);
              setConfirmed(false);
            }}
            placeholder="例如 Evan 先生"
            autoComplete="off"
          />
        </label>
        <label>
          手机号 <span className="muted micro">中国大陆，其他地区请带区号</span>
          <input
            value={phone}
            onChange={(e) => {
              setPhone(e.target.value);
              setConfirmed(false);
            }}
            placeholder="手机号与邮箱至少填写一项"
            inputMode="tel"
            autoComplete="off"
          />
        </label>
        <label>
          邮箱
          <input
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setConfirmed(false);
            }}
            placeholder="name@example.com"
            autoComplete="off"
          />
        </label>
        <details className="crm-section">
          <summary>从 CRM 粘贴已有资料</summary>
          <p className="muted micro">
            提取后先预览、补齐与确认。历史预算不会自动作为本次预算。
          </p>
          <textarea
            rows={5}
            value={crm}
            onChange={(e) => setCrm(e.target.value)}
            placeholder="粘贴必要客户信息，无需整理格式"
          />
          <button
            type="button"
            disabled={busy || !crm.trim()}
            onClick={() => void extract()}
          >
            提取预览
          </button>
          {extraction && (
            <div className="notice">
              已填入可识别的信息，请在上方检查。
              {extraction.missing.length > 0 && "仍有必填信息待补齐。"}
              {extraction.historical_facts.length > 0 && (
                <p>
                  已保留 {extraction.historical_facts.length}{" "}
                  条历史参考，本次需重新确认。
                </p>
              )}
            </div>
          )}
        </details>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          我已核对客户称呼及联系方式
        </label>
        <ErrorNotice message={error} />
        {duplicates.length > 0 && (
          <div className="notice">
            <strong>发现相同联系方式</strong>
            <p>可能是同一位客户再次试驾，也可能是不同的人。</p>
            {duplicates.map((c) => (
              <button type="button" key={c.id} onClick={() => void existing(c)}>
                进入 {c.nickname} · {c.contact_mask}
              </button>
            ))}
            <button
              type="button"
              disabled={busy || !confirmed}
              onClick={() => void create(true)}
            >
              确认是不同客户，独立建档
            </button>
          </div>
        )}
        <button
          className="primary"
          disabled={
            busy ||
            !nickname.trim() ||
            (!phone.trim() && !email.trim()) ||
            !confirmed
          }
        >
          {busy ? "正在处理…" : "确认并开始复盘"}
        </button>
      </form>
    </>
  );
}
