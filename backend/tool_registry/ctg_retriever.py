"""ClinicalTrials.gov retriever with a ReAct loop.

Unlike ``trialgpt_tools`` (which searches a bundled local dataset), this tool
queries the **live ClinicalTrials.gov API v2** based on the user's request and
drives the search with a small ReAct loop:

    Thought -> Action(search_trials | finish) -> Observation -> ... -> Final

In live mode an LLM produces each Thought/Action; in mock mode (no
``OPENAI_API_KEY``) it falls back to a single keyword search so the tool still
returns real trials without any LLM. The whole trace is rendered as Markdown so
the reasoning process is visible in the UI.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

log = logging.getLogger("agent_server.ctg")

CTG_API = "https://clinicaltrials.gov/api/v2/studies"
_FIELDS = "NCTId,BriefTitle,OverallStatus,Condition,BriefSummary,InterventionName,EligibilityCriteria"
_UA = "dataizeai-trial-agent/0.1"


# ---------------------------------------------------------------------------
# CTG API v2 client
# ---------------------------------------------------------------------------
def search_trials(term: str, *, condition: str = "", intervention: str = "",
                  status: str = "", page_size: int = 5, timeout: int = 30) -> list[dict]:
    """Query ClinicalTrials.gov API v2 and return a list of compact trial dicts."""
    params: dict[str, str] = {"pageSize": str(max(1, min(page_size, 50))), "fields": _FIELDS}
    if term.strip():
        params["query.term"] = term.strip()
    if condition.strip():
        params["query.cond"] = condition.strip()
    if intervention.strip():
        params["query.intr"] = intervention.strip()
    if status.strip():
        params["filter.overallStatus"] = status.strip().upper()

    url = CTG_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)

    out: list[dict] = []
    for study in data.get("studies", []):
        ps = study.get("protocolSection", {})
        ident = ps.get("identificationModule", {})
        out.append({
            "nctId": ident.get("nctId", ""),
            "title": ident.get("briefTitle", ""),
            "status": ps.get("statusModule", {}).get("overallStatus", ""),
            "conditions": ps.get("conditionsModule", {}).get("conditions", []),
            "interventions": [i.get("name", "") for i in
                              ps.get("armsInterventionsModule", {}).get("interventions", [])],
            "summary": ps.get("descriptionModule", {}).get("briefSummary", ""),
            "eligibility": ps.get("eligibilityModule", {}).get("eligibilityCriteria", ""),
        })
    return out


# ---------------------------------------------------------------------------
# Adapt CTG studies into the TrialGPT trial format (so matching/ranking can
# consume CTG search results directly).
# ---------------------------------------------------------------------------
def _normalize_criteria(text: str) -> str:
    """Turn a criteria blob into items separated by blank lines.

    TrialGPT's parser splits criteria on blank lines, so we re-flow numbered or
    bulleted lists into one item per blank-line-delimited block.
    """
    items: list[str] = []
    current = ""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(\d+[\.\)]|[\*\-\u2022])\s+", line):
            if current:
                items.append(current.strip())
            current = re.sub(r"^(\d+[\.\)]|[\*\-\u2022])\s+", "", line)
        else:
            current = f"{current} {line}".strip() if current else line
    if current:
        items.append(current.strip())
    return "\n\n".join(items)


def _split_eligibility(text: str) -> tuple[str, str]:
    """Split a CTG eligibility blob into (inclusion, exclusion) item strings."""
    text = text or ""
    m = re.search(r"exclusion criteria\s*:?", text, re.IGNORECASE)
    if m:
        inc, exc = text[:m.start()], text[m.end():]
    else:
        inc, exc = text, ""
    inc = re.sub(r"inclusion criteria\s*:?", "", inc, flags=re.IGNORECASE)
    return _normalize_criteria(inc), _normalize_criteria(exc)


def to_trialgpt_trial(t: dict) -> dict:
    """Convert a compact CTG dict into the trial schema TrialGPT expects."""
    inc, exc = _split_eligibility(t.get("eligibility", ""))
    return {
        "NCTID": t.get("nctId", ""),
        "brief_title": t.get("title", ""),
        "diseases_list": list(t.get("conditions", [])),
        "drugs_list": [x for x in t.get("interventions", []) if x],
        "brief_summary": t.get("summary", ""),
        "inclusion_criteria": inc,
        "exclusion_criteria": exc,
    }


def _format_trials(trials: list[dict], limit: int = 8) -> str:
    if not trials:
        return "_No trials found._"
    lines = []
    for i, t in enumerate(trials[:limit], 1):
        conds = ", ".join(t.get("conditions", []))
        intr = ", ".join(x for x in t.get("interventions", []) if x)
        nctid = t.get("nctId", "")
        link = f"[{nctid}](https://clinicaltrials.gov/study/{nctid})" if nctid else "(no NCT)"
        lines.append(f"{i}. {link} — **{t.get('title','')}**")
        meta = []
        if t.get("status"):
            meta.append(f"status: {t['status']}")
        if conds:
            meta.append(f"conditions: {conds}")
        if intr:
            meta.append(f"interventions: {intr}")
        if meta:
            lines.append("   - " + " · ".join(meta))
    return "\n".join(lines)


def _observation(trials: list[dict]) -> str:
    """Compact, model-facing observation of a search result."""
    if not trials:
        return "0 trials found."
    head = "; ".join(
        f"{t.get('nctId','')}: {t.get('title','')[:80]}" for t in trials[:5]
    )
    return f"{len(trials)} trial(s). Top: {head}"


# ---------------------------------------------------------------------------
# Retriever (ReAct)
# ---------------------------------------------------------------------------
_SYSTEM = (
    "You are a ClinicalTrials.gov search agent using a ReAct strategy. "
    "At each step output STRICT JSON for ONE action:\n"
    '  {"thought": "...", "action": "search_trials", "args": {"term": "...", '
    '"condition": "...", "intervention": "...", "status": "RECRUITING"}}\n'
    "or, when you have enough good candidates:\n"
    '  {"thought": "...", "action": "finish", "nctids": ["NCT...", "NCT..."]}\n'
    "Rules: keep `term` concise (key conditions + biomarkers + line of therapy). "
    "Use `status` only if the user implies recruiting/active. Refine the query if a "
    "search returns too few or irrelevant trials. Output JSON only, no prose."
)


class CTGRetriever:
    def __init__(self, mock: bool, model: str, max_steps: int = 4, page_size: int = 5):
        self.mock = mock
        self.model = model
        self.max_steps = max_steps
        self.page_size = page_size
        self._client = None
        # Structured candidates from the last run, in TrialGPT trial format, so
        # downstream matching/ranking can consume the CTG search results.
        self.candidates: list[dict] = []

    # -- LLM ----------------------------------------------------------------
    def _chat(self, messages: list[dict]) -> str:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        resp = self._client.chat.completions.create(model=self.model, messages=messages)
        return (resp.choices[0].message.content or "").strip()

    @staticmethod
    def _parse_action(text: str) -> dict | None:
        cleaned = (text or "").strip().strip("`")
        cleaned = re.sub(r"^json", "", cleaned, flags=re.IGNORECASE).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    # -- public -------------------------------------------------------------
    def run(self, query: str, extra_context: str = "") -> str:
        """Run the ReAct search and return a Markdown trace + final results."""
        if self.mock or not query.strip():
            return self._run_keyword(query)
        try:
            return self._run_react(query, extra_context)
        except Exception as exc:  # noqa: BLE001
            log.warning("CTG ReAct failed (%s); falling back to keyword search", exc)
            return self._run_keyword(query)

    # -- ReAct loop ---------------------------------------------------------
    def _run_react(self, query: str, extra_context: str) -> str:
        """Drive the search with a ReAct loop, but return ONLY the final results.

        The Thought/Action/Observation trace is logged to the terminal; the UI
        output is just the retrieved trials.
        """
        seen: dict[str, dict] = {}

        user_intro = f"User request:\n{query}"
        if extra_context.strip():
            user_intro += f"\n\nShared context from other tools:\n{extra_context}"
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_intro + "\n\nBegin. Output the first action as JSON."},
        ]

        final_ids: list[str] = []
        for step in range(1, self.max_steps + 1):
            raw = self._chat(messages)
            action = self._parse_action(raw)
            if not action:
                log.info("  CTG ReAct step %d: unparseable action; stopping", step)
                break

            thought = str(action.get("thought", "")).strip()
            act = str(action.get("action", "")).strip()

            if act == "finish":
                final_ids = [str(x).strip() for x in action.get("nctids", []) if str(x).strip()]
                log.info("  CTG ReAct step %d: finish | thought=%s", step, thought)
                break

            if act != "search_trials":
                log.info("  CTG ReAct step %d: unknown action %r; stopping", step, act)
                break

            args = action.get("args", {}) if isinstance(action.get("args"), dict) else {}
            term = str(args.get("term", "")) or query
            trials = search_trials(
                term=term,
                condition=str(args.get("condition", "")),
                intervention=str(args.get("intervention", "")),
                status=str(args.get("status", "")),
                page_size=self.page_size,
            )
            for t in trials:
                if t["nctId"]:
                    seen[t["nctId"]] = t

            obs = _observation(trials)
            log.info("  CTG ReAct step %d: term=%r -> %s", step, term, obs)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Observation: {obs}\n\nNext action as JSON."})

        # Choose final trials: explicit finish list if given, else everything seen.
        if final_ids:
            final = [seen[n] for n in final_ids if n in seen] or list(seen.values())
        else:
            final = list(seen.values())

        self.candidates = [to_trialgpt_trial(t) for t in final]
        return "## Retrieved trials (ClinicalTrials.gov)\n\n" + _format_trials(final)

    # -- mock / fallback ----------------------------------------------------
    def _run_keyword(self, query: str) -> str:
        """No-LLM path: keyword search with progressive relaxation.

        A full keyword term often over-constrains CTG's search and returns
        nothing, so we retry with progressively fewer (higher-priority) terms.
        A "recruiting/active" hint is moved to the status filter.
        """
        status = ""
        low = (query or "").lower()
        if "recruit" in low or "모집" in low:
            status = "RECRUITING"

        keywords = [k for k in _keywords(query).split() if k != "recruiting"]
        # Try the full set first, then relax to the top 4 and top 2 terms.
        candidates_terms: list[str] = []
        for n in (len(keywords), 4, 2):
            term = " ".join(keywords[:n]).strip()
            if term and term not in candidates_terms:
                candidates_terms.append(term)
        if not candidates_terms:
            candidates_terms = [query.strip()]

        attempts: list[str] = []
        trials: list[dict] = []
        used_term = candidates_terms[-1]
        try:
            for term in candidates_terms:
                attempts.append(term)
                trials = search_trials(term=term, status=status, page_size=self.page_size)
                used_term = term
                if trials:
                    break
        except Exception as exc:  # noqa: BLE001
            log.warning("CTG keyword search failed: %s", exc)
            return ("## Retrieved trials (ClinicalTrials.gov)\n\n"
                    f"_ClinicalTrials.gov request failed: {exc}_")

        log.info("  CTG keyword search: term=%r status=%r (%d attempt(s)) -> %d trial(s)",
                 used_term, status, len(attempts), len(trials))
        self.candidates = [to_trialgpt_trial(t) for t in trials]
        return "## Retrieved trials (ClinicalTrials.gov)\n\n" + _format_trials(trials)


_STOP = {
    "the", "and", "with", "for", "from", "that", "this", "find", "search", "trial",
    "trials", "clinical", "study", "studies", "patient", "patients", "please",
    # Platform / noise words that should never become search terms.
    "clinicaltrials", "gov", "clinicaltrials.gov", "ctg", "registry", "database",
    "website", "api", "online", "list", "show", "give", "want", "need", "looking",
    # Task/verb words from the request that aren't medical search terms.
    "matching", "match", "rank", "ranking", "eligibility", "check", "them", "they",
    "candidate", "candidates", "retrieve", "retrieval", "line",
}


def _keywords(text: str, limit: int = 10) -> str:
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", (text or "").lower())
    out: list[str] = []
    seen: set[str] = set()
    for t in toks:
        if t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return " ".join(out)
