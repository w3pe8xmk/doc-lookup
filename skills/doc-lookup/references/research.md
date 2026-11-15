# Research and save procedure

### B. Marked "⚠ stale: re-verify"

1. Read the cache
2. Fetch the source URL to check for differences
3. Unchanged → update `fetched:` to today and answer.
   Changed → rewrite the affected parts, update `fetched:`, and **tell the user what changed and how** (never overwrite silently)

### C. No match

1. Research the web. **Prefer primary sources** (official docs, source code, specs); secondary sources only as support. Fetch as described in "How to fetch" below
2. Save to `~/.claude/docs/reference/<kebab-case>.md` (format below)
3. Tell the user that you saved it and where

## How to fetch (B and C)

- **If a Markdown source is available, use curl, not WebFetch.** WebFetch summarizes everything past roughly the first 40k characters of a long page, so it is not verbatim.
  `curl -sL '<md URL>' -o <file> && wc -l <file> && grep -n -i -E '<term1>|<term2>' <file>`, then `sed -n '<start>,<end>p' <file>` to read only the relevant section.
  - Claude Code: `https://code.claude.com/docs/en/<page>.md` (index: `/docs/llms.txt`)
  - Anthropic API: `https://platform.claude.com/docs/en/<page>.md`
  - GitHub: `github.com/<o>/<r>/blob/<ref>/<p>` → `raw.githubusercontent.com/<o>/<r>/<ref>/<p>`
  - Elsewhere, pick URLs from `<official domain>/llms.txt` if it exists
- Do not guess URL paths. If unknown, search `site:<official domain> <keyword>`
- At most 8 WebFetch calls per request. After two 404s in a row, go back to searching. Stop once you found what you need
- Before concluding "not documented", re-fetch once with a different extraction prompt

## Save format

```markdown
---
topic: Claude Code hooks configuration
source: https://code.claude.com/docs/en/hooks
fetched: 2026-08-31
keywords: hooks, PreToolUse, SessionStart, settings.json
---

## Summary

(conclusion first)

## Details

(tables, code samples; not a verbatim copy — write it so it is understandable later)

## Sources

- [Page title](URL) — date referenced
```

| Field | Content |
|---|---|
| `topic` (required) | The subject. Weighted most heavily in search |
| `source` (required) | Primary-source URL; a YAML list for several |
| `fetched` (required) | `YYYY-MM-DD`. Basis for the freshness check; without it a warning is always shown |
| `keywords` (recommended) | Aliases, abbreviations and translations not in `topic` |
| `ttl` (optional) | Allowed age in days; derived from the source domain if omitted |

Default TTL: claude.com / anthropic.com 7 days, github.com / pypi.org / npmjs.com 30,
python.org / nodejs.org / developer.mozilla.org 180, rfc-editor.org / w3.org 365, others 30.
Override with `ttl:` or edit `DOMAIN_TTL` in `scripts/doc-search.py`.

### Writing principles

- Summarize instead of pasting, but copy numbers, flag names and commands exactly as in the source
- Conclusion first; no history
- Mark anything you could not confirm in a primary source as "**unverified**" (a blank looks verified)
- Kebab-case file names; no emoji
