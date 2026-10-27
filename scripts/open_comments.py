"""List the visitor comments on the progress site still waiting for a reply.

A comment counts as addressed once the repository owner gives it a rocket
reaction on GitHub (see comments-worker/src/core.js). Run from the repo root:

    python scripts/open_comments.py
"""

import json
import pathlib
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import keep_site  # noqa: E402


def thread(term):
    url = f"{keep_site.COMMENTS_API}/comments?term={urllib.parse.quote(term)}"
    # The service's host refuses urllib's default user agent.
    request = urllib.request.Request(url, headers={"User-Agent": "open-comments/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["comments"]


def main():
    terms = [u["term"] for u in keep_site.UPDATES] + [q["term"] for q in keep_site.QUESTIONS]
    waiting = 0
    for term in terms:
        for comment in thread(term):
            for c in [comment] + comment["replies"]:
                first_line = c["text"].strip().splitlines()[0][:100]
                if c.get("status") == "waiting":
                    waiting += 1
                    print(f"[ ] {term}\n    {c['name']}, {c['at'][:10]} (id {c['id']}): {first_line}")
                elif c.get("votes", {}).get("down"):
                    # A thumbs-down on one of our answers puts it back on the list.
                    waiting += 1
                    v = c["votes"]
                    print(f"[-] {term}\n    our answer, {c['at'][:10]}, {v['up']} up / {v['down']} down: {first_line}")
    print(f"\n{waiting} waiting for a reply or with a thumbs-down.")


if __name__ == "__main__":
    main()
