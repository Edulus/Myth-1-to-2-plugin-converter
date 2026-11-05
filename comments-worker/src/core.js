// Pure logic for KEEP's comment box: validation, and the comment format
// stored in GitHub Discussions. No I/O here, so it can be tested in Node.

export const LIMITS = { name: 40, message: 4000 };

// Marks a comment posted through the site, carrying the name typed there.
// GitHub hides HTML comments when it renders Markdown.
const MARKER = /^<!-- keep-site name="([^"]*)" -->\n/;

export function normalizeAnswer(text) {
  return String(text ?? "").toLowerCase().replace(/[^a-z]/g, "");
}

export function answerAccepted(text, accepted) {
  const given = normalizeAnswer(text);
  return given !== "" && accepted.map(normalizeAnswer).includes(given);
}

// Returns { ok: true, value } or { ok: false, error } -- the error is shown
// to the person typing, so it is written for them.
export function validate(input, accepted) {
  const body = input && typeof input === "object" ? input : {};
  if (body.website) {
    // The hidden trap field: people never see it, bots fill it in.
    return { ok: false, error: "Sorry, that didn't go through." };
  }
  const term = String(body.term ?? "").trim();
  const name = String(body.name ?? "").trim();
  const message = String(body.message ?? "").replace(/\r\n/g, "\n").trim();
  const replyTo = body.replyTo ? String(body.replyTo) : null;
  if (!term || term.length > 200) return { ok: false, error: "This page is missing its topic." };
  if (!name) return { ok: false, error: "Please type your name." };
  if (name.length > LIMITS.name) return { ok: false, error: `Please keep your name under ${LIMITS.name} characters.` };
  if (!message) return { ok: false, error: "Please type a message." };
  if (message.length > LIMITS.message) {
    return { ok: false, error: `That's a long one -- please keep it under ${LIMITS.message} characters, or split it in two.` };
  }
  if (!answerAccepted(body.answer, accepted)) {
    return { ok: false, error: "That answer to the Myth question doesn't look right -- try again." };
  }
  if (replyTo && !/^[A-Za-z0-9_=-]{4,100}$/.test(replyTo)) return { ok: false, error: "That reply link is broken." };
  const image = validateImage(body.image);
  if (!image.ok) return image;
  return { ok: true, value: { term, name, message, replyTo, image: image.value } };
}

// A picture sent with a comment. Its bytes are kept in the VOTES KV store
// under "img:<id>" and served from GET /images/<id>.<ext>. What it is comes
// from its first bytes, never from its name or the type the browser declared,
// and only these four kinds are taken (no SVG: it can carry script).
export const IMAGE_LIMIT = 8 * 1024 * 1024;
export const IMAGE_TYPES = { png: "image/png", jpg: "image/jpeg", gif: "image/gif", webp: "image/webp" };
const BASE64_LIMIT = Math.ceil(IMAGE_LIMIT / 3) * 4;
// A whole POST /comments body: the picture as base64 plus room for the rest.
export const BODY_LIMIT = BASE64_LIMIT + 64 * 1024;

export const IMAGE_ERRORS = {
  big: "That picture is too big -- please keep it under 8 MB.",
  kind: "That picture can't be used -- please send a PNG, JPEG, GIF or WebP.",
  broken: "That picture didn't come through -- please choose it again.",
};

export function sniffImage(bytes) {
  const has = (sig, at = 0) => [...sig].every((ch, i) => bytes[at + i] === ch.charCodeAt(0));
  if (has("\x89PNG\r\n\x1a\n")) return { ext: "png", type: IMAGE_TYPES.png };
  if (has("\xff\xd8\xff")) return { ext: "jpg", type: IMAGE_TYPES.jpg };
  if (has("GIF87a") || has("GIF89a")) return { ext: "gif", type: IMAGE_TYPES.gif };
  if (has("RIFF") && has("WEBP", 8)) return { ext: "webp", type: IMAGE_TYPES.webp };
  return null;
}

