import { test } from "node:test";
import assert from "node:assert/strict";

import { answerAccepted, formatComment, parseComment, shapeThread, validate } from "../src/core.js";

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
