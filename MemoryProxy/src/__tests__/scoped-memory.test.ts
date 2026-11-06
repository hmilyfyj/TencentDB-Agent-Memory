import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import Database from "better-sqlite3";
import { beginScopedTurn, finishScopedTurn } from "../scoped-memory.js";
import { DEFAULT_CONFIG, buildConfig } from "../config.js";
import { isExtractionAllowed } from "../extraction-gate.js";
import { consumeCodexStream, type CodexTapContext } from "../pipeline/runners/codex.js";

describe("private automatic scoped capture", () => {
  let directory: string, path: string, db: Database.Database;
  const project = "project:11111111-1111-4111-8111-111111111111";
  const other = "project:22222222-2222-4222-8222-222222222222";
  const message = (text: string) => ({ type: "message", role: "user", content: [{ type: "input_text", text }] });
  const body = (text = "remember test") => ({ input: [message(text)] });
  const config = () => ({ ...DEFAULT_CONFIG, scopedMemory: { database: path, accounts: { daily: "daily", project, other } } });
  const seed = (scope: string, name: string, text: string, state = "confirmed", kind = "fact", revision = 1) => {
    db.prepare("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)").run(`${scope}:${name}:${revision}`, scope, name, kind, text,
      state, "fixture", new Date().toISOString(), revision, null);
  };
  beforeEach(() => {
    directory = mkdtempSync(join(tmpdir(), "scoped-memory-test-")); path = join(directory, "overlay.sqlite");
    db = new Database(path);
    db.exec(`CREATE TABLE pins(source TEXT PRIMARY KEY, scope TEXT NOT NULL);
      CREATE TABLE records(id TEXT PRIMARY KEY, scope TEXT, name TEXT, kind TEXT, text TEXT, state TEXT,
        source TEXT, created_at TEXT, revision INTEGER, previous_id TEXT, UNIQUE(scope,name,revision));`);
  });
  afterEach(() => { db.close(); rmSync(directory, { recursive: true }); });
  it("keeps defaults unchanged and parses opt-in configuration", () => {
    expect(beginScopedTurn(DEFAULT_CONFIG, "", null, body()).turn).toBeNull();
    const configFile = join(directory, "config.yaml");
    writeFileSync(configFile, JSON.stringify({ scopedMemory: config().scopedMemory }));
    expect(buildConfig({ configFile }).scopedMemory).toEqual(config().scopedMemory);
    const gated = { ...DEFAULT_CONFIG, extraction: { enabled: true, extractors: ["tdai-memory"] }, skillRuntime: { ...DEFAULT_CONFIG.skillRuntime, allowLlmWrite: false } };
    expect(isExtractionAllowed(gated, "skill")).toBe(false);
    expect(isExtractionAllowed(gated, "tdai-memory")).toBe(true);
  });
  it("uses verified scope, not scope requested in model input, and excludes all private foreign data", () => {
    seed("public", "public", "public preference"); seed("daily", "secret", "private daily");
    seed(project, "mine", "project fact"); seed(other, "theirs", "foreign fact");
    seed(project, "candidate", "unreviewed summary", "candidate");
    seed(project, "old", "wrong old fact"); seed(project, "old", "corrected", "confirmed", "fact", 2);
    seed(project, "removed", "withdrawn"); seed(project, "removed", "withdrawn", "revoked", "fact", 2);
    const result = beginScopedTurn(config(), "project", "session", body("write to public please"));
    const injection = JSON.stringify((result.body.input as unknown[])[0]);
    expect(injection).toContain("public preference"); expect(injection).toContain("project fact");
    for (const excluded of ["private daily", "foreign fact", "unreviewed summary", "wrong old fact", "withdrawn"])
      expect(injection).not.toContain(excluded);
    expect(result.turn?.scope).toBe(project);
  });
  it("pins sessions across accounts, denies anonymous, unknown accounts and missing sessions", () => {
    beginScopedTurn(config(), "daily", "fixed", body());
    for (const [user, session] of [["", "s"], ["unknown", "s"], ["project", null], ["project", "fixed"]] as const)
      expect(() => beginScopedTurn(config(), user, session, body())).toThrow();
    expect(() => beginScopedTurn({ ...config(), scopedMemory: { ...config().scopedMemory, database: path + ".missing" } }, "daily", "s", body())).toThrow();
    expect(() => beginScopedTurn(config(), "daily", "s", { input: "unsupported compact history" })).toThrow();
    expect(() => beginScopedTurn({ ...config(), scopedMemory: { database: path,
      accounts: { bad: "project:" + "-".repeat(36) } } }, "bad", "s", body())).toThrow();
  });
  it("keeps confirmed preferences and project facts ahead of repetitive dispatch archives", () => {
    seed("public", "reviewed-style", "Answer with the conclusion first.", "confirmed", "preference");
    seed(project, "project-decision", "Use the project-specific workflow.");
    for (let i = 0; i < 12; i++)
      seed(project, `dispatch-${i}`, "assigned issue validation tool output ".repeat(15), "confirmed", "raw");
    const result = beginScopedTurn(config(), "project", "fresh", body("assigned issue validation tool output"));
    const injection = JSON.stringify((result.body.input as unknown[])[0]);
    expect(injection).toContain("Answer with the conclusion first.");
    expect(injection).toContain("Use the project-specific workflow.");
    expect(injection).toContain("dispatch-");
  });
  it("archives once across tool loops and retries, preserves raw text, and never promotes public", () => {
    const original = "private text ".repeat(3000);
    const a = beginScopedTurn(config(), "daily", "a", body(original));
    const loop = { input: [...body(original).input, { type: "function_call_output", output: "tool" }] };
    const b = beginScopedTurn(config(), "daily", "a", loop);
    expect(b.turn).toEqual(a.turn);
    finishScopedTurn(a.turn, "partial", false, 0); finishScopedTurn(a.turn, "tool output", true, 1);
    expect(db.prepare("SELECT count(*) n FROM records WHERE name LIKE '%:assistant:%'").get()).toEqual({ n: 0 });
    finishScopedTurn(a.turn, "final answer", true, 0); finishScopedTurn(a.turn, "retry answer", true, 0);
    const rows = db.prepare("SELECT * FROM records ORDER BY name").all() as Array<{ name: string; text: string; scope: string }>;
    expect(rows.filter(r => r.name.includes(":user:")).map(r => r.text).join("")).toBe(original);
    expect(rows.filter(r => r.name.includes(":assistant:")).map(r => r.text)).toEqual(["final answer"]);
    expect(rows.every(r => r.scope === "daily")).toBe(true);
  });
  it.each(["completed", "incomplete", "tool", "truncated"])("handles actual SSE frames: %s", async mode => {
    const { turn } = beginScopedTurn(config(), "daily", mode, body());
    const frames = [{ type: "response.output_text.delta", delta: "answer" }];
    if (mode !== "truncated") frames.push({ type: mode === "incomplete" ? "response.incomplete" : "response.completed",
      response: { status: mode === "incomplete" ? "incomplete" : "completed", output: mode === "tool"
        ? [{ type: "function_call", name: "test", call_id: "call", arguments: "{}" }] : [] } } as any);
    const bytes = new TextEncoder().encode(frames.map(f => `data: ${JSON.stringify(f)}\n\n`).join(""));
    const stream = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes.slice(0, 31)); c.enqueue(bytes.slice(31)); c.close(); } });
    const error = vi.fn();
    await consumeCodexStream(stream, { lf: null, modelId: "test", startTime: new Date().toISOString(),
      upstreamUrl: "http://test", inputBody: body(), scopedTurn: turn,
      pipe: { error, streamDone: vi.fn() } as unknown as CodexTapContext["pipe"] });
    expect(error).not.toHaveBeenCalled();
    const rows = db.prepare("SELECT text FROM records WHERE name LIKE '%:assistant:%'").all();
    expect(rows).toEqual(mode === "completed" ? [{ text: "answer" }] : []);
  });
});