export function decodeBase64(text) {
  if (typeof Uint8Array.fromBase64 === "function") return Uint8Array.fromBase64(text);
  const raw = atob(text);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

// { ok: true, value: null } when no picture was sent.
export function validateImage(input) {
  if (input === undefined || input === null) return { ok: true, value: null };
  const data = typeof input === "object" ? input.data : null;
  if (typeof data !== "string" || !data) return { ok: false, error: IMAGE_ERRORS.broken };
  // Measured before decoding, so an oversized one costs no work.
  if (data.length > BASE64_LIMIT) return { ok: false, error: IMAGE_ERRORS.big };
  let bytes;
  try {
    bytes = decodeBase64(data);
  } catch {
    return { ok: false, error: IMAGE_ERRORS.broken };
  }
  if (bytes.length > IMAGE_LIMIT) return { ok: false, error: IMAGE_ERRORS.big };
  const kind = sniffImage(bytes);
  if (!kind) return { ok: false, error: IMAGE_ERRORS.kind };
  return { ok: true, value: { bytes, ...kind } };
}

// 16 random bytes, URL-safe base64 without padding: 22 characters.
export function imageId(bytes) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const IMAGE_PATH = /^\/images\/([A-Za-z0-9_-]{22})\.(png|jpg|gif|webp)$/;

// "/images/<id>.<ext>" -> { id, ext, type }, or null for anything else.
export function parseImagePath(path) {
  const match = typeof path === "string" ? path.match(IMAGE_PATH) : null;
  return match ? { id: match[1], ext: match[2], type: IMAGE_TYPES[match[2]] } : null;
}

export function imageUrl(base, id, ext) {
  return `${base.replace(/\/+$/, "")}/images/${id}.${ext}`;
}

// True only for exactly <base>/images/<id>.<ext>.
export function isOurImage(url, base) {
  const root = String(base ?? "").replace(/\/+$/, "");
  return typeof url === "string" && root !== "" && url.startsWith(`${root}/images/`)
    && parseImagePath(url.slice(root.length)) !== null;
}

// The picture line goes after a marker of its own. formatComment turns every
// "<!--" in a message into "&lt;!--", so a visitor cannot type the marker, and
// a picture line typed into a message stays part of its text.
const IMAGE_MARK = "<!-- keep-site image -->";
const IMAGE_TAIL = /\r?\n\r?\n<!-- keep-site image -->\r?\n!\[picture\]\(([^()\s]+)\)\s*$/;

// ``image`` is a URL the worker made itself (imageUrl), never visitor input.
export function formatComment(name, message, image = null) {
  const safeName = name.replace(/["<>\-]/g, "");
  // Neutralise anything that could forge the marker on a later line.
  const safeMessage = message.replace(/<!--/g, "&lt;!--");
  const picture = image ? `\n\n${IMAGE_MARK}\n![picture](${image})` : "";
  return `<!-- keep-site name="${safeName}" -->\n**${safeName}** wrote:\n\n${safeMessage}${picture}`;
}

// A Discussion comment as the site shows it: who wrote it and what they said,
// plus its picture's address when it has one of ours (under imageBase).
export function parseComment(node, imageBase = "") {
  const body = node.body ?? "";
  const match = body.match(MARKER);
  if (match) {
    const name = match[1];
    const text = body.slice(match[0].length).replace(/^\*\*[^*]*\*\* wrote:\n\n/, "");
    const shown = { id: node.id, name, text, at: node.createdAt, viaSite: true };
    const tail = text.match(IMAGE_TAIL);
    if (tail && isOurImage(tail[1], imageBase)) {
      shown.text = text.slice(0, tail.index);
      shown.image = tail[1];
    }
    return shown;
  }
  return { id: node.id, name: node.author?.login ?? "someone", text: body, at: node.createdAt, viaSite: false };
}

// Names we post under (compared on letters only, like the Myth answer).
// Our own posts are answers, so they get no addressed/waiting box.
export function isStaff(shown, owner, staff) {
  if (!shown.viaSite) return shown.name.toLowerCase() === owner.toLowerCase();
  return staff.map(normalizeAnswer).includes(normalizeAnswer(shown.name));
}

// A visitor's comment is "addressed" once the repository owner gives it a
// rocket reaction on GitHub, "waiting" until then; our own posts get null.
// Only the owner's reaction counts, so visitors cannot tick their own.
export function statusOf(node, shown, owner, staff) {
  if (isStaff(shown, owner, staff)) return null;
  const marked = (node.reactions?.nodes ?? []).some((r) => r.user?.login?.toLowerCase() === owner.toLowerCase());
  return marked ? "addressed" : "waiting";
}

export function shapeThread(discussion, { owner = "", staff = [], imageBase = "" } = {}) {
  if (!discussion) return [];
  const shape = (node) => {
    const shown = parseComment(node, imageBase);
    return { ...shown, status: statusOf(node, shown, owner, staff) };
  };
  return (discussion.comments?.nodes ?? []).map((c) => ({
    ...shape(c),
    replies: (c.replies?.nodes ?? []).map(shape),
  }));
}

// Thumbs up/down on our replies. Each browser remembers its own vote and
// sends it along with the new one, so a changed vote moves a count rather
// than adding one.
const VOTES = ["up", "down"];

export function validateVote(input) {
  const body = input && typeof input === "object" ? input : {};
  const term = String(body.term ?? "").trim();
  const id = String(body.id ?? "");
  const vote = body.vote ?? null;
  const previous = body.previous ?? null;
  if (!term || term.length > 200) return { ok: false, error: "This page is missing its topic." };
  if (!/^[A-Za-z0-9_=-]{4,100}$/.test(id)) return { ok: false, error: "That reply link is broken." };
  if (vote !== null && !VOTES.includes(vote)) return { ok: false, error: "Sorry, that didn't go through." };
  if (previous !== null && !VOTES.includes(previous)) return { ok: false, error: "Sorry, that didn't go through." };
  return { ok: true, value: { term, id, vote, previous } };
}

export function applyVote(counts, previous, vote) {
  const next = { up: counts?.up ?? 0, down: counts?.down ?? 0 };
  if (previous === vote) return next;
  if (previous) next[previous] = Math.max(0, next[previous] - 1);
  if (vote) next[vote] += 1;
  return next;
}

// The public log of conversions made on the web converter, for visitors who
// tick "add this plugin's name". Only these four facts are kept.
export const CONVERSION_LOG_SIZE = 500;

export function validateConversion(input) {
  const body = input && typeof input === "object" ? input : {};
  const plugin = String(body.plugin ?? "").replace(/[\x00-\x1f\x7f]/g, "").trim();
  const levels = Number(body.levels);
  const version = String(body.version ?? "");
  if (!plugin || plugin.length > 64) return { ok: false, error: "That plugin name can't be listed." };
  if (!Number.isInteger(levels) || levels < 0 || levels > 9999) return { ok: false, error: "Sorry, that didn't go through." };
  if (!/^\d{1,3}\.\d{1,3}$/.test(version)) return { ok: false, error: "Sorry, that didn't go through." };
  return { ok: true, value: { plugin, levels, version } };
}

export function addConversion(log, entry, size = CONVERSION_LOG_SIZE) {
  return [entry, ...(Array.isArray(log) ? log : [])].slice(0, size);
}

// Every comment in a thread, replies included, flattened.
export function allComments(thread) {
  return thread.flatMap((c) => [c, ...(c.replies ?? [])]);
}

// The phone alert for a new comment. ``page`` is where it was written, as
// the site reports it; only an address on the site itself is trusted.
export function alertFor({ name, term, message, replyTo }, page, siteUrl) {
  const click = typeof page === "string" && page.startsWith(siteUrl) ? page : siteUrl;
  const short = message.length > 200 ? `${message.slice(0, 200)}...` : message;
  // HTTP headers carry Latin-1 only; keep the title plain.
  const title = `${name} ${replyTo ? "replied" : "wrote"} on ${term}`.replace(/[^ -~]/g, "");
  return { title: title.slice(0, 150), click, body: short };
}
