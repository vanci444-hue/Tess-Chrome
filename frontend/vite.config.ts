import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_BACKEND_PROXY_TARGET || "http://127.0.0.1:8099";
  return {
    base: "/",
    plugins: [react()],
    define: {
      "import.meta.env.VITE_EXTENSION_API_ORIGIN": JSON.stringify(
        env.VITE_EXTENSION_API_ORIGIN || target,
      ),
    },
    server: {
      port: 5199,
      strictPort: true,
      proxy: {
        "/api": { target, changeOrigin: false },
        "/ws": {
          target: target.replace(/^http/, "ws"),
          ws: true,
          changeOrigin: false,
        },
      },
    },
  };
});
