---
description: Run the whole pipeline for one task with approval gates
argument-hint: <task-id>
---

Run the full pipeline for $ARGUMENTS, stopping at each gate:

1. /understand $ARGUMENTS  -> STOP for my answers or "approved"
2. /blueprint $ARGUMENTS   -> STOP for "approved"
3. /build $ARGUMENTS
4. /review $ARGUMENTS      -> STOP when approved
5. /ship $ARGUMENTS        -> only after I say "ship"

Never skip a gate, even if the task looks simple. Tell me which gate you are
at every time you stop.
