import type { ReactNode } from "react";
import { Link } from "react-router";
import { contractMock } from "../services/api";
export function Brand() {
  return (
    <div className="brand-row">
      <Link className="wordmark" to="/">
        tess<span>·</span>
      </Link>
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
  back = "/",
  children,
}: {
  title: string;
  back?: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-header">
      <Link className="icon-button" to={back} aria-label="返回">
        ←
      </Link>
      <h1>{title}</h1>
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
  return contractMock ? (
    <div className="mode-banner">
      Mock · 前端契约演示，未调用真实官网、模型或地图
    </div>
  ) : null;
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
