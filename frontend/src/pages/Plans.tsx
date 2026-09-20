import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { tess } from "../services/tess";
import { PageHeader, Loading, ErrorNotice, Empty } from "../components/Shared";
import { Icon } from "../components/Icon";
import CaptureCard from "../components/CaptureCard";
import {
  loadAppliedPlans,
  mergeWorkingOptions,
  type AppliedPlan,
} from "../mocks/sessionPlans";
import type { Capture } from "../types/api";

export default function Plans() {
  const { sessionId = "" } = useParams();
  const [customerId, setCustomerId] = useState("");
  const [nickname, setNickname] = useState("当前客户");
  const [contact, setContact] = useState<string | undefined>();
  const [active, setActive] = useState<Capture[]>([]);
  const [plans, setPlans] = useState<AppliedPlan[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    tess
      .session(sessionId)
      .then((detail) => {
        if (!alive) return;
        setCustomerId(detail.customer.id);
        setNickname(detail.customer.nickname);
        setContact(detail.customer.contact_mask);
        setActive(detail.captures.filter((item) => item.active));
        setPlans(loadAppliedPlans(sessionId));
        setError("");
      })
      .catch((e) => {
        if (alive) setError((e as Error).message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [sessionId]);

  const working = mergeWorkingOptions(active, plans);

  return (
    <>
      <PageHeader
        title={nickname}
        subtitle={contact}
        back={`/sessions/${sessionId}`}
      >
        <div className="page-header-actions">
          <Link
            className="quiet-icon-link is-active"
            to={`/sessions/${sessionId}/plans`}
            aria-label="已生成方案"
            title="已生成方案"
          >
            <Icon name="plans" size={18} />
          </Link>
          <Link
            className="quiet-icon-link"
            to={
              customerId
                ? `/customers/${customerId}/history/${sessionId}`
                : `/sessions/${sessionId}`
            }
            aria-label="历史报告"
            title="历史报告"
          >
            <Icon name="history" size={18} />
          </Link>
        </div>
      </PageHeader>
      <div className="scroll-area conversation">
        <div className="row between">
          <div>
            <p className="eyebrow">WORKING OPTIONS</p>
            <h2>已生成方案</h2>
          </div>
        </div>
        <p className="muted plans-lead">
          金融规划确认后的工作候选。已生成的 V1 会直接替代对应 Option。
        </p>
        <ErrorNotice message={error} />
        {loading && <Loading />}
        {!loading && working.length === 0 && (
          <Empty title="还没有候选">先在会话里 Capture 或进入场景 3。</Empty>
        )}
        {!loading && working.length > 0 && plans.length === 0 && (
          <div className="notice">
            <p>
              还没有生成方案。在会话里完成金融规划，并点「按方案更改」后，会显示在这里。
            </p>
          </div>
        )}
        {!loading &&
          working.map((item) => (
            <div key={`${item.optionNumber}-${item.versionTag || "base"}`}>
              {item.replaced ? (
                <p className="plans-replace-note">
                  Option {item.optionNumber} 已由方案 {item.planId} 更新为{" "}
                  {item.versionTag}
                </p>
              ) : null}
              <CaptureCard
                capture={item.capture}
                index={item.optionNumber - 1}
                optionNumber={item.optionNumber}
                versionTag={item.versionTag}
                readOnly={item.replaced}
                busy={false}
                onRemove={() => {}}
                onConfirmFinance={async () => {}}
              />
            </div>
          ))}
      </div>
    </>
  );
}
