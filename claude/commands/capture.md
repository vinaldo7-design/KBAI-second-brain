---
description: Generate a draft note proposal from a raw idea — preview only, no vault writes.
---

Idea: `$ARGUMENTS`

## Step 1 — context

Call `mcp__mini-vinny__assemble_context(query="$ARGUMENTS", mode="standard", seed_k=3)`.

Use the results to find:
- The most relevant existing note to link from (the "parent" anchor)
- 2–3 related notes that would become neighbours

## Step 2 — generate draft

Produce a preview of the note that would be created:

```
---
title: <proposed-title>
note_id: <proposed-kebab-case-id>
tags: [<suggested tags based on neighbours>]
---

# <Title>

<2–3 sentence core claim — in Vinay's direct declarative style, no hedging>

## Links to add

- [[note_a]] — <edge_type>: <reason>
- [[note_b]] — <edge_type>: <reason>
```

## Step 3 — placement

Print one line: `Suggested folder: <folder based on note type>`

## Step 4 — confirm

Print:
```
This is a preview. No file has been created.
To create: tell me "create it" and I'll write the file via the vault tools.
```

No preamble. No trailing disclaimers beyond Step 4.
