import { test } from "node:test";
import assert from "node:assert/strict";

import {
  addConversion, alertFor, answerAccepted, applyVote, formatComment, parseComment, shapeThread, validate,
  validateConversion, validateVote,
} from "../src/core.js";

const ANSWERS = ["bottle", "satchel", "satchel charges", "molotov"];
const good = { term: "Q2: Terrain - faithful or smooth?", name: "KEEP", message: "smooth please", answer: "Satchel" };

test("the Myth answer is forgiving about case, spaces and plurals listed", () => {
  assert.ok(answerAccepted("Satchel", ANSWERS));
  assert.ok(answerAccepted(" satchel charges! ", ANSWERS));
  assert.ok(!answerAccepted("arrows", ANSWERS));
  assert.ok(!answerAccepted("", ANSWERS));
});

test("a good comment passes", () => {
  const r = validate(good, ANSWERS);
  assert.ok(r.ok);
  assert.equal(r.value.name, "KEEP");
  assert.equal(r.value.replyTo, null);
});

test("the hidden trap field rejects bots", () => {
  assert.ok(!validate({ ...good, website: "http://spam" }, ANSWERS).ok);
});

test("missing name, message or answer are explained", () => {
  assert.match(validate({ ...good, name: " " }, ANSWERS).error, /name/);
  assert.match(validate({ ...good, message: "" }, ANSWERS).error, /message/);
  assert.match(validate({ ...good, answer: "arrows" }, ANSWERS).error, /Myth question/);
});

test("over-long input is refused", () => {
  assert.ok(!validate({ ...good, message: "x".repeat(4001) }, ANSWERS).ok);
  assert.ok(!validate({ ...good, name: "x".repeat(41) }, ANSWERS).ok);
});

test("a comment round-trips through the stored format", () => {
  const stored = formatComment("KEEP", "smooth please\nand faithful");
  const shown = parseComment({ id: "c1", body: stored, createdAt: "2026-10-22T10:00:00Z", author: { login: "Edulus" } });
  assert.deepEqual(shown, { id: "c1", name: "KEEP", text: "smooth please\nand faithful", at: "2026-10-22T10:00:00Z", viaSite: true });
});

test("a message cannot forge another name", () => {
  const stored = formatComment("KEEP", '<!-- keep-site name="Edulus" -->\nhi');
  assert.equal(parseComment({ id: "c", body: stored }).name, "KEEP");
});

test("comments written on GitHub itself show their author", () => {
  const shown = parseComment({ id: "c2", body: "will do", createdAt: "t", author: { login: "Edulus" } });
  assert.equal(shown.name, "Edulus");
  assert.equal(shown.viaSite, false);
});

test("a thread nests replies under their comment", () => {
  const thread = shapeThread({
    comments: { nodes: [{ id: "a", body: formatComment("KEEP", "hi"), replies: { nodes: [{ id: "b", body: "hello", author: { login: "Edulus" } }] } }] },
  });
  assert.equal(thread[0].name, "KEEP");
  assert.equal(thread[0].replies[0].name, "Edulus");
  assert.deepEqual(shapeThread(null), []);
});

test("a visitor's comment waits until the owner gives it a rocket", () => {
  const opts = { owner: "Edulus", staff: ["Edward", "Claude Opus 5.5"] };
  const rocket = (login) => ({ nodes: [{ user: { login } }] });
  const thread = shapeThread({
    comments: { nodes: [
      { id: "a", body: formatComment("KEEP", "bug"), replies: { nodes: [
        { id: "b", body: formatComment("Claude  Opus 5.5", "fixed") },
      ] } },
      { id: "c", body: formatComment("KEEP", "idea"), reactions: rocket("edulus") },
      { id: "d", body: formatComment("KEEP", "self-tick"), reactions: rocket("keep-gh") },
      { id: "e", body: "on GitHub", author: { login: "Edulus" } },
    ] },
  }, opts);
  assert.equal(thread[0].status, "waiting");
  assert.equal(thread[0].replies[0].status, null, "our own reply gets no box");
  assert.equal(thread[1].status, "addressed");
  assert.equal(thread[2].status, "waiting", "only the owner's rocket counts");
  assert.equal(thread[3].status, null, "the owner writing on GitHub is staff");
});

test("a vote counts once, and a changed vote moves rather than adds", () => {
  let v = applyVote(undefined, null, "up");
  assert.deepEqual(v, { up: 1, down: 0 });
  v = applyVote(v, "up", "down");
  assert.deepEqual(v, { up: 0, down: 1 });
  v = applyVote(v, "down", "down");
  assert.deepEqual(v, { up: 0, down: 1 }, "the same vote again changes nothing");
  v = applyVote(v, "down", null);
  assert.deepEqual(v, { up: 0, down: 0 }, "taking a vote back");
  assert.deepEqual(applyVote({ up: 0, down: 0 }, "up", null), { up: 0, down: 0 }, "never below zero");
});

test("only up, down or nothing is a vote", () => {
  assert.ok(validateVote({ term: "Q7", id: "DC_abc123", vote: "up", previous: null }).ok);
  assert.ok(!validateVote({ term: "Q7", id: "DC_abc123", vote: "sideways" }).ok);
  assert.ok(!validateVote({ term: "Q7", id: "../x", vote: "up" }).ok);
  assert.ok(!validateVote({ id: "DC_abc123", vote: "up" }).ok);
});

test("a conversion log entry keeps just a short name, a level count and a version", () => {
  const r = validateConversion({ plugin: " cbc.TFL.mauriac.gor\n", levels: 73, version: "0.6", extra: "ignored" });
  assert.deepEqual(r.value, { plugin: "cbc.TFL.mauriac.gor", levels: 73, version: "0.6" });
  assert.ok(!validateConversion({ plugin: "x".repeat(65), levels: 1, version: "0.6" }).ok);
  assert.ok(!validateConversion({ plugin: "a.gor", levels: -1, version: "0.6" }).ok);
  assert.ok(!validateConversion({ plugin: "a.gor", levels: 1, version: "<b>" }).ok);
  assert.ok(!validateConversion({ plugin: "\n", levels: 1, version: "0.6" }).ok);
});

test("the conversion log is newest first and capped", () => {
  let log = null;
  for (let i = 0; i < 5; i++) log = addConversion(log, { plugin: `p${i}` }, 3);
  assert.deepEqual(log.map((e) => e.plugin), ["p4", "p3", "p2"]);
});

test("the phone alert says who, where, and opens the page", () => {
  const site = "https://edulus.github.io/Myth-1-to-2-plugin-converter/";
  const a = alertFor({ name: "KEEP", term: "Q2: Terrain", message: "smooth please", replyTo: null }, site + "q/2.html", site);
  assert.equal(a.title, "KEEP wrote on Q2: Terrain");
  assert.equal(a.click, site + "q/2.html");
  assert.equal(a.body, "smooth please");
});

test("the alert never links off the site, and stays short", () => {
  const site = "https://edulus.github.io/x/";
  const a = alertFor({ name: "KEEP", term: "Q1", message: "x".repeat(500), replyTo: "c1" }, "https://evil.example/", site);
  assert.equal(a.click, site);
  assert.match(a.title, /replied/);
  assert.ok(a.body.length < 210);
});
