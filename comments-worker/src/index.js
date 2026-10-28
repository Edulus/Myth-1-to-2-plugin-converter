// KEEP's comment box: lets someone with no GitHub account read and write the
// comment threads on the progress site. Threads are GitHub Discussions in the
// repo's Announcements category, one per page, titled with the page's term --
// the same storage giscus used, so either can be read in the repo.
//
//   GET  /config          -> { question }            the Myth check question
//   GET  /comments?term=  -> { comments: [...] }     a page's thread
//   POST /comments        -> { comments: [...] }     add a comment or reply
//
// Each comment carries a status: "addressed" once the repo owner reacts with
// a rocket on GitHub, "waiting" before that, null for our own posts
// (STAFF_NAMES). Our own posts also carry thumbs up/down counts, kept in the
// VOTES KV store:
//
//   POST /vote  { term, id, vote, previous }  -> { votes: { up, down } }
//
// The web converter's public log, for visitors who tick the box (kept in
// the same KV store, under the key "conversions"):
//
//   GET  /conversions                              -> { conversions: [...] }
//   POST /conversions  { plugin, levels, version } -> { conversions: [...] }
//
// Secrets: GITHUB_TOKEN (fine-grained, Discussions read/write on the repo);
//          NTFY_TOPIC (optional) -- an unguessable ntfy.sh topic. Each new
//          comment is pushed there, since posts made through the site go out
//          under the token owner's account and GitHub does not notify you
//          of your own activity.

import {
  shapeThread, validate, formatComment, alertFor, validateVote, applyVote, allComments,
  validateConversion, addConversion,
} from "./core.js";

const GRAPHQL = "https://api.github.com/graphql";

function cors(env, request) {
  const origin = request.headers.get("Origin") ?? "";
  const allowed = env.ALLOWED_ORIGINS.split(",").map((s) => s.trim());
  return {
    "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0],
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    Vary: "Origin",
  };
}

function json(data, status, headers) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers },
  });
}

async function github(env, query, variables) {
  const res = await fetch(GRAPHQL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "keep-comments-worker",
    },
    body: JSON.stringify({ query, variables }),
  });
  const data = await res.json();
  if (!res.ok || data.errors) {
    throw new Error(`GitHub: ${res.status} ${JSON.stringify(data.errors ?? data).slice(0, 300)}`);
  }
  return data.data;
}

// ROCKET is the "addressed" mark (see core.js statusOf).
const COMMENT_FIELDS = `id body createdAt author { login } reactions(content: ROCKET, first: 20) { nodes { user { login } } }`;
const THREAD_FIELDS = `
  id
  comments(first: 100) {
    nodes {
      ${COMMENT_FIELDS}
      replies(first: 100) { nodes { ${COMMENT_FIELDS} } }
    }
  }`;

function threadOptions(env) {
  return { owner: env.REPO.split("/")[0], staff: (env.STAFF_NAMES ?? "").split(",") };
}

// A page's thread, with the vote counts on our own posts (status null).
async function loadThread(env, term) {
  const thread = shapeThread(await findDiscussion(env, term), threadOptions(env));
  if (!env.VOTES) return thread;
  await Promise.all(
    allComments(thread)
      .filter((c) => c.status === null)
      .map(async (c) => {
        c.votes = (await env.VOTES.get(`votes:${c.id}`, "json")) ?? { up: 0, down: 0 };
      }),
  );
  return thread;
}

// Two queries, not one: GitHub refuses a query that could reach more than
// 500,000 nodes, and discussions x comments x replies at 100 each is 1,000,000.
async function findDiscussion(env, term) {
  const [owner, name] = env.REPO.split("/");
  const listed = await github(
    env,
    `query($owner: String!, $name: String!, $category: ID!) {
      repository(owner: $owner, name: $name) {
        discussions(first: 100, categoryId: $category, orderBy: { field: CREATED_AT, direction: DESC }) {
          nodes { id title }
        }
      }
    }`,
    { owner, name, category: env.CATEGORY_ID },
  );
  const match = listed.repository.discussions.nodes.find((d) => d.title === term);
  if (!match) return null;
  const data = await github(
    env,
    `query($id: ID!) { node(id: $id) { ... on Discussion { ${THREAD_FIELDS} } } }`,
    { id: match.id },
  );
  return data.node;
}

