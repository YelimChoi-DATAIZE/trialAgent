"""Shared Markdown style guidelines for the clinical-protocol-review agents.

Every agent appends one of these blocks to its prompt so that the Markdown that
gets streamed back to the UI looks consistent across tools (same heading levels,
same Concern/Recommendation labels, no stray code fences, etc.).

NOTE: These strings are fed into ``langchain_core.prompts.PromptTemplate`` which
treats ``{`` / ``}`` as variable delimiters, so the text below must never contain
unescaped curly braces.
"""

# Common conventions shared by every agent.
_COMMON_RULES = """
- Write in clean GitHub-Flavored Markdown.
- Use `## ` for each numbered top-level section heading (e.g. `## 1. Section Title`).
- Use `### ` for sub-sections only when needed.
- Use `-` for bullet lists and `**bold**` only for inline emphasis.
- Use `` `code` `` for identifiers, values, or section names you are quoting.
- Do NOT wrap the whole answer in a code block, and do NOT use HTML or tables.
- Start directly with the first `## ` heading; do not add a preamble sentence.
"""

# For the reviewer agents (Health Authority, PI, Site Physician).
REVIEW_FORMAT = (
    """

    ## Output format (follow exactly)
    """
    + _COMMON_RULES
    + """- Under each section, report findings on their own lines using the bold labels
      `**Concern:**` and `**Recommendation:**`.
    - If a section has no issues, write exactly `No major concerns for this section.`
    """
)

# For the protocol generator (produces the draft itself, not a review).
GENERATE_FORMAT = (
    """

    ## Output format (follow exactly)
    """
    + _COMMON_RULES
)

# Shared-memory context block injected by the reasoning step. The
# ``{retrieved_context}`` placeholder is filled at invoke time with snippets
# retrieved from the run's vector memory (user message + other tools' outputs).
# The value may contain braces, which is safe because only the *template* text
# is parsed for placeholders, not the substituted value.
CONTEXT_BLOCK = """

    ## Shared context retrieved from other tools (reasoning step)
    The snippets below were retrieved from a shared memory of the user's request
    and the Markdown produced by earlier tools in this run. Treat them as
    supporting context: rely on them when relevant, and ignore anything that does
    not apply. Do not simply repeat them.
    ---
    {retrieved_context}
    ---
    """

