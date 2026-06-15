"""Per-tool reasoning step.

Before a tool does its real work, this builds a focused query from the user
message plus the tool's area of concern, retrieves the most relevant chunks
from the shared :class:`VectorMemory`, and returns a context block that the
executor injects into the tool's prompt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .vector_store import MemoryRecord, VectorMemory

log = logging.getLogger("agent_server.reasoning")

# What each tool "cares about" — appended to the user message to steer retrieval.
TOOL_FOCUS: dict[str, str] = {
    "Protocol Generator": (
        "clinical trial protocol design study objectives population endpoints "
        "procedures statistics safety ethics"
    ),
    "Health Authority": (
        "regulatory compliance ICH-GCP FDA EMA informed consent data integrity "
        "safety reporting statistical plan ethics"
    ),
    "PI": (
        "scientific soundness feasibility patient recruitment retention safety "
        "monitoring objectives endpoints bias"
    ),
    "Site Physician": (
        "site operations patient burden visit schedule dosing administration "
        "drug supply logistics resources workflow"
    ),
    "TrialGPT Retrieval": (
        "patient conditions diagnoses eligibility candidate clinical trial search keywords"
    ),
    "TrialGPT Matching": (
        "patient eligibility inclusion exclusion criteria matching"
    ),
    "TrialGPT Ranking": (
        "relevance eligibility ranking best matching trial score"
    ),
}


@dataclass
class ReasoningResult:
    query: str
    hits: list[tuple[float, MemoryRecord]] = field(default_factory=list)
    context_block: str = ""
    note: str = ""

    @property
    def has_context(self) -> bool:
        return bool(self.hits)


def reason_before_tool(memory: VectorMemory, tool_key: str, label: str,
                       user_message: str, k: int = 4) -> ReasoningResult:
    """Retrieve relevant shared-memory context for ``tool_key`` before it runs."""
    focus = TOOL_FOCUS.get(tool_key, "")
    query = "\n".join(p for p in (user_message or "", focus) if p).strip()

    hits = memory.search(query, k=k, exclude_source=tool_key)
    if not hits:
        note = f"No prior shared context yet — {label} works from the user request only."
        log.info("  reasoning[%s]: empty memory (mem=%d)", label, len(memory))
        return ReasoningResult(query=query, hits=[], context_block="", note=note)

    lines: list[str] = []
    for i, (score, rec) in enumerate(hits, 1):
        snippet = rec.text.strip()
        lines.append(f"[{i}] (source: {rec.source}, relevance: {score:.2f})\n{snippet}")
    context_block = "\n\n".join(lines)

    sources = ", ".join(rec.source for _, rec in hits)
    note = f"{label} retrieved {len(hits)} relevant snippet(s) from shared memory (sources: {sources})."
    log.info("  reasoning[%s]: %d hit(s) | sources=%s",
             label, len(hits), [rec.source for _, rec in hits])
    return ReasoningResult(query=query, hits=hits, context_block=context_block, note=note)
