import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { ErrorNotice } from "../components/Shared";
import { Icon } from "../components/Icon";
import { DEMO_CRM_TEXT, profileFromCrm } from "../mocks/demoCrm";

export default function Home() {
  const navigate = useNavigate();
  const [crm, setCrm] = useState("");
  const [filled, setFilled] = useState("");
  const [error, setError] = useState("");

  function fillDemo() {
    setError("");
    setCrm(DEMO_CRM_TEXT);
    setFilled("已填入演示资料");
    window.setTimeout(() => setFilled(""), 2000);
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
          placeholder="粘贴客户资料或截屏"
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
        <button type="button" className="demo-copy" onClick={fillDemo}>
          {filled || "复制演示 CRM"}
        </button>
        <p className="muted micro">
          仅 Demo：一点即填入客户甲资料，无需再走剪贴板。
        </p>
      </div>
    </div>
  );
}
