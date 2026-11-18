import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

import worker from "../src/index.js";
import { isStaffName, staffKeyMatches } from "../src/core.js";

// The worker's POST /comments, run against a fake GitHub (globalThis.fetch)
// and fake bindings, so no request leaves the machine.
const KEY = "correct horse battery staple";
const STAFF = "Edward,Edulus,Claude,Claude Code,Claude Opus 5.5,Claude Fable 5.2";
const RESERVED = "That name is reserved for the project. Please choose another name.";

let calls;
let realFetch;

beforeEach(() => {
  calls = [];
  realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    const { query } = JSON.parse(init.body);
    let data;
    if (query.includes("addDiscussionComment")) data = { addDiscussionComment: { comment: { id: "DC_new" } } };
    else if (query.includes("discussions(")) data = { repository: { discussions: { nodes: [{ id: "D_1", title: "Q1" }] } } };
    else data = { node: { id: "D_1", comments: { nodes: [] } } };
    return new Response(JSON.stringify({ data }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function makeEnv(overrides = {}) {
  const puts = [];
  return {
    puts,
    REPO: "Edulus/repo",
    REPO_ID: "R_1",
    CATEGORY_ID: "DIC_1",
    SITE_URL: "https://edulus.github.io/repo/",
    ALLOWED_ORIGINS: "https://edulus.github.io",
    IMAGE_BASE: "https://worker.example",
    STAFF_NAMES: STAFF,
    ANSWERS: "satchel,bottle",
    GITHUB_TOKEN: "test-token",
    STAFF_KEY: KEY,
    POST_LIMIT: { limit: async () => ({ success: true }) },
    VOTES: {
      get: async () => null,
      put: async (...args) => puts.push(args),
      delete: async () => {},
    },
    ...overrides,
  };
}

const ctx = { waitUntil() {} };
const PNG = Buffer.from("\x89PNG\r\n\x1a\n" + "\0".repeat(16), "latin1").toString("base64");

function post(body, headers = {}) {
  return new Request("https://worker.example/comments", {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: "https://edulus.github.io", ...headers },
    body: JSON.stringify({ term: "Q1", page: "", message: "hello", answer: "Satchel", website: "", ...body }),
  });
}

const githubCalls = () => calls.filter((c) => c.url.startsWith("https://api.github.com/"));
const posted = () => githubCalls().some((c) => JSON.parse(c.init.body).query.includes("addDiscussionComment"));

test("a staff name without the key is refused before GitHub or storage is touched", async () => {
  const env = makeEnv();
  const res = await worker.fetch(post({ name: "Edward", image: { data: PNG } }), env, ctx);
  assert.equal(res.status, 403);
  assert.deepEqual(await res.json(), { error: RESERVED });
  assert.equal(githubCalls().length, 0, "no GitHub call");
  assert.equal(env.puts.length, 0, "the picture is not stored");
});

test("a staff name with the wrong key is refused", async () => {
  // (Header values are trimmed by the Fetch Headers API, so KEY + " " is KEY.)
  for (const wrong of ["wrong", KEY.slice(0, -1), KEY + "x", "x" + KEY, KEY.toUpperCase(), ""]) {
    calls = [];
    const res = await worker.fetch(post({ name: "Claude Opus 5.5" }, { "X-Staff-Key": wrong }), makeEnv(), ctx);
    assert.equal(res.status, 403, JSON.stringify(wrong));
    assert.equal(githubCalls().length, 0);
  }
});

test("a staff name with the right key is posted", async () => {
  const res = await worker.fetch(post({ name: "Claude Opus 5.5" }, { "X-Staff-Key": KEY }), makeEnv(), ctx);
  assert.equal(res.status, 200);
  assert.ok(posted(), "the comment went to GitHub");
  const sent = githubCalls().find((c) => JSON.parse(c.init.body).query.includes("addDiscussionComment"));
  assert.ok(!JSON.stringify(sent.init).includes(KEY), "the key is not passed on to GitHub");
});

test("with no STAFF_KEY set, staff names are refused for everyone", async () => {
  for (const env of [makeEnv({ STAFF_KEY: undefined }), makeEnv({ STAFF_KEY: "" })]) {
    for (const header of [undefined, "", KEY, "undefined"]) {
      calls = [];
      const headers = header === undefined ? {} : { "X-Staff-Key": header };
      const res = await worker.fetch(post({ name: "Edward" }, headers), env, ctx);
      assert.equal(res.status, 403, `STAFF_KEY=${JSON.stringify(env.STAFF_KEY)} header=${JSON.stringify(header)}`);
      assert.equal(githubCalls().length, 0);
    }
  }
});

test("a visitor's name needs no key, with or without STAFF_KEY set", async () => {
  for (const env of [makeEnv(), makeEnv({ STAFF_KEY: undefined })]) {
    // Digits are ignored, so "Claude Opus 5.6" would be staff; these differ in letters.
    for (const name of ["KEEP", "Edwardo", "Claude Sonnet", "Mr Edward", "Claud"]) {
      calls = [];
      const res = await worker.fetch(post({ name }), env, ctx);
      assert.equal(res.status, 200, name);
      assert.ok(posted(), name);
    }
  }
});

test("staff names are matched on letters only, as isStaff shows them", async () => {
  for (const name of ["claude opus 5.5", "CLAUDE  OPUS", "Claude-Opus-5.5!", "claude.code", " e d w a r d ", "Claude Opus 4"]) {
    calls = [];
    const res = await worker.fetch(post({ name }), makeEnv(), ctx);
    assert.equal(res.status, 403, name);
    assert.equal(githubCalls().length, 0, name);
  }
  assert.ok(isStaffName("claude opus 5.5", STAFF.split(",")));
  assert.ok(!isStaffName("Edwardo", STAFF.split(",")));
  assert.ok(!isStaffName("5.5", ["Edward", ""]), "a name with no letters never matches, even a stray empty entry");
});

test("the existing checks still come first", async () => {
  // Honeypot and a wrong Myth answer are refused with 400, staff name or not.
  let res = await worker.fetch(post({ name: "Edward", website: "http://spam" }), makeEnv(), ctx);
  assert.equal(res.status, 400);
  res = await worker.fetch(post({ name: "Edward", answer: "arrows" }), makeEnv(), ctx);
  assert.equal(res.status, 400);
  // The rate limit is checked before the body is read.
  res = await worker.fetch(post({ name: "Edward" }), makeEnv({ POST_LIMIT: { limit: async () => ({ success: false }) } }), ctx);
  assert.equal(res.status, 429);
  assert.equal(githubCalls().length, 0);
});

test("the preflight allows the X-Staff-Key header", async () => {
  const res = await worker.fetch(new Request("https://worker.example/comments", {
    method: "OPTIONS",
    headers: { Origin: "https://edulus.github.io", "Access-Control-Request-Headers": "content-type, x-staff-key" },
  }), makeEnv(), ctx);
  assert.equal(res.status, 204);
  const allowed = res.headers.get("Access-Control-Allow-Headers").toLowerCase().split(",").map((s) => s.trim());
  assert.ok(allowed.includes("x-staff-key"));
  assert.ok(allowed.includes("content-type"));
});

test("the key comparison", async () => {
  assert.equal(await staffKeyMatches(KEY, KEY), true);
  assert.equal(await staffKeyMatches("x", KEY), false);
  assert.equal(await staffKeyMatches(null, KEY), false);
  assert.equal(await staffKeyMatches("", ""), false);
  assert.equal(await staffKeyMatches(undefined, undefined), false);
  assert.equal(await staffKeyMatches(KEY, undefined), false);
});
