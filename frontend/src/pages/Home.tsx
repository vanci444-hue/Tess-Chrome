import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { ErrorNotice } from "../components/Shared";
import { Icon } from "../components/Icon";
import { DEMO_CRM_TEXT, profileFromCrm } from "../mocks/demoCrm";

export default function Home() {
  const navigate = useNavigate();
  const [crm, setCrm] = useState("");
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");

  async function copyDemo() {
    setError("");
    try {
      await navigator.clipboard.writeText(DEMO_CRM_TEXT);
      setCopied("已复制演示资料");
      window.setTimeout(() => setCopied(""), 2000);
    } catch {
      setError("复制失败，请长按选中后手动复制。");
    }
  }

  function submit() {
    const text = crm.trim();
    if (!text) return;
    if (!profileFromCrm(text)) {
      setError("没有整理出称呼和联系方式，请检查粘贴内容后重试。");
      return;
    }
    navigate("/customers/new", { state: { crm: text } });
  }

  return (
    <div className="home-desk">
      <Link className="list-entry" to="/customers">
        用户列表
      </Link>
      <div className="crm-paste">
        <label className="sr-only" htmlFor="crm-paste">
          CRM 粘贴区
        </label>
        <textarea
          id="crm-paste"
          rows={10}
          value={crm}
          onChange={(e) => {
            setCrm(e.target.value);
            setError("");
          }}
          placeholder="粘贴客户资料"
        />
        <button
          type="button"
          className="paste-submit"
          disabled={!crm.trim()}
          aria-label="提交粘贴内容"
          onClick={submit}
        >
          <Icon name="send" size={18} />
        </button>
      </div>
      <ErrorNotice message={error} />
      <div className="demo-copy-row">
        <button type="button" className="demo-copy" onClick={() => void copyDemo()}>
          {copied || "复制演示 CRM"}
        </button>
        <p className="muted micro">
          仅 Demo：假装已经从 CRM 拷好资料，再贴进上面的区域。
        </p>
      </div>
    </div>
  );
}
