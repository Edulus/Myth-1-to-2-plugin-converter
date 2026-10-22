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

export function shapeThread(discussion) {
  if (!discussion) return [];
  return (discussion.comments?.nodes ?? []).map((c) => ({
    ...parseComment(c),
    replies: (c.replies?.nodes ?? []).map(parseComment),
  }));
}
