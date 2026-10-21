"""Response schema for POST /api/v1/sessions/{session_id}/complete (design doc 14; T1.9).

Table models are never returned from the API (17.1); this is the stats-only summary. The design
doc's "update phase" and "enqueue jobs" parts of /complete are M2 (assignment/worker) and are
left as documented follow-ups in the router (T1.9 brief owner answer 3).
"""

from pydantic import BaseModel


class SessionSummary(BaseModel):
    """What POST /sessions/{session_id}/complete returns: the computed session stats.

    wpm and accuracy are None when undefined (owner answer 5). bigram_count is the number of
    bigram_stats rows written for the session; blocks is the number of blocks in the session.
    """

    session_id: str
    wpm: float | None
    accuracy: float | None
    bigram_count: int
    blocks: int
