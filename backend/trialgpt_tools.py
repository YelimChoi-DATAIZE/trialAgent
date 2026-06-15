"""TrialGPT pipeline adapter.

Wraps the bundled TrialGPT modules (retrieval / matching / ranking) into a
small, dependency-light pipeline that the agent server can call the same way
it calls the clinical-protocol-review agents.

The original TrialGPT code under ``tool_registry/TrialGPT`` is hard-wired to
``AzureOpenAI`` and the BEIR/NLTK research stack. To make the tools actually
runnable from this app (which is configured with a standard ``OPENAI_API_KEY``
and ``gpt-5.1``), we re-implement the prompt building here and call the
standard OpenAI client. A mock mode mirrors the protocol tools so the pipeline
also works without any API key.
"""

from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger("agent_server.trialgpt")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
TRIALGPT_DIR = os.path.join(BACKEND_DIR, "tool_registry", "TrialGPT")
# Bundled candidate pool (patients + pre-retrieved trials) used as a stand-in
# for a live ClinicalTrials.gov search.
DEFAULT_POOL_PATH = os.path.join(TRIALGPT_DIR, "dataset", "sigir", "retrieved_trials.json")

# How many candidate trials to carry through matching/ranking (cost control).
MAX_TRIALS = int(os.getenv("TRIALGPT_MAX_TRIALS", "3"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ctg_link(nctid: str) -> str:
    """Markdown link to the trial's ClinicalTrials.gov page."""
    nctid = (nctid or "").strip()
    return f"[{nctid}](https://clinicaltrials.gov/study/{nctid})" if nctid else "(no NCT)"


def _parse_json(text: str):
    """Best-effort JSON extraction from an LLM response."""
    cleaned = text.strip().strip("`")
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"[\{\[].*[\}\]]", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None


def _split_sentences(note: str) -> str:
    """Number the sentences of a patient note (mirrors run_matching)."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", note.strip()) if s.strip()]
    parts.append(
        "The patient will provide informed consent, and will comply with the "
        "trial protocol without any practical issues."
    )
    return "\n".join(f"{i}. {s}" for i, s in enumerate(parts))


# ---------------------------------------------------------------------------
# Prompt builders (faithful to tool_registry/TrialGPT/*/TrialGPT.py)
# ---------------------------------------------------------------------------
def _parse_criteria(criteria: str) -> str:
    output = ""
    idx = 0
    for criterion in (criteria or "").split("\n\n"):
        criterion = criterion.strip()
        if "inclusion criteria" in criterion.lower() or "exclusion criteria" in criterion.lower():
            continue
        if len(criterion) < 5:
            continue
        output += f"{idx}. {criterion}\n"
        idx += 1
    return output


def _print_trial(trial: dict, inc_exc: str) -> str:
    text = f"Title: {trial.get('brief_title', '')}\n"
    text += f"Target diseases: {', '.join(trial.get('diseases_list', []))}\n"
    text += f"Interventions: {', '.join(trial.get('drugs_list', []))}\n"
    text += f"Summary: {trial.get('brief_summary', '')}\n"
    if inc_exc == "inclusion":
        text += "Inclusion criteria:\n %s\n" % _parse_criteria(trial.get("inclusion_criteria", ""))
    elif inc_exc == "exclusion":
        text += "Exclusion criteria:\n %s\n" % _parse_criteria(trial.get("exclusion_criteria", ""))
    return text


def _matching_prompt(trial: dict, inc_exc: str, patient: str):
    system = (
        "You are a helpful assistant for clinical trial recruitment. Your task is "
        f"to compare a given patient note and the {inc_exc} criteria of a clinical "
        "trial to determine the patient's eligibility at the criterion level.\n"
    )
    system += (
        f"You should check the {inc_exc} criteria one-by-one and, for each criterion, "
        "reason briefly, list any relevant patient sentence IDs, and classify the "
        "eligibility.\n"
    )
    if inc_exc == "inclusion":
        system += (
            'The eligibility label must be chosen from {"not applicable", "not enough '
            'information", "included", "not included"}.\n'
        )
    else:
        system += (
            'The eligibility label must be chosen from {"not applicable", "not enough '
            'information", "excluded", "not excluded"}.\n'
        )
    system += (
        "Output only a JSON dict formatted as: "
        "dict{str(criterion_number): [str(brief_reasoning), list[int(sentence_id)], "
        "str(eligibility_label)]}."
    )
    user = f"Here is the patient note, each sentence is led by a sentence_id:\n{patient}\n\n"
    user += f"Here is the clinical trial:\n{_print_trial(trial, inc_exc)}\n\n"
    user += "Plain JSON output:"
    return system, user


def _criteria_pred_to_string(prediction: dict, trial: dict) -> str:
    output = ""
    for inc_exc in ["inclusion", "exclusion"]:
        idx2criterion = {}
        idx = 0
        for criterion in (trial.get(inc_exc + "_criteria", "") or "").split("\n\n"):
            criterion = criterion.strip()
            if "inclusion criteria" in criterion.lower() or "exclusion criteria" in criterion.lower():
                continue
            if len(criterion) < 5:
                continue
            idx2criterion[str(idx)] = criterion
            idx += 1
        preds = prediction.get(inc_exc, {})
        if not isinstance(preds, dict):
            continue
        for i, (criterion_idx, info) in enumerate(preds.items()):
            if criterion_idx not in idx2criterion or not isinstance(info, list) or len(info) != 3:
                continue
            output += f"{inc_exc} criterion {i}: {idx2criterion[criterion_idx]}\n"
            output += f"\tPatient relevance: {info[0]}\n"
            if info[1]:
                output += f"\tEvident sentences: {info[1]}\n"
            output += f"\tPatient eligibility: {info[2]}\n"
    return output


def _aggregation_prompt(patient: str, pred: dict, trial: dict):
    trial_str = f"Title: {trial.get('brief_title', '')}\n"
    trial_str += f"Target conditions: {', '.join(trial.get('diseases_list', []))}\n"
    trial_str += f"Summary: {trial.get('brief_summary', '')}"
    pred_str = _criteria_pred_to_string(pred, trial)
    system = (
        "You are a helpful assistant for clinical trial recruitment. You will be given "
        "a patient note, a clinical trial, and the patient eligibility predictions for "
        "each criterion.\n"
        "Your task is to output two scores, a relevance score (R) and an eligibility "
        "score (E), between the patient and the clinical trial.\n"
        "Predict the relevance score R (0~100). Then predict the eligibility score E "
        "(-R~R).\n"
        'Output a JSON dict formatted as {"relevance_explanation": Str, '
        '"relevance_score_R": Float, "eligibility_explanation": Str, '
        '"eligibility_score_E": Float}.'
    )
    user = "Here is the patient note:\n" + patient + "\n\n"
    user += "Here is the clinical trial description:\n" + trial_str + "\n\n"
    user += "Here are the criterion-level eligibility prediction:\n" + pred_str + "\n\n"
    user += "Plain JSON output:"
    return system, user


def _keyword_messages(note: str):
    system = (
        "You are a helpful assistant and your task is to help search relevant clinical "
        "trials for a given patient description. First summarize the main medical "
        "problems of the patient. Then generate up to 32 key conditions for searching "
        "relevant clinical trials, ranked by priority. Output only a JSON dict formatted "
        'as {"summary": Str, "conditions": List[Str]}.'
    )
    user = f"Here is the patient description:\n{note}\n\nJSON output:"
    return system, user


# ---------------------------------------------------------------------------
# Scoring (faithful to trialgpt_ranking/rank_results.py)
# ---------------------------------------------------------------------------
_EPS = 1e-9


def matching_score(matching: dict) -> float:
    included = not_inc = no_info_inc = excluded = 0
    for _, info in (matching.get("inclusion", {}) or {}).items():
        if not isinstance(info, list) or len(info) != 3:
            continue
        if info[2] == "included":
            included += 1
        elif info[2] == "not included":
            not_inc += 1
        elif info[2] == "not enough information":
            no_info_inc += 1
    for _, info in (matching.get("exclusion", {}) or {}).items():
        if not isinstance(info, list) or len(info) != 3:
            continue
        if info[2] == "excluded":
            excluded += 1
    score = included / (included + not_inc + no_info_inc + _EPS)
    if not_inc > 0:
        score -= 1
    if excluded > 0:
        score -= 1
    return score


def agg_score(assessment: dict) -> float:
    try:
        rel = float(assessment["relevance_score_R"])
        eli = float(assessment["eligibility_score_E"])
    except Exception:
        rel = eli = 0.0
    return (rel + eli) / 100


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
class TrialGPTPipeline:
    def __init__(self, mock: bool, model: str):
        self.mock = mock
        self.model = model
        self._client = None
        self._pool: list[dict] | None = None

    # -- LLM ----------------------------------------------------------------
    def _chat(self, system: str, user: str) -> str:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    # -- candidate pool -----------------------------------------------------
    def _load_pool(self) -> list[dict]:
        if self._pool is not None:
            return self._pool
        trials: dict[str, dict] = {}
        try:
            with open(DEFAULT_POOL_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for instance in data:
                for label in ("2", "1", "0"):
                    for trial in instance.get(label, []):
                        nctid = trial.get("NCTID")
                        if nctid and nctid not in trials:
                            trials[nctid] = trial
        except Exception as exc:  # noqa: BLE001
            log.warning("TrialGPT pool load failed (%s); using empty pool", exc)
        self._pool = list(trials.values())
        return self._pool

    @staticmethod
    def _trial_text(trial: dict) -> str:
        return " ".join([
            trial.get("brief_title", ""),
            " ".join(trial.get("diseases_list", [])),
            " ".join(trial.get("drugs_list", [])),
            trial.get("brief_summary", ""),
        ]).lower()

    # -- retrieval ----------------------------------------------------------
    def generate_keywords(self, note: str) -> dict:
        if self.mock:
            words = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", note)
            seen, conditions = set(), []
            for w in words:
                lw = w.lower()
                if lw not in seen:
                    seen.add(lw)
                    conditions.append(w)
                if len(conditions) >= 8:
                    break
            return {"summary": note[:160], "conditions": conditions or [note[:40]]}
        system, user = _keyword_messages(note)
        parsed = _parse_json(self._chat(system, user)) or {}
        if not isinstance(parsed, dict):
            parsed = {}
        parsed.setdefault("summary", note[:160])
        parsed.setdefault("conditions", [])
        return parsed

    def retrieve(self, note: str, k: int = 5):
        keywords = self.generate_keywords(note)
        query_terms = set()
        for cond in keywords.get("conditions", []):
            for tok in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", str(cond).lower()):
                query_terms.add(tok)
        for tok in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", note.lower()):
            query_terms.add(tok)

        scored = []
        for trial in self._load_pool():
            text = self._trial_text(trial)
            hits = sum(1 for t in query_terms if t in text)
            scored.append((hits, trial))
        scored.sort(key=lambda x: -x[0])
        candidates = [t for hits, t in scored[:k] if hits > 0] or [t for _, t in scored[:k]]
        return keywords, candidates

    # -- matching -----------------------------------------------------------
    def match(self, patient_fmt: str, trial: dict) -> dict:
        if self.mock:
            return {
                "inclusion": {"0": ["[MOCK] inferred from note", [0], "included"]},
                "exclusion": {"0": ["[MOCK] no evidence", [], "not excluded"]},
            }
        results = {}
        for inc_exc in ("inclusion", "exclusion"):
            system, user = _matching_prompt(trial, inc_exc, patient_fmt)
            parsed = _parse_json(self._chat(system, user))
            results[inc_exc] = parsed if isinstance(parsed, dict) else {}
        return results

    # -- ranking ------------------------------------------------------------
    def aggregate(self, patient_fmt: str, preds: dict, trial: dict) -> dict:
        if self.mock:
            return {
                "relevance_explanation": "[MOCK] relevance estimate",
                "relevance_score_R": 70.0,
                "eligibility_explanation": "[MOCK] eligibility estimate",
                "eligibility_score_E": 35.0,
            }
        system, user = _aggregation_prompt(patient_fmt, preds, trial)
        parsed = _parse_json(self._chat(system, user))
        return parsed if isinstance(parsed, dict) else {}

    # -- orchestration ------------------------------------------------------
    def iter_pipeline(self, note: str, want_retrieval: bool,
                      want_matching: bool, want_ranking: bool,
                      extra_context: str = "",
                      external_candidates: list[dict] | None = None):
        """Yield per-tool result dicts as each step finishes (progressive).

        Each dict is ``{key, status, output}`` where ``key`` is the TOOL_REGISTRY
        key. Prerequisite steps run automatically (matching/ranking need
        candidate trials; ranking needs matching predictions).

        ``extra_context`` is shared-memory context retrieved by the reasoning
        step; it is folded into trial *retrieval* (to steer keyword/candidate
        search) but kept out of the patient note used for criterion matching so
        the matcher still reasons over the patient only.

        ``external_candidates`` lets an upstream tool (e.g. the live CTG
        retriever) supply the trials to score; when provided, matching/ranking
        run on these instead of the bundled local dataset.
        """
        patient_fmt = _split_sentences(note)
        candidates: list[dict] = []
        keywords: dict = {}

        # Augment only the retrieval query with shared context.
        retrieval_input = note
        if extra_context.strip():
            retrieval_input = f"{note}\n\n[Shared context from other tools]\n{extra_context}"

        need_candidates = want_retrieval or want_matching or want_ranking
        if external_candidates:
            # Use the trials handed in by an upstream retriever (e.g. CTG).
            candidates = external_candidates[:MAX_TRIALS]
            keywords = {"summary": "Candidates supplied by ClinicalTrials.gov retrieval."}
        elif need_candidates:
            keywords, candidates = self.retrieve(retrieval_input, k=5)
            candidates = candidates[:MAX_TRIALS]

        if want_retrieval:
            yield {
                "key": "TrialGPT Retrieval",
                "status": "ok",
                "output": self._fmt_retrieval(keywords, candidates),
            }

        matches: dict[str, dict] = {}
        if (want_matching or want_ranking) and candidates:
            for trial in candidates:
                matches[trial["NCTID"]] = self.match(patient_fmt, trial)

        if want_matching:
            if candidates:
                yield {
                    "key": "TrialGPT Matching",
                    "status": "ok",
                    "output": self._fmt_matching(candidates, matches),
                }
            else:
                yield {
                    "key": "TrialGPT Matching",
                    "status": "skipped",
                    "output": "후보 임상시험을 찾지 못했습니다.",
                }

        if want_ranking:
            if candidates:
                ranked = []
                for trial in candidates:
                    nctid = trial["NCTID"]
                    preds = matches.get(nctid, {})
                    assessment = self.aggregate(patient_fmt, preds, trial)
                    total = matching_score(preds) + agg_score(assessment)
                    ranked.append((total, trial, assessment))
                ranked.sort(key=lambda x: -x[0])
                yield {
                    "key": "TrialGPT Ranking",
                    "status": "ok",
                    "output": self._fmt_ranking(ranked),
                }
            else:
                yield {
                    "key": "TrialGPT Ranking",
                    "status": "skipped",
                    "output": "후보 임상시험을 찾지 못했습니다.",
                }

    def run_pipeline(self, note: str, want_retrieval: bool,
                     want_matching: bool, want_ranking: bool,
                     extra_context: str = "",
                     external_candidates: list[dict] | None = None) -> list[dict]:
        return list(self.iter_pipeline(note, want_retrieval, want_matching,
                                       want_ranking, extra_context, external_candidates))

    # -- output formatting --------------------------------------------------
    # Markdown conventions here mirror the clinical-protocol-review agents
    # (agents/_md_style.py): `## ` top-level headings, `### ` sub-sections,
    # `-` bullets, `**bold**` emphasis, and `` `code` `` for identifiers.
    @staticmethod
    def _fmt_retrieval(keywords: dict, candidates: list[dict]) -> str:
        lines = []
        if keywords.get("summary"):
            lines.append("## 1. Patient Summary")
            lines.append(str(keywords["summary"]))
            lines.append("")
        conds = keywords.get("conditions") or []
        if conds:
            lines.append("## 2. Key Conditions")
            for c in conds[:12]:
                lines.append(f"- `{c}`")
            lines.append("")
        lines.append("## 3. Retrieved Trials")
        lines.append(f"Retrieved **{len(candidates)}** candidate trial(s).")
        lines.append("")
        for i, t in enumerate(candidates, 1):
            diseases = ", ".join(t.get("diseases_list", []))
            line = f"{i}. {_ctg_link(t.get('NCTID', ''))} — **{t.get('brief_title', '')}**"
            lines.append(line)
            if diseases:
                lines.append(f"   - Target conditions: {diseases}")
        return "\n".join(lines).rstrip()

    @staticmethod
    def _fmt_matching(candidates: list[dict], matches: dict[str, dict]) -> str:
        lines = ["## 1. Criterion-Level Matching", ""]
        for t in candidates:
            nctid = t.get("NCTID", "")
            preds = matches.get(nctid, {})
            inc = preds.get("inclusion", {}) if isinstance(preds, dict) else {}
            exc = preds.get("exclusion", {}) if isinstance(preds, dict) else {}
            inc_ok = sum(1 for v in inc.values() if isinstance(v, list) and len(v) == 3 and v[2] == "included")
            exc_hit = sum(1 for v in exc.values() if isinstance(v, list) and len(v) == 3 and v[2] == "excluded")
            lines.append(f"### {_ctg_link(nctid)} — {t.get('brief_title', '')}")
            lines.append(f"- **Inclusion met:** {inc_ok}/{len(inc)}")
            lines.append(f"- **Exclusion triggered:** {exc_hit}/{len(exc)}")
            lines.append("")
        return "\n".join(lines).rstrip()

    @staticmethod
    def _fmt_ranking(ranked: list[tuple]) -> str:
        lines = ["## 1. Ranked Candidate Trials", "Higher score = better fit.", ""]
        for rank, (score, trial, assessment) in enumerate(ranked, 1):
            r = assessment.get("relevance_score_R", "?")
            e = assessment.get("eligibility_score_E", "?")
            lines.append(f"{rank}. {_ctg_link(trial.get('NCTID', ''))} — **{trial.get('brief_title', '')}**")
            lines.append(f"   - Score: `{score:.2f}` (R = {r}, E = {e})")
        return "\n".join(lines).rstrip()
