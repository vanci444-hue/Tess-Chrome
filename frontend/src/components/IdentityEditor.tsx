import { useState } from "react";
import type { SessionDetail } from "../types/api";
import { tess } from "../services/tess";
import { ApiError } from "../services/api";
import { ErrorNotice } from "./Shared";
export default function IdentityEditor({
  customer,
  onSaved,
}: {
  customer: SessionDetail["customer"];
  onSaved: () => Promise<unknown>;
}) {
  const [name, setName] = useState(customer.nickname),
    [phone, setPhone] = useState(customer.phone || ""),
    [email, setEmail] = useState(customer.email || ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [duplicate, setDuplicate] = useState(false);
  async function save(allow = false) {
    setBusy(true);
    setError("");
    try {
      await tess.editCustomer(customer.id, {
        expected_revision: customer.revision,
        nickname: name.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        identity_confirmed: confirmed,
        allow_duplicate: allow,
      });
      await onSaved();
      setConfirmed(false);
      setDuplicate(false);
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && e.metadata.reason === "DUPLICATE_CONTACT")
        setDuplicate(true);
      if (e instanceof ApiError && e.metadata.reason === "STALE_REVISION")
        await onSaved();
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="identity-editor">
      <summary>纠正客户称呼 / 联系方式</summary>
      <form
        className="form-stack"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <p className="muted micro">
          只影响后续报告；已发布报告保持原样。联系方式不会进入报告。
        </p>
        <label>
          称呼
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setConfirmed(false);
            }}
            required
            maxLength={80}
          />
        </label>
        <label>
          手机号
          <input
            value={phone}
            onChange={(e) => {
              setPhone(e.target.value);
              setConfirmed(false);
            }}
            inputMode="tel"
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
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          已核对本次客户身份
        </label>
        <ErrorNotice message={error} />
        {duplicate && (
          <button
            type="button"
            disabled={busy || !confirmed}
            onClick={() => void save(true)}
          >
            确认属于不同客户，保留独立档案
          </button>
        )}
        <button
          disabled={
            busy ||
            !confirmed ||
            !name.trim() ||
            (!phone.trim() && !email.trim())
          }
        >
          保存身份信息
        </button>
      </form>
    </details>
  );
}
