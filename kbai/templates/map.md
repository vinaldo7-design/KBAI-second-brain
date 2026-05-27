---
id: 
title: {title}
created: 
updated: 
type: map
status: evergreen
summary: {summary}
tags:
  - topic/
---

# {title} — Map

> {summary}

## Entry Points
Start here if new to this cluster.
- 

## Open Questions
What this cluster doesn't yet answer.
- 

## Connected Maps
- 

---
*Maps are navigation aids, not containers.*

```dataview
TABLE summary, status
FROM "01-Ideas"
WHERE contains(tags, "topic/REPLACE")
SORT status ASC
```

## Status Log
- created
