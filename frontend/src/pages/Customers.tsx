import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { tess } from "../services/tess";
import type { CustomerSummary, Health } from "../types/api";
import { Empty, ErrorNotice, Loading, PageHeader } from "../components/Shared";
export default function Customers() {
  const [items, setItems] = useState<CustomerSummary[]>([]),
    [q, setQ] = useState(""),
    [cursor, setCursor] = useState<string | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(true),
    [health, setHealth] = useState<Health | null>(null);
  const navigate = useNavigate();
  useEffect(() => {
    let alive = true;
    setBusy(true);
    tess
      .customers(q)
      .then((r) => {
        if (alive) {
          setItems(r.items);
          setCursor(r.next_cursor);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
  }, [q]);
  useEffect(() => {
    tess
      .health()
      .then(setHealth)
      .catch(() => {});
  }, []);
  const open = async (c: CustomerSummary) => {
    setError("");
    try {
      if (c.latest_session_id) navigate(`/sessions/${c.latest_session_id}`);
      else {
        const s = await tess.newSession(c.id);
        navigate(`/sessions/${s.id}`);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <>
      <PageHeader title="用户列表" />
      <div className="page-intro">
        <div>
          <p className="eyebrow">暂缓设计</p>
          <h1>今日客户</h1>
        </div>
      </div>
      <div className="search">
        <span aria-hidden>⌕</span>
        <input
          aria-label="搜索客户"
          placeholder="搜索称呼、手机号或邮箱"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <div className="scroll-area">
        <ErrorNotice message={error} retry={() => location.reload()} />
        {busy ? (
          <Loading />
        ) : items.length ? (
          <div className="customer-list">
            {items.map((c) => (
              <button
                className="customer-row"
                key={c.id}
                onClick={() => void open(c)}
              >
                <span className="customer-avatar">
                  {c.nickname.slice(0, 1)}
                </span>
                <span className="grow">
                  <strong>{c.nickname}</strong>
                  <small>{c.contact_mask}</small>
                  <span className="muted micro">
                    {c.latest_session_id
                      ? "继续最近一次试驾复盘"
                      : "开始首次试驾复盘"}
                  </span>
                </span>
                <span className="muted">↗</span>
              </button>
            ))}
            {cursor && (
              <button
                onClick={() =>
                  void tess
                    .customers(q, cursor)
                    .then((r) => {
                      setItems((old) => [...old, ...r.items]);
                      setCursor(r.next_cursor);
                    })
                    .catch((e) => setError(e.message))
                }
              >
                加载更多客户
              </button>
            )}
          </div>
        ) : (
          <Empty title={q ? "没有匹配客户" : "从一位客户开始"}>
            先确认客户称呼与联系方式，再记录本次试驾和候选方案。
          </Empty>
        )}
        {health && (
          <div className="capability-note">
            <strong>本机工作空间</strong>
            <p>
              官网采集在插件内使用。
              <br />
              模型{" "}
              {health.capabilities.llm === "configured" ? "已配置" : "待配置"} ·
              实时转写{" "}
              {health.capabilities.asr === "configured" ? "已配置" : "待配置"} ·
              高德{" "}
              {health.capabilities.maps === "configured" ? "已配置" : "待配置"}
            </p>
          </div>
        )}
      </div>
      <footer className="quiet-footer">每次试驾，留下一份清楚的复盘。</footer>
    </>
  );
}
