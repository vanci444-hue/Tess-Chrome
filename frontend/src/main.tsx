import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  createBrowserRouter,
  createHashRouter,
  RouterProvider,
} from "react-router";
import { appRoutes } from "./router";
import "./styles.css";
// Hash routes work inside an unpacked extension without any server rewrite.
// Published /reports/:id are served by FastAPI and use ordinary web routes.
const router = location.pathname.startsWith("/reports/")
  ? createBrowserRouter(appRoutes)
  : createHashRouter(appRoutes);
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
