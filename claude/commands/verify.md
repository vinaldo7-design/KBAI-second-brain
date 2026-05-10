---
description: Verify a factual claim against Perplexity — returns verdict, confidence, and supporting evidence.
---

Claim: `$ARGUMENTS`

## Step 1 — verify

Call `mcp__perplexity-research__research_verify_claim(claim_text="$ARGUMENTS")`.

## Step 2 — render

Print:

```
Claim:      <claim_text>
Verdict:    <verdict>          (true / false / uncertain / partially_true)
Confidence: <confidence>       (0.0–1.0)

Evidence:
- <evidence point 1>
- <evidence point 2>
...
```

If verdict is `uncertain` or confidence < 0.6: add a one-line caveat — "Low confidence — treat as a starting point, not a fact."

No preamble. No trailing notes.
