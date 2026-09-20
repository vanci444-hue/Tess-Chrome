import { copyFile, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
// 仅保留公开密钥，保证换目录或重建后扩展来源不变，不包含签名私钥。
const identity = JSON.parse(await readFile("extension-identity.json", "utf8"));
const id = [...createHash("sha256").update(Buffer.from(identity.key, "base64")).digest("hex").slice(0, 32)]
  .map((digit) => String.fromCharCode(97 + parseInt(digit, 16))).join("");
if (id !== identity.id) throw new Error("扩展公钥与 ID 不一致");
// The verified capture adapter is copied byte-for-byte; the spike remains untouched.
await copyFile("../extension/capture.js", "dist/capture.js");
await copyFile("../extension/service-worker.js", "dist/service-worker.js");
await writeFile(
  "dist/manifest.json",
  JSON.stringify(
    {
      manifest_version: 3,
      key: identity.key,
      name: "Tess · 销售工作空间",
      version: "0.2.0",
      minimum_chrome_version: "116",
      description: "真实 Model Y 配置采集与试驾复盘",
      icons: {
        "16": "icons/icon-16.png",
        "32": "icons/icon-32.png",
        "48": "icons/icon-48.png",
        "128": "icons/icon-128.png",
      },
      permissions: ["sidePanel", "storage", "scripting"],
      host_permissions: [
        "https://www.tesla.cn/modely/design*",
        "http://127.0.0.1/*",
        "http://localhost/*",
      ],
      background: { service_worker: "service-worker.js" },
      action: {
        default_title: "打开 Tess",
        default_icon: {
          "16": "icons/icon-16.png",
          "32": "icons/icon-32.png",
          "48": "icons/icon-48.png",
          "128": "icons/icon-128.png",
        },
      },
      side_panel: { default_path: "index.html" },
      content_security_policy: {
        extension_pages: "script-src 'self'; object-src 'none'",
      },
    },
    null,
    2,
  ),
);
