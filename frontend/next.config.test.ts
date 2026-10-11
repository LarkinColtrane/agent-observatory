// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

type Header = { key: string; value: string };

async function loadConfig(nodeEnv: string) {
  vi.resetModules();
  vi.stubEnv("NODE_ENV", nodeEnv);
  const { default: config } = await import("./next.config");
  const rules = await config.headers!();
  expect(rules).toHaveLength(1);
  const rule = rules[0]!;
  expect(rule.source).toBe("/:path*");
  const byKey = new Map(
    (rule.headers as Header[]).map((h) => [h.key.toLowerCase(), h.value]),
  );
  return { config, byKey };
}

function cspDirectives(csp: string): Map<string, string[]> {
  return new Map(
    csp
      .split(";")
      .map((d) => d.trim().split(/\s+/))
      .filter((parts) => parts[0])
      .map(([name, ...values]) => [name!, values]),
  );
}

describe("next.config security headers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it.each(["production", "test", "development"])(
    "sets the baseline security headers when NODE_ENV=%s",
    async (nodeEnv) => {
      const { config, byKey } = await loadConfig(nodeEnv);

      expect(config.poweredByHeader).toBe(false);
      expect(byKey.get("x-content-type-options")).toBe("nosniff");
      expect(byKey.get("x-frame-options")).toBe("DENY");
      expect(byKey.get("referrer-policy")).toBe(
        "strict-origin-when-cross-origin",
      );

      const csp = cspDirectives(byKey.get("content-security-policy") ?? "");
      expect(csp.get("default-src")).toEqual(["'self'"]);
      expect(csp.get("frame-ancestors")).toEqual(["'none'"]);
      expect(csp.get("object-src")).toEqual(["'none'"]);
    },
  );

  it.each(["production", "test"])(
    "has no 'unsafe-eval' or websocket sources when NODE_ENV=%s",
    async (nodeEnv) => {
      const { byKey } = await loadConfig(nodeEnv);
      const raw = byKey.get("content-security-policy") ?? "";
      const csp = cspDirectives(raw);

      expect(raw).not.toContain("'unsafe-eval'");
      expect(csp.get("script-src")).toEqual(["'self'", "'unsafe-inline'"]);
      expect(csp.get("connect-src")).toEqual(["'self'"]);
    },
  );

  it("relaxes script-src and connect-src only for NODE_ENV=development", async () => {
    const { byKey } = await loadConfig("development");
    const csp = cspDirectives(byKey.get("content-security-policy") ?? "");

    expect(csp.get("script-src")).toContain("'unsafe-eval'");
    expect(csp.get("connect-src")).toEqual(["'self'", "ws:", "wss:"]);
  });
});
