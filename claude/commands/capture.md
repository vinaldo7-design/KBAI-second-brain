---
description: Capture an idea into the vault — preview then write on confirmation.
---

Idea: `$ARGUMENTS`

## Step 1 — context

Call `mcp__mini-vinny__assemble_context(query="$ARGUMENTS", seed_k=3)`.

Use results to identify the closest neighbour notes and candidate edge types.

## Step 2 — draft

Derive the following from the idea and the context results:

- `note_id` (file name): kebab-case slug from the title, e.g. `distributed-systems-tradeoffs`
- `id` (frontmatter): current date-time as YYYYMMDDHHmm, e.g. `202605121430`
- `type`: `capture` by default; upgrade to `idea` if the content has a clear falsifiable claim and an identifiable tension
- Folder: `00-Captures` for `type=capture`; `01-Ideas` for `type=idea`

Build the frontmatter dict:
```
id: <YYYYMMDDHHmm>
title: <proposed title>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
type: capture          # or idea
status: seedling
summary: <one-sentence summary>
tags:
  - topic/<x>
  - lens/<y>
origin: conversation
```

Build the body:
```
# <Title>

<2–3 sentence core claim — direct declarative style, no hedging>

## Links

### Builds on
- [[<closest neighbour from context>]]

### Analogous to
-
```

Show the full proposed note as a fenced code block (frontmatter delimiters + body).

## Step 3 — preview prompt

After showing the preview, print this line exactly — no surrounding text, no extra punctuation:

```
Preview ready. Say 'create it' to write to vault, or 'edit: <field> <value>' to adjust before creating.
```

## Step 4 — on 'create it'

Call:

```
mcp__write-agent__write_create_note(
  folder="00-Captures",    # use "01-Ideas" if type=idea
  note_id="<proposed-id>",
  frontmatter=<dict>,
  body=<body>,
  dryrun=False
)
```

On success (`status="applied"`), print exactly:

```
Created: <receipt.file> (journal #<receipt.journal_id>)
```

On error, print the `message` field from the receipt and stop.

## Step 5 — on 'edit: <field> <value>'

Apply the change to the current draft (frontmatter field or body section as appropriate).
Re-display the full preview as in Step 2, then repeat Step 3.
Continue the loop until 'create it'.

No preamble. No trailing disclaimers.