async function createDiscussion(env, term) {
  const data = await github(
    env,
    `mutation($repo: ID!, $category: ID!, $title: String!, $body: String!) {
      createDiscussion(input: { repositoryId: $repo, categoryId: $category, title: $title, body: $body }) {
        discussion { title ${THREAD_FIELDS} }
      }
    }`,
    {
      repo: env.REPO_ID,
      category: env.CATEGORY_ID,
      title: term,
      body: `Comments for **${term}** on the [progress site](${env.SITE_URL}).`,
    },
  );
  return data.createDiscussion.discussion;
}

async function addComment(env, discussionId, body, replyTo) {
  await github(
    env,
    `mutation($discussion: ID!, $body: String!, $replyTo: ID) {
      addDiscussionComment(input: { discussionId: $discussion, body: $body, replyToId: $replyTo }) { comment { id } }
    }`,
    { discussion: discussionId, body, replyTo },
  );
}

async function notify(env, alert) {
  try {
    await fetch(`https://ntfy.sh/${env.NTFY_TOPIC}`, {
      method: "POST",
      headers: { Title: alert.title, Click: alert.click, Tags: "speech_balloon" },
      body: alert.body,
    });
  } catch (err) {
    console.error("ntfy", err);
  }
}

export default {
  async fetch(request, env, ctx) {
    const headers = cors(env, request);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
    const url = new URL(request.url);

    try {
      if (url.pathname === "/config" && request.method === "GET") {
        return json({ question: env.QUESTION }, 200, headers);
      }

      if (url.pathname === "/comments" && request.method === "GET") {
        const term = url.searchParams.get("term") ?? "";
        if (!term) return json({ error: "missing term" }, 400, headers);
        return json({ comments: await loadThread(env, term) }, 200, headers);
      }

      if (url.pathname === "/conversions" && request.method === "GET") {
        return json({ conversions: (await env.VOTES.get("conversions", "json")) ?? [] }, 200, headers);
      }

      if (url.pathname === "/conversions" && request.method === "POST") {
        const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
        const { success } = await env.CONVERT_LIMIT.limit({ key: ip });
        if (!success) return json({ error: "Easy there -- please wait a minute." }, 429, headers);
        let input;
        try {
          input = await request.json();
        } catch {
          return json({ error: "Sorry, that didn't go through." }, 400, headers);
        }
        const checked = validateConversion(input);
        if (!checked.ok) return json({ error: checked.error }, 400, headers);
        const log = addConversion(await env.VOTES.get("conversions", "json"), {
          ...checked.value,
          at: new Date().toISOString(),
        });
        await env.VOTES.put("conversions", JSON.stringify(log));
        return json({ conversions: log }, 200, headers);
      }

      if (url.pathname === "/vote" && request.method === "POST") {
        const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
        const { success } = await env.VOTE_LIMIT.limit({ key: ip });
        if (!success) return json({ error: "Easy there -- please wait a minute." }, 429, headers);
        let input;
        try {
          input = await request.json();
        } catch {
          return json({ error: "Sorry, that didn't go through." }, 400, headers);
        }
        const checked = validateVote(input);
        if (!checked.ok) return json({ error: checked.error }, 400, headers);
        const { term, id, vote, previous } = checked.value;
        // Only our own posts on this page can be voted on.
        const target = allComments(await loadThread(env, term)).find((c) => c.id === id);
        if (!target || target.status !== null) return json({ error: "That reply can't be voted on." }, 400, headers);
        const votes = applyVote(target.votes, previous, vote);
        await env.VOTES.put(`votes:${id}`, JSON.stringify(votes));
        return json({ votes }, 200, headers);
      }

      if (url.pathname === "/comments" && request.method === "POST") {
        const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
        const { success } = await env.POST_LIMIT.limit({ key: ip });
        if (!success) return json({ error: "Easy there -- please wait a minute and send it again." }, 429, headers);

        let input;
        try {
          input = await request.json();
        } catch {
          return json({ error: "Sorry, that didn't go through." }, 400, headers);
        }
        const checked = validate(input, env.ANSWERS.split(","));
        if (!checked.ok) return json({ error: checked.error }, 400, headers);
        const { term, name, message, replyTo } = checked.value;

        const discussion = (await findDiscussion(env, term)) ?? (await createDiscussion(env, term));
        await addComment(env, discussion.id, formatComment(name, message), replyTo);
        if (env.NTFY_TOPIC) ctx.waitUntil(notify(env, alertFor(checked.value, input.page, env.SITE_URL)));
        return json({ comments: await loadThread(env, term) }, 200, headers);
      }

      return json({ error: "not found" }, 404, headers);
    } catch (err) {
      console.error(err);
      return json({ error: "Something went wrong on our side -- please try again in a little while." }, 502, headers);
    }
  },
};
