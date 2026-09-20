import { Navigate, createRoutesFromElements, Route } from "react-router";
import Home from "../pages/Home";
import Customers from "../pages/Customers";
import NewCustomer from "../pages/NewCustomer";
import Session from "../pages/Session";
import Plans from "../pages/Plans";
import History from "../pages/History";
import Report from "../pages/Report";
import { Brand, ModeBanner } from "../components/Shared";
import type { ReactNode } from "react";
function Shell({ children }: { children: ReactNode }) {
  return (
    <main className="sidepanel">
      <Brand />
      <ModeBanner />
      {children}
    </main>
  );
}
export const appRoutes = createRoutesFromElements(
  <>
    <Route
      path="/"
      element={
        <Shell>
          <Home />
        </Shell>
      }
    />
    <Route
      path="/customers"
      element={
        <Shell>
          <Customers />
        </Shell>
      }
    />
    <Route
      path="/customers/new"
      element={
        <Shell>
          <NewCustomer />
        </Shell>
      }
    />
    <Route
      path="/sessions/:sessionId"
      element={
        <Shell>
          <Session />
        </Shell>
      }
    />
    <Route
      path="/sessions/:sessionId/plans"
      element={
        <Shell>
          <Plans />
        </Shell>
      }
    />
    <Route
      path="/customers/:customerId/history/:sessionId"
      element={
        <Shell>
          <History />
        </Shell>
      }
    />
    <Route path="/reports/:reportId" element={<Report />} />
    <Route path="/preview/:sessionId" element={<Report preview />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </>,
);
