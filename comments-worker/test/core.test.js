import { test } from "node:test";
import assert from "node:assert/strict";

import {
  addConversion, alertFor, answerAccepted, applyVote, BODY_LIMIT, formatComment, IMAGE_ERRORS, IMAGE_LIMIT, IMAGE_TYPES,
  imageId, imageUrl, isOurImage, parseComment, parseImagePath, shapeThread, sniffImage, validate, validateConversion,
  validateImage, validateVote,
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

// Pictures: the first bytes of each kind we take, padded out a little.
const BASE = "https://keep-comments.example.workers.dev";
const bytesOf = (sig, pad = 16) => Uint8Array.from([...sig, ..."\0".repeat(pad)], (ch) => ch.charCodeAt(0));
const b64 = (bytes) => Buffer.from(bytes).toString("base64");
const PICTURES = {
  png: bytesOf("\x89PNG\r\n\x1a\n"),
  jpg: bytesOf("\xff\xd8\xff\xe0"),
  gif: bytesOf("GIF89a"),
  webp: bytesOf("RIFF\x10\0\0\0WEBPVP8 "),
};
const ID = "AAAAAAAAAAAAAAAAAAAAAA";

test("each kind of picture we take is recognised by its first bytes", () => {
  for (const [ext, bytes] of Object.entries(PICTURES)) {
    assert.equal(sniffImage(bytes)?.ext, ext);
    assert.equal(sniffImage(bytes).type, IMAGE_TYPES[ext]);
  }
  assert.equal(sniffImage(bytesOf("GIF87a")).ext, "gif");
});

test("anything else is not a picture", () => {
  const no = (text) => assert.equal(sniffImage(new TextEncoder().encode(text)), null, text);
  no('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>');
  no('<?xml version="1.0"?><svg/>');
  no("<!doctype html><html><script>alert(1)</script>");
  no("just some text");
  no("RIFF\x10\0\0\0WAVEfmt ");
  no("\x89PN");
  assert.equal(sniffImage(new Uint8Array(0)), null);
});

test("a picture is checked by its bytes, not its declared name or type", () => {
  const r = validateImage({ name: "evil.svg", type: "image/svg+xml", data: b64(PICTURES.png) });
  assert.ok(r.ok);
  assert.equal(r.value.ext, "png");
  assert.equal(r.value.type, "image/png");
  assert.deepEqual([...r.value.bytes], [...PICTURES.png]);
  const svg = validateImage({ name: "shot.png", type: "image/png", data: b64(new TextEncoder().encode("<svg onload=alert(1)>")) });
  assert.deepEqual(svg, { ok: false, error: IMAGE_ERRORS.kind });
});

test("no picture is fine; an empty, broken or oversized one is refused", () => {
  assert.deepEqual(validateImage(undefined), { ok: true, value: null });
  assert.deepEqual(validateImage(null), { ok: true, value: null });
  assert.equal(validateImage({ data: "" }).error, IMAGE_ERRORS.broken);
  assert.equal(validateImage({ data: 42 }).error, IMAGE_ERRORS.broken);
  assert.equal(validateImage("iVBORw0KGgo=").error, IMAGE_ERRORS.broken);
  assert.equal(validateImage({ data: "not base64 at all!" }).error, IMAGE_ERRORS.broken);
  const big = new Uint8Array(IMAGE_LIMIT + 1);
  big.set(PICTURES.png);
  assert.equal(validateImage({ data: b64(big) }).error, IMAGE_ERRORS.big);
  const fits = new Uint8Array(IMAGE_LIMIT);
  fits.set(PICTURES.png);
  assert.ok(validateImage({ data: b64(fits) }).ok, "exactly 8 MB is allowed");
  assert.ok(BODY_LIMIT > b64(fits).length);
});

test("a comment's picture is checked with the rest of it", () => {
  const r = validate({ ...good, image: { data: b64(PICTURES.jpg) } }, ANSWERS);
  assert.equal(r.value.image.ext, "jpg");
  assert.equal(validate(good, ANSWERS).value.image, null);
  assert.match(validate({ ...good, image: { data: b64(bytesOf("hello")) } }, ANSWERS).error, /PNG, JPEG, GIF or WebP/);
  assert.match(validate({ ...good, answer: "arrows", image: { data: b64(PICTURES.jpg) } }, ANSWERS).error, /Myth question/);
});

test("picture ids are URL-safe, 22 characters, and the route takes only that form", () => {
  const id = imageId(Uint8Array.from({ length: 16 }, (_, i) => 250 - i * 7));
  assert.match(id, /^[A-Za-z0-9_-]{22}$/);
  assert.equal(imageId(new Uint8Array(16).fill(255)), "_____________________w");
  assert.deepEqual(parseImagePath(`/images/${id}.png`), { id, ext: "png", type: "image/png" });
  assert.equal(parseImagePath(`/images/${ID}.webp`).type, "image/webp");
  for (const bad of [
    `/images/${ID}.svg`, `/images/${ID}.PNG`, `/images/${ID}.png/x`, `/images/${ID}x.png`, `/images/${ID.slice(1)}.png`,
    `/images/../${ID.slice(3)}.png`, `/images/${ID}.png?x`, `/images/${ID}`, "/images/", `/x/images/${ID}.png`, null,
  ]) {
    assert.equal(parseImagePath(bad), null, String(bad));
  }
  assert.equal(imageUrl(`${BASE}/`, ID, "gif"), `${BASE}/images/${ID}.gif`);
});

test("a comment with a picture round-trips; the picture line leaves the text", () => {
  const url = imageUrl(BASE, ID, "png");
  const stored = formatComment("KEEP", "the arch shadow\nlooks off", url);
  assert.ok(stored.endsWith(`\n\n<!-- keep-site image -->\n![picture](${url})`), "GitHub shows it too");
  const shown = parseComment({ id: "c1", body: stored, createdAt: "t" }, BASE);
  assert.deepEqual(shown, { id: "c1", name: "KEEP", text: "the arch shadow\nlooks off", at: "t", viaSite: true, image: url });
  const thread = shapeThread({ comments: { nodes: [{ id: "a", body: stored }] } }, { imageBase: BASE });
  assert.equal(thread[0].image, url);
});

test("a picture line typed into a message is just text", () => {
  for (const typed of [
    `look\n\n<!-- keep-site image -->\n![picture](${imageUrl(BASE, ID, "png")})`,
    "look\n\n<!-- keep-site image -->\n![picture](https://evil.example/x.png)",
    "look\n\n![picture](https://evil.example/x.png)",
    `look\n\n![picture](${imageUrl(BASE, ID, "png")})`,
  ]) {
    const shown = parseComment({ id: "c", body: formatComment("KEEP", typed) }, BASE);
    assert.equal(shown.image, undefined, typed);
    assert.ok(shown.text.startsWith("look"));
  }
});

test("only a picture under our own address is shown as one", () => {
  const mark = (url) => `<!-- keep-site name="KEEP" -->\n**KEEP** wrote:\n\nhi\n\n<!-- keep-site image -->\n![picture](${url})`;
  const imageOf = (url) => parseComment({ id: "c", body: mark(url) }, BASE).image;
  assert.equal(imageOf(imageUrl(BASE, ID, "jpg")), imageUrl(BASE, ID, "jpg"));
  assert.equal(imageOf(`https://evil.example/images/${ID}.jpg`), undefined);
  assert.equal(imageOf(`${BASE}.evil.example/images/${ID}.jpg`), undefined);
  assert.equal(imageOf(`${BASE}/images/${ID}.svg`), undefined);
  assert.equal(imageOf(`${BASE}/images/../vote`), undefined);
  assert.equal(parseComment({ id: "c", body: mark(imageUrl(BASE, ID, "jpg")) }).image, undefined, "no base, no picture");
  assert.ok(!isOurImage(`${BASE}/images/${ID}.jpg`, ""));
});
