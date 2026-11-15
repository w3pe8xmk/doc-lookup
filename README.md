# doc-lookup

A Claude Code skill that saves documentation summaries as local Markdown files and reuses them across sessions.

[日本語](README_JA.md)

When Claude needs to check an API, configuration option, or other external documentation, doc-lookup searches the local cache first. If it finds a current summary, Claude can answer without fetching the page again. Otherwise, it checks the source and saves or updates the summary with its URL and retrieval date.

## How it works

1. **Fresh match:** Read the cached summary and answer from it.
2. **Stale match:** Check the source again, report any changes, and update the summary.
3. **No match:** Research the topic, preferring primary sources, and save a summary.

Each summary has an expiration period, or time to live (TTL). The default depends on the source domain and can be overridden per file. Asking for the latest information or a different version also triggers a source check, even if the cache has not expired. A valid TTL does not guarantee that the source has not changed.

The cache is stored in `~/.claude/docs/reference/` by default. The files are plain Markdown, so you can read, edit, search, and version them. The search script reads their frontmatter directly; there is no separate index to maintain.

### Example

```text
First request:  "How do I cache static assets in Cloudflare Workers?"
                No match → check the official docs → save a summary and answer

Later request:  "Remind me how Workers static asset caching works."
                Fresh match → answer from the cached summary
```

When a Markdown source is available, the skill instructs Claude to fetch it with `curl` and read the relevant section. This avoids relying on a `WebFetch` summary for details such as flags and configuration values.

## Installation

### Claude Code plugin (recommended)

Run these commands in Claude Code:

```text
/plugin marketplace add w3pe8xmk/doc-lookup
/plugin install doc-lookup@doc-lookup
```

The plugin can receive updates through the marketplace.

### Manual installation

```bash
git clone https://github.com/w3pe8xmk/doc-lookup
cp -r doc-lookup/skills/doc-lookup ~/.claude/skills/
```

A manually copied skill does not update automatically.

## Usage

Ask Claude Code to check documentation as usual. The skill instructs Claude to search the cache before using `WebSearch` or `WebFetch`; whether it is invoked depends on Claude and the request.

You can also invoke it directly:

```text
/doc-lookup cloudflare workers static assets cache
```

Ask Claude to list cached or stale documents. If you installed the skill manually, you can also run the search script directly:

```bash
python3 ~/.claude/skills/doc-lookup/scripts/doc-search.py --list    # all cached documents
python3 ~/.claude/skills/doc-lookup/scripts/doc-search.py --stale   # expired documents
```

## Configuration

| Setting | Description |
|---|---|
| Cache location | Defaults to `~/.claude/docs/reference/`. Set `DOC_LOOKUP_ROOT` to change the search location, and update the save path in `references/research.md` to match. |
| TTL | Defaults vary by source domain: 7 days for claude.com and anthropic.com, 365 days for rfc-editor.org and w3.org, and 30 days for most other domains. Set `ttl:` in a document to override the default. |
| Model and effort | `SKILL.md` sets `model: sonnet` and `effort: low`. Edit its frontmatter to change them. |

## Security

- Cached content is read back as reference material, and an excerpt of the best match is placed into the prompt automatically when the skill runs. The skill instructs Claude to save attributable facts in its own words and ignore instructions in fetched pages. This reduces risk but does not guarantee safety. Review `~/.claude/docs/reference/` periodically.
- The skill pre-approves `Write`, `Edit`, `WebFetch`, and `WebSearch` through `allowed-tools`. Review `SKILL.md` before installation and remove permissions you do not need.

## Requirements

- Python 3.8 or later and `curl`. The search script uses only the Python standard library.
- macOS, Linux, or WSL2. Native Windows is untested.
- The skill replies in your language; search supports Japanese and other CJK text.

## License

[MIT](LICENSE)
