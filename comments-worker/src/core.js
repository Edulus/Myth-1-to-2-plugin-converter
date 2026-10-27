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
  return { ok: true, value: { term, name, message, replyTo } };
}

export function formatComment(name, message) {
  const safeName = name.replace(/["<>\-]/g, "");
  // Neutralise anything that could forge the marker on a later line.
  const safeMessage = message.replace(/<!--/g, "&lt;!--");
  return `<!-- keep-site name="${safeName}" -->\n**${safeName}** wrote:\n\n${safeMessage}`;
}

// A Discussion comment as the site shows it: who wrote it and what they said.
export function parseComment(node) {
  const body = node.body ?? "";
  const match = body.match(MARKER);
  if (match) {
    const name = match[1];
    const text = body.slice(match[0].length).replace(/^\*\*[^*]*\*\* wrote:\n\n/, "");
    return { id: node.id, name, text, at: node.createdAt, viaSite: true };
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

export function shapeThread(discussion, { owner = "", staff = [] } = {}) {
  if (!discussion) return [];
  const shape = (node) => {
    const shown = parseComment(node);
    return { ...shown, status: statusOf(node, shown, owner, staff) };
  };
  return (discussion.comments?.nodes ?? []).map((c) => ({
    ...shape(c),
    replies: (c.replies?.nodes ?? []).map(shape),
  }));
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
