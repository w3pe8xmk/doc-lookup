#!/usr/bin/env python3
"""Search cached reference documents (default: ~/.claude/docs/reference/).

Each document is a Markdown file with YAML-like frontmatter (topic, source,
fetched, keywords, optional ttl). Frontmatter is read directly on every run,
so there is no index file that could drift out of sync with the documents.
Stdlib only; works on Python 3.8+.

Always exits 0: the skill embeds this output in a ```!``` block, and a
non-zero exit would stop the skill from loading.

usage:
  doc-search.py <term> [term...]   keyword search (OR, ranked by score)
  doc-search.py --stdin            read the query from stdin (safe with quotes/brackets)
  doc-search.py --list             list everything, newest first
  doc-search.py --stale            list only documents past their TTL
"""
import argparse
import datetime as dt
import glob
import math
import os
import re
import sys
from urllib.parse import urlparse

# Cache location; override with the DOC_LOOKUP_ROOT environment variable.
ROOT = os.path.expanduser(os.environ.get("DOC_LOOKUP_ROOT", "~/.claude/docs/reference"))
DEFAULT_TTL = 30

# Default TTL (days) per source domain, subdomains included.
# A `ttl:` in frontmatter takes precedence.
DOMAIN_TTL = [
    # Vendor product docs: change almost daily
    ("claude.com", 7),
    ("anthropic.com", 7),
    # Active OSS: changes with every release
    ("github.com", 30),
    ("githubusercontent.com", 30),
    ("pypi.org", 30),
    ("npmjs.com", 30),
    # Language/runtime official docs: change, but slowly
    ("python.org", 180),
    ("nodejs.org", 180),
    ("developer.mozilla.org", 180),
    # Standards and specs: almost never change
    ("rfc-editor.org", 365),
    ("w3.org", 365),
]

FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def parse(path):
    """Return {"path", "meta", "body"}, or None if unreadable or no frontmatter.

    Understands only `key: value` lines and `- item` lists.
    """
    try:
        with open(path, errors="ignore") as f:
            raw = f.read()
    except OSError:
        return None
    m = FM.match(raw)
    if not m:
        return None

    meta, body = {}, raw[m.end():]
    key = None
    for line in m.group(1).splitlines():
        # "- item": append to the list under the previous key
        if re.match(r"^\s*-\s+", line) and key:
            meta[key] = meta.get(key, []) if isinstance(meta.get(key), list) else []
            meta[key].append(line.split("-", 1)[1].strip())
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        meta[key] = val if val else []
    return {"path": path, "meta": meta, "body": body}


def age_days(meta):
    f = meta.get("fetched")
    if not isinstance(f, str):
        return None
    try:
        return (dt.date.today() - dt.date.fromisoformat(f.strip())).days
    except ValueError:
        return None


def sources(meta):
    s = meta.get("source", [])
    return s if isinstance(s, list) else [s]


def ttl_of(meta):
    """Return (allowed days, reason): frontmatter `ttl:`, else source-domain default, else DEFAULT_TTL."""
    raw = meta.get("ttl")
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip()), "explicit"

    best = None  # (days, domain); with several sources the shortest TTL wins
    for src in sources(meta):
        host = urlparse(str(src)).hostname or ""
        for domain, days in DOMAIN_TTL:
            if host == domain or host.endswith("." + domain):
                if best is None or days < best[0]:
                    best = (days, domain)
    return best or (DEFAULT_TTL, "default")


def load_all():
    docs = [parse(p) for p in glob.glob(os.path.join(ROOT, "**/*.md"), recursive=True)]
    return [d for d in docs if d and os.path.basename(d["path"]) != "README.md"]


STOP = {"the", "and", "for", "with", "how", "what", "from", "into", "claude", "code"}
CJK_SPLIT = re.compile(r"[のはをにでとがやもへ、。，．・：:；;！？!?「」『』（）()\[\]{}<>\"'`/\\,|]+")


