import { cp, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
if (!process.env.VERCEL) {
  try {
    process.loadEnvFile(path.join(root, "..", ".env"));
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
}
const apiBaseUrl = (
  process.env.API_BASE_URL ||
  (process.env.VERCEL ? "" : "http://127.0.0.1:8000")
).replace(/\/+$/, "");
if (!apiBaseUrl)
  throw new Error(
    "Vercel 환경 변수 API_BASE_URL에 Render 백엔드 주소를 설정하세요.",
  );
const parsed = new URL(apiBaseUrl);
if (
  !["http:", "https:"].includes(parsed.protocol) ||
  parsed.username ||
  parsed.password ||
  parsed.search ||
  parsed.hash ||
  parsed.pathname !== "/"
) {
  throw new Error(
    "API_BASE_URL은 경로/인증정보가 없는 http(s) 서버 주소여야 합니다.",
  );
}
if (process.env.VERCEL && parsed.protocol !== "https:")
  throw new Error("배포 API_BASE_URL은 HTTPS 주소여야 합니다.");
await mkdir(path.join(root, "dist"), { recursive: true });
for (const file of ["index.html", "styles.css", "app.js", "favicon.svg"]) {
  await cp(path.join(root, file), path.join(root, "dist", file));
}
await writeFile(
  path.join(root, "dist", "config.js"),
  `window.APP_CONFIG = ${JSON.stringify({ apiBaseUrl })};\n`,
);
console.log("정적 프론트엔드 빌드 완료: frontend/dist");
