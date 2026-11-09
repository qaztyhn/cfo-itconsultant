import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { resolveAppEnv, resolvePosUrl } from "./config";

describe("resolveAppEnv", () => {
  it.each([
    // [VITE_APP_ENV, isProd, kết quả]
    [undefined, true, "production"], // lỗi P1: build production quên đặt biến
    ["", true, "production"],
    ["production", true, "production"],
    ["prod", true, "production"], // gõ sai → vẫn an toàn
    ["demo", true, "demo"], // bật demo tường minh
    [" Staging ", true, "staging"],
    [undefined, false, "demo"], // dev/test giữ mặc định demo
    ["production", false, "production"],
  ])("VITE_APP_ENV=%j, isProd=%s → %s", (raw, isProd, expected) => {
    expect(resolveAppEnv(raw, isProd)).toBe(expected);
  });
});

/** Script chạy trong tiến trình Node riêng (không có jsdom): build config.ts ở production mode, in mã đầu ra ra stdout. */
const BUILD_SCRIPT = `
import { build } from "vite";
const result = await build({
  configFile: false,
  mode: "production",
  envDir: process.env.CFG_ENV_DIR,
  logLevel: "silent",
  build: {
    write: false,
    minify: false,
    lib: { entry: process.env.CFG_ENTRY, formats: ["cjs"], fileName: "config" },
  },
});
const out = Array.isArray(result) ? result[0] : result;
const chunk = out.output.find((o) => o.type === "chunk");
process.stdout.write(JSON.stringify(chunk.code));
`;

/** Build riêng config.ts như `vite build` thật, rồi chạy kết quả để đọc giá trị APP_ENV thật. */
function loadBuiltConfig(appEnv?: string) {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    NODE_ENV: "production",
    CFG_ENTRY: resolve(__dirname, "config.ts"),
    CFG_ENV_DIR: mkdtempSync(join(tmpdir(), "vite-env-")), // thư mục rỗng: không đọc .env trên máy dev
  };
  delete env.VITE_APP_ENV;
  if (appEnv !== undefined) env.VITE_APP_ENV = appEnv;

  const stdout = execFileSync(process.execPath, ["--input-type=module", "-e", BUILD_SCRIPT], {
    cwd: resolve(__dirname, "../.."), // thư mục frontend, để resolve được "vite" trong node_modules
    env,
    encoding: "utf8",
  });

  const exports: Record<string, unknown> = {};
  new Function("exports", JSON.parse(stdout) as string)(exports);
  return exports as { APP_ENV: string; isDemoEnv: (env?: string) => boolean };
}

describe("APP_ENV trong bản build production thực tế", () => {
  it("không đặt VITE_APP_ENV → production, không hiện demo", () => {
    const cfg = loadBuiltConfig(undefined);
    expect(cfg.APP_ENV).toBe("production");
    expect(cfg.isDemoEnv()).toBe(false);
  }, 30_000);

  it("giá trị gõ sai (prod) → vẫn production", () => {
    const cfg = loadBuiltConfig("prod");
    expect(cfg.APP_ENV).toBe("production");
    expect(cfg.isDemoEnv()).toBe(false);
  }, 30_000);

  it("VITE_APP_ENV=demo → bật demo tường minh", () => {
    const cfg = loadBuiltConfig("demo");
    expect(cfg.APP_ENV).toBe("demo");
    expect(cfg.isDemoEnv()).toBe(true);
  }, 30_000);
});
describe("POS configuration is safe for cloud deployment", () => {
  it("does not use an implicit localhost URL", () => {
    expect(resolvePosUrl(undefined, true)).toBeNull();
    expect(resolvePosUrl("", true)).toBeNull();
    expect(resolvePosUrl("   ", false)).toBeNull();
  });

  it("rejects localhost and insecure schemes in production", () => {
    expect(resolvePosUrl("http://localhost:8100", true)).toBeNull();
    expect(resolvePosUrl("https://localhost:8100", true)).toBeNull();
    expect(resolvePosUrl("http://127.0.0.1:8100", true)).toBeNull();
    expect(resolvePosUrl("https://pos.example.test", true)).toBe("https://pos.example.test");
    expect(resolvePosUrl("javascript:alert(1)", true)).toBeNull();
    expect(resolvePosUrl("https://user:password@pos.example.test", true)).toBeNull();
  });

  it("allows a deliberately configured HTTP local POS UI only during development", () => {
    expect(resolvePosUrl("http://localhost:9000/", false)).toBe("http://localhost:9000");
    expect(resolvePosUrl(" https://pos.example.test/orders/ ", false)).toBe("https://pos.example.test/orders");
  });
});