def tokenize(raw):
    """Split a query into de-duplicated, lower-cased search terms.

    Works on whole sentences, not only keyword lists:
    - ASCII words (steamworks-ffi-node, wrangler.toml, ...) are kept intact;
      1-character words and STOP words are dropped
    - CJK runs are split on particles, punctuation and brackets (chunks of 2+ chars)
    """
    toks = []
    for chunk in re.split(r"\s+", raw):
        for ascii_tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9._+\-]*", chunk):
            t = ascii_tok.lower().strip(".-_+")
            if len(t) >= 2 and t not in STOP:
                toks.append(t)
        for run in re.findall(r"[^\x00-\x7f]+", chunk):
            for part in CJK_SPLIT.split(run):
                if len(part) >= 2:
                    toks.append(part.lower())
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def count(text, t):
    """Count occurrences of t in text.

    ASCII terms must match on word boundaries ("ai" must not hit "main");
    CJK has no word boundaries, so it is a plain substring count.
    """
    if t.isascii():
        return len(re.findall(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", text))
    return text.count(t)


def score(doc, terms):
    """Per term: topic +10, keywords +6, filename +4, body occurrences (max 5); summed."""
    topic = str(doc["meta"].get("topic", "")).lower()
    kw = doc["meta"].get("keywords", "")
    kw = " ".join(kw).lower() if isinstance(kw, list) else str(kw).lower()
    name = os.path.basename(doc["path"]).lower()
    body = doc["body"].lower()

    total = 0
    for t in terms:
        hits = 0
        if count(topic, t):
            hits += 10
        if count(kw, t):
            hits += 6
        if t in name:
            hits += 4
        hits += min(count(body, t), 5)
        total += hits
    return total


def fmt(doc, with_sources=True):
    home = os.path.expanduser("~")
    p = doc["path"]
    rel = "~/" + os.path.relpath(p, home) if p.startswith(home + os.sep) else p
    a = age_days(doc["meta"])
    ttl, why = ttl_of(doc["meta"])

    if a is None:
        age = "fetch date unknown ⚠ stale: re-fetch"
    elif a > ttl:
        age = f"{a} days ago / TTL {ttl}d ({why}) ⚠ stale: re-verify"
    else:
        age = f"{a} days ago / TTL {ttl}d ({why})"

    out = [f"  {doc['meta'].get('topic', '(no topic)')}",
           f"    {rel}",
           f"    fetched: {doc['meta'].get('fetched', '?')} ({age})"]
    if with_sources:
        for s in sources(doc["meta"]):
            out.append(f"    source: {s}")
    return "\n".join(out)



def excerpt(doc, limit=2000):
    """The '## Summary' section (or the start of the body), capped, so the skill can answer without a second Read."""
    m = re.search(r"^## Summary\s*\n(.*?)(?=^## |\Z)", doc["body"], re.S | re.M)
    text = (m.group(1) if m else "").strip() or doc["body"].strip()
    return text[:limit] + (" ...(truncated)" if len(text) > limit else "")


def procedure():
    """Print the research/save procedure, only when it is needed (no match, or a stale hit)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "research.md")
    try:
        with open(path, encoding="utf-8") as f:
            print("== Procedure (follow this for B / C) ==\n" + f.read())
    except OSError:
        pass


def is_stale(doc):
    a = age_days(doc["meta"])
    return a is None or a > ttl_of(doc["meta"])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="*")
    ap.add_argument("--stdin", action="store_true",
                    help="read the query from stdin (avoids shell expansion)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--stale", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(ROOT):
        print(f"No cache ({ROOT} does not exist) -> research on the web and save the result")
        procedure()
        return

    docs = load_all()
    if not docs:
        print("No cache (reference/ is empty) -> research on the web and save the result")
        procedure()
        return

    # Unknown fetch date sorts as oldest (not `a or ...`: age 0 is valid)
    def age_or_oldest(doc):
        a = age_days(doc["meta"])
        return 10**6 if a is None else a

    if args.list or args.stale:
        sel = [d for d in docs if not args.stale or is_stale(d)]
        sel.sort(key=age_or_oldest)
        label = "stale (past each document's TTL)" if args.stale else "all"
        print(f"== {label}: {len(sel)} of {len(docs)} ==\n")
        for d in sel:
            print(fmt(d) + "\n")
        return

    raw = sys.stdin.read() if args.stdin else " ".join(args.terms)
    terms = tokenize(raw)
    if not terms:
        print("Empty query (no usable terms) -> retry with 2-4 short English keywords")
        return

    # Weight terms by rarity (IDF): a rare term like steamworks-ffi-node counts
    # more than one that appears in most documents, like "control" in Cache-Control
    per = {t: [score(d, [t]) for d in docs] for t in terms}
    weight = {t: math.log(1 + len(docs) / max(1, sum(1 for s in per[t] if s > 0)))
              for t in terms}
    rows = []
    for i, d in enumerate(docs):
        raw = sum(per[t][i] for t in terms)
        rows.append((sum(weight[t] * per[t][i] for t in terms), raw, d))
    rows.sort(key=lambda r: (-r[0], r[2]["path"]))
    # Low scores from incidental body mentions are noise. Keep only raw >= 6
    # (a topic/keywords/filename-level hit) and weighted >= 50% of the top
    top = rows[0][0]
    hits = [d for w, raw, d in rows if raw >= 6 and w >= top * 0.5][:5]

    if not hits:
        # Normal entry to the skill's branch C, not an error (exit 0, see module docstring)
        print(f"No match (terms: {' '.join(terms)})")
        print("-> research on the web and save the result under reference/")
        procedure()
        return

    print(f"== {len(hits)} match(es) (terms: {' '.join(terms)}) ==\n")
    for i, d in enumerate(hits):
        print(fmt(d, with_sources=False) + "\n")
        if i == 0 and not is_stale(d):
            text = excerpt(d)
            if text:
                print("    excerpt of the top match:")
                print("\n".join("    | " + ln for ln in text.splitlines()) + "\n")
    if any(is_stale(d) for d in hits):
        procedure()


if __name__ == "__main__":
    main()
