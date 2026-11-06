import { describe, expect, it, vi } from "vitest";
import { Hono } from "hono";
import { DEFAULT_CONFIG } from "../config.js";
import { createSkillBridgeHandler } from "../skill/skill-bridge.js";
import { stageArchive } from "../pipeline/stages/archive.js";
import { triggerSkillExtractIfReady } from "../skill/handler-glue.js";

vi.mock("../skill/handler-glue.js", () => ({ triggerSkillExtractIfReady: vi.fn() }));
vi.mock("../bridge-auth.js", () => ({ authorizeBridgeSession: async () => null }));
vi.mock("../tdai/team-memory-switch.js", () => ({ fetchTeamMemoryEnabled: async () => true }));
vi.mock("../session/store.js", () => ({ getSessionStore: () => ({ getBindingRepo: () => null,
  get: () => ({ status: "initialized", sessionInfo: { user_id: "owner", team_id: "team", agent_id: "agent" } }),
}) }));

describe("Skill write opt-out covers manual extraction", () => {
  it.each(["extract", "create", "update", "patch", "delete", "files/write", "files/remove"])("rejects %s before forwarding", async sub => {
    const fetcher = vi.fn();
    const app = new Hono();
    app.post("/skill-bridge/*", createSkillBridgeHandler({ ...DEFAULT_CONFIG,
      skillRuntime: { ...DEFAULT_CONFIG.skillRuntime, allowLlmWrite: false },
    }, { fetcher }));
    const response = await app.request("/skill-bridge/v3/skill/" + sub, { method: "POST",
      headers: { "content-type": "application/json", "x-conversation-id": "fixture" }, body: "{}" });
    expect(response.status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([false, true])("automatic extraction respects explicit whitelist: %s", async allowed => {
    vi.mocked(triggerSkillExtractIfReady).mockClear();
    await stageArchive({ config: { ...DEFAULT_CONFIG,
      extraction: { enabled: true, extractors: allowed ? ["skill"] : ["tdai-memory"] } },
      sessionKey: "fixture", agentSource: "codex", inputMessages: [],
      assistant: { text: "final", raw: { role: "assistant", content: "final" } },
      protocol: "responses", isAuxiliary: false, dshHeadless: false });
    expect(triggerSkillExtractIfReady).toHaveBeenCalledTimes(allowed ? 1 : 0);
  });
});
