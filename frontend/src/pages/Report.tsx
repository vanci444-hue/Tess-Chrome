import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { tess } from "../services/tess";
import type { ReportSnapshot } from "../types/api";
import { ErrorNotice, Loading, ModeBanner } from "../components/Shared";
import { date } from "../utils/display";
import { moduleData, optionsFrom, safeOfficialUrl } from "../utils/reportData";
import {
  OptionsModule,
  FinanceModule,
  EnergyModule,
  ChargingModule,
  FamilyModule,
  TrialModule,
  MissingModule,
  StaticAsk,
} from "../components/ReportModules";
import "../report.css";
export default function Report({ preview = false }: { preview?: boolean }) {
  const { reportId, sessionId } = useParams();
  // Each report owns its loading and map states; never show the prior customer's snapshot.
  return <ReportContent key={`${preview ? "preview" : "report"}:${reportId || sessionId}`} preview={preview} />;
}
function ReportContent({ preview }: { preview: boolean }) {
  const { reportId = "", sessionId = "" } = useParams(),
    [data, setData] = useState<ReportSnapshot | null>(null),
    [error, setError] = useState(""),
    [stale, setStale] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      if (preview) {
        const s = await tess.session(sessionId);
        if (!s.draft) throw new Error("本次会话尚无可预览草稿");
        if (alive)
          setStale(s.draft.stale || s.draft.source_revision !== s.revision);
        return s.draft.report_data;
      }
      return tess.report(reportId);
    };
    load()
      .then((r) => {
        if (alive) setData(r);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [reportId, sessionId, preview]);
  const options = data ? optionsFrom(data.modules) : [],
    advisorModule = data?.modules.find((m) => m.type === "advisor"),
    advisor = advisorModule
      ? moduleData<{
          id: string;
          name: string;
          store_name: string;
          is_demo: boolean;
        }>(advisorModule)
      : null;
  return (
    <main className="report-page">
      <ModeBanner />
      <header className="report-topbar">
        <span className="wordmark">
          tess<span>·</span>
        </span>
        <span>TEST DRIVE REPORT</span>
        <span>{preview ? "草稿预览" : "试驾后的下一步"}</span>
      </header>
      <ErrorNotice message={error} />
      {!data && !error && <Loading />}
      {data && (
        <>
          {preview && (
            <div className={`notice ${stale ? "warning" : ""}`}>
              {stale
                ? "草稿待更新，不能发布。请回销售侧重新准备。"
                : "销售审核预览 · 尚未发布，不代表最终报告。"}
            </div>
          )}
          <header className="report-hero">
            <p className="eyebrow">{date(data.generated_at)} · MODEL Y</p>
            <h1>{data.customer_salutation}</h1>
            <p className="hero-subtitle">把这次试驾，带回家慢慢聊。</p>
            <div className="three-questions">
              <section>
                <span>01 / 正在比较</span>
                <h2>现在比较什么</h2>
                <p>{data.summary.comparing || "候选方案仍待确认"}</p>
              </section>
              <section>
                <span>02 / 阶段性判断</span>
                <h2>已经明确什么</h2>
                {data.summary.confirmed.length ? (
                  <ul>
                    {data.summary.confirmed.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                ) : (
                  <p>暂无已确认结论。</p>
                )}
              </section>
              <section>
                <span>03 / 下一步</span>
                <h2>还需确认什么</h2>
                {data.summary.pending.length ? (
                  <ul>
                    {data.summary.pending.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                ) : (
                  <p>本次暂未记录新的待确认事项。</p>
                )}
              </section>
            </div>
          </header>
          {data.modules
            .filter((m) => m.type === "trial")
            .map((m, i) => (
              <TrialModule module={m} key={`trial-${i}`} />
            ))}
          {options.length > 0 && (
            <OptionsModule options={options} modules={data.modules} />
          )}
          <div className="report-modules">
            {data.modules
              .filter((m) => !["options", "trial", "advisor"].includes(m.type))
              .map((m, i) => {
                // Map retrieval can fail after real station lookup succeeds.
                // Preserve those stations instead of collapsing the whole module.
                if (
                  m.type === "charging" &&
                  Array.isArray(m.data.stations) &&
                  typeof m.data.region === "string"
                )
                  return (
                    <ChargingModule
                      key={i}
                      module={m}
                      owner={preview ? sessionId : reportId}
                      preview={preview}
                    />
                  );
                if (m.status === "missing" || m.type === "missing")
                  return <MissingModule module={m} key={i} />;
                switch (m.type) {
                  case "finance":
                    return (
                      <FinanceModule key={i} module={m} options={options} />
                    );
                  case "energy":
                    return <EnergyModule key={i} module={m} />;
                  case "charging":
                    return (
                      <ChargingModule
                        key={i}
                        module={m}
                        owner={preview ? sessionId : reportId}
                        preview={preview}
                      />
                    );
                  case "family":
                    return <FamilyModule key={i} module={m} />;
                  default:
                    return <MissingModule key={i} module={m} />;
                }
              })}
          </div>
          <section className="report-section ask-section">
            <div className="section-heading">
              <p className="eyebrow">ASK TESS</p>
              <h2>从这次试驾，继续聊下去。</h2>
              <p>
                可以基于当前候选、家庭需求和待确认事项继续提问。当前页面的问答、分享和联系按钮仅为
                Prototype 展示。
              </p>
            </div>
            <div className="ask-grid">
              <StaticAsk>没有家充，日常通勤如何安排？</StaticAsk>
              <StaticAsk>更高预算带来的体验差别是什么？</StaticAsk>
              <StaticAsk>下次到店，还应该重点体验什么？</StaticAsk>
            </div>
          </section>
          <section className="advisor-section">
            <div>
              <p className="eyebrow">YOUR SALES ADVISOR</p>
              <h2>{advisor?.name || "销售顾问信息待确认"}</h2>
              <p>{advisor?.store_name || "门店信息待确认"}</p>
              {advisor?.is_demo && (
                <span className="tag">Demo · 模拟销售身份</span>
              )}
            </div>
            <div>
              <p>
                如果某个问题还不能可靠回答，可以带着这次试驾的背景继续与销售确认。
              </p>
              <div className="row wrap">
                <button disabled>联系销售 · 演示</button>
                <button disabled>分享给家人 · 演示</button>
              </div>
            </div>
          </section>
          <footer className="report-sources">
            <h3>信息来源与时间</h3>
            <p>
              报告生成：{date(data.generated_at)}
              {data.published_at ? ` · 发布：${date(data.published_at)}` : ""}
            </p>
            {data.sources.map((source) => (
              <div className="source-row" key={source.id}>
                <span>
                  {source.label} · {source.kind}
                </span>
                <span>{date(source.observed_at)}</span>
                {source.url && safeOfficialUrl(source.url) && (
                  <a
                    href={safeOfficialUrl(source.url)!}
                    target="_blank"
                    rel="noreferrer"
                  >
                    官方来源 ↗
                  </a>
                )}
              </div>
            ))}
            <p>{data.disclaimer}</p>
            <p>
              价格、金融、权益、交付和站点状态可能变化。本页保留原采集时间，不自动刷新为当前有效信息。
            </p>
            <span className="report-signoff">tess · A clearer next step.</span>
          </footer>
        </>
      )}
    </main>
  );
}
