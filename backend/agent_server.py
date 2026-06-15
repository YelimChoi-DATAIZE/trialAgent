"""DATAIZEAI - Trial Agent backend server.

A small FastAPI service that exposes the clinical-protocol-review agents as
tools the PyQt frontend can call.

Architecture
------------
- Tool registry  : maps a frontend tool key -> ToolSpec (label / kind / supported)
- Executor       : builds the input context, resolves dependencies
                   (a reviewer needs a protocol, so the generator runs first),
                   then invokes the matching agent.
- HTTP router    : the endpoints the frontend talks to (/tools, /agent/run).

Run (inside the project venv)::

    ./venv/bin/python -m uvicorn backend.agent_server:app --reload --port 8000
    # or simply
    ./venv/bin/python backend/agent_server.py

Environment
-----------
- OPENAI_API_KEY : required for real LLM calls.
- AGENT_MOCK=1   : force mock responses (no LLM / no network), useful for
                   developing and testing the UI wiring end-to-end.

If langchain/OpenAI are unavailable or no API key is set, the server
automatically falls back to mock responses so the frontend keeps working.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent_server")

try:  # optional, only used to load a local .env during development
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
CPR_DIR = os.path.join(BACKEND_DIR, "tool_registry", "clinical-protocol-review")
ICH_TEMPLATE_PATH = os.path.join(CPR_DIR, "templates", "ich_templates", "ich_template_v1.md")

# LLM model used by all protocol-review agents (override with AGENT_MODEL).
AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-5.1")

# The protocol-review agents import each other as top-level packages
# (`from agents...`, `from mcp_interface...`), so the package root must be
# importable.
if CPR_DIR not in sys.path:
    sys.path.insert(0, CPR_DIR)
# Make the backend package root importable for `util` / `trialgpt_tools`
# regardless of how the server is launched.
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
# `ctg_retriever` lives under tool_registry/.
TOOL_REGISTRY_DIR = os.path.join(BACKEND_DIR, "tool_registry")
if TOOL_REGISTRY_DIR not in sys.path:
    sys.path.insert(0, TOOL_REGISTRY_DIR)

from util import EmbeddingProvider, VectorMemory, reason_before_tool  # noqa: E402

# How many shared-memory snippets each reasoning step retrieves.
MEMORY_TOP_K = int(os.getenv("AGENT_MEMORY_TOP_K", "4"))


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
Kind = Literal["generator", "reviewer", "retriever", "matcher", "ranker", "ctg", "other"]


@dataclass(frozen=True)
class ToolSpec:
    key: str          # must match the frontend tool key exactly
    label: str        # human-friendly name
    kind: Kind
    supported: bool    # whether the server can actually execute it


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "Protocol Generator": ToolSpec(
        "Protocol Generator", "Protocol Drafting", "generator", True
    ),
    "Health Authority": ToolSpec(
        "Health Authority", "Regulatory Review", "reviewer", True
    ),
    "PI": ToolSpec("PI", "Scientific & PI Review", "reviewer", True),
    "Site Physician": ToolSpec(
        "Site Physician", "Site Feasibility Review", "reviewer", True
    ),
    # TrialGPT patient-to-trial pipeline.
    "TrialGPT Retrieval": ToolSpec("TrialGPT Retrieval", "TrialGPT Retrieval", "retriever", True),
    "TrialGPT Matching": ToolSpec("TrialGPT Matching", "TrialGPT Matching", "matcher", True),
    "TrialGPT Ranking": ToolSpec("TrialGPT Ranking", "TrialGPT Ranking", "ranker", True),
    # Live ClinicalTrials.gov search via a ReAct loop.
    "CTG Retrieval": ToolSpec("CTG Retrieval", "ClinicalTrials.gov Retrieval", "ctg", True),
}

# reviewer key -> (module, class) for lazy import
REVIEWER_AGENTS = {
    "Health Authority": ("agents.health_authority_agent", "HealthAuthorityAgent"),
    "PI": ("agents.pi_agent", "PIAgent"),
    "Site Physician": ("agents.site_physician_agent", "SitePhysicianAgent"),
}


# ---------------------------------------------------------------------------
# Tool preconditions (explicit dependencies)
# ---------------------------------------------------------------------------
# Each tool maps to a list of prerequisite "groups". A group is a tuple of tool
# keys, and AT LEAST ONE tool in each group must run before this tool. Groups
# are AND-ed together (every group must be satisfied), tools within a group are
# OR-ed (any one satisfies it). When a prerequisite is missing it is added
# automatically using the first (default) option of the group.
#
#   - Reviewers (Health Authority / PI / Site Physician) need a protocol, which
#     is produced by the Protocol Generator (or already supplied in the request).
#   - TrialGPT Matching / Ranking need candidate trials from a retriever, which
#     is either the TrialGPT Retrieval or the live CTG Retrieval tool.
TOOL_PREREQUISITES: dict[str, list[tuple[str, ...]]] = {
    "Health Authority": [("Protocol Generator",)],
    "PI": [("Protocol Generator",)],
    "Site Physician": [("Protocol Generator",)],
    "TrialGPT Matching": [("TrialGPT Retrieval", "CTG Retrieval")],
    "TrialGPT Ranking": [("TrialGPT Retrieval", "CTG Retrieval")],
}


def expand_prerequisites(selected: list[str], has_protocol: bool = False) -> list[str]:
    """Auto-add missing prerequisites for the selected tools.

    A reviewer pulls in the Protocol Generator (unless a protocol already
    exists), and TrialGPT Matching/Ranking pull in a retriever (TrialGPT
    Retrieval by default) when none is selected. Returns the expanded list in
    TOOL_REGISTRY order so generation/retrieval run before their dependents.
    """
    result = list(selected)
    changed = True
    while changed:
        changed = False
        for tool in list(result):
            for group in TOOL_PREREQUISITES.get(tool, []):
                # Already satisfied by a selected tool in this group?
                if any(option in result for option in group):
                    continue
                # A protocol already in context satisfies the generator prereq.
                if group == ("Protocol Generator",) and has_protocol:
                    continue
                result.append(group[0])  # add the default option
                log.info("  prerequisite: %s requires %s -> auto-added %s",
                         tool, " or ".join(group), group[0])
                changed = True
    return [k for k in TOOL_REGISTRY if k in result]


# ---------------------------------------------------------------------------
# Auto tool routing
# ---------------------------------------------------------------------------
# Keyword hints (lower-cased, Korean + English) used to pick tools from the
# free-form prompt when the caller does not select any tool explicitly.
ROUTING_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Protocol Generator": (
        "프로토콜 생성", "프로토콜 작성", "프로토콜 초안", "초안", "작성", "설계", "디자인",
        "generate", "draft", "design", "create protocol", "write protocol",
    ),
    "Health Authority": (
        "규제", "당국", "허가", "승인", "ich", "gcp", "fda", "ema", "mfds", "식약처",
        "데이터 무결성", "compliance", "regulatory", "health authority",
    ),
    "PI": (
        "pi", "연구자", "책임자", "과학적", "타당성", "환자 모집", "모집", "안전성",
        "principal investigator", "investigator", "scientific", "feasibility",
    ),
    "Site Physician": (
        "현장", "사이트", "기관", "운영", "실행 가능", "환자 부담", "로지스틱", "동선",
        "site", "physician", "operational", "logistic", "burden",
    ),
    "TrialGPT Retrieval": (
        "후보 시험 검색", "시험 검색", "임상시험 검색", "retrieval", "검색",
    ),
    "TrialGPT Matching": (
        "매칭", "적격", "적격성", "eligibility", "matching", "환자 적합",
    ),
    "TrialGPT Ranking": (
        "랭킹", "순위", "우선순위", "ranking", "rank",
    ),
    "CTG Retrieval": (
        "clinicaltrials.gov", "ctg", "공개 임상", "등록 정보", "registry",
    ),
}

# A generic "review my protocol" request maps to every reviewer.
REVIEW_TRIGGERS: tuple[str, ...] = (
    "검토", "리뷰", "평가", "점검", "피드백", "review", "evaluate", "assess", "critique",
)

# Used when nothing matches but a prompt is present: the core supported flow.
DEFAULT_ROUTE: list[str] = ["Protocol Generator", "Health Authority", "PI", "Site Physician"]

# Short, router-facing descriptions of what each tool is for. Shown to the LLM
# planner so it can pick the right tools from a free-form request.
ROUTING_DESCRIPTIONS: dict[str, str] = {
    "Protocol Generator": "Draft a brand-new clinical trial protocol from the request.",
    "Health Authority": "Regulatory/compliance review (ICH-GCP, FDA, EMA), ethics, data integrity, safety reporting.",
    "PI": "Principal Investigator review: scientific soundness, feasibility, recruitment, endpoints, bias.",
    "Site Physician": "Site-level operational review: patient burden, visit schedule, dosing, logistics, resources.",
    "TrialGPT Retrieval": "Search candidate clinical trials for a given patient description.",
    "TrialGPT Matching": "Check a patient's eligibility against trial inclusion/exclusion criteria.",
    "TrialGPT Ranking": "Rank candidate trials by relevance/eligibility for the patient.",
    "CTG Retrieval": "Search the LIVE ClinicalTrials.gov website/API for real trials matching a free-text query (use when the user wants up-to-date or real registry results).",
}


def _parse_tool_list(text: str, valid: set[str]) -> list[str]:
    """Parse an LLM routing reply into ordered, validated tool keys."""
    import re

    cleaned = (text or "").strip().strip("`")
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    raw = match.group(0) if match else cleaned
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("tools", [])
    if not isinstance(data, list):
        return []
    picked = {str(x).strip() for x in data}
    # Preserve registry order so generation precedes review, etc.
    return [k for k in TOOL_REGISTRY if k in picked and k in valid]


def auto_route(prompt: str) -> list[str]:
    """Infer which tools to run from a free-form prompt.

    Order follows TOOL_REGISTRY so generation precedes review. Returns an
    empty list only when the prompt itself is empty.
    """
    text = (prompt or "").lower()
    if not text.strip():
        return []

    matched: list[str] = []
    for key in TOOL_REGISTRY:
        hints = ROUTING_KEYWORDS.get(key, ())
        if any(h.lower() in text for h in hints):
            matched.append(key)

    # "검토/review" with no specific reviewer -> run all reviewers.
    if any(t in text for t in REVIEW_TRIGGERS):
        for key, spec in TOOL_REGISTRY.items():
            if spec.kind == "reviewer" and key not in matched:
                matched.append(key)

    if not matched:
        return list(DEFAULT_ROUTE)

    # Preserve registry order for stable generation-before-review execution.
    return [k for k in TOOL_REGISTRY if k in matched]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    prompt: str = ""
    tools: list[str] = []
    # When provided, applied to the process env so the real models are used
    # for this run (instead of mock mode).
    openai_api_key: str | None = None
    # Optional structured inputs for the generator. When omitted they are
    # synthesized from `prompt`.
    study_title: str | None = None
    indication: str | None = None
    objectives: str | None = None
    # When the user already has a protocol, reviewers use it directly and the
    # generator step is skipped.
    protocol_content: str | None = None


class ToolResult(BaseModel):
    tool: str
    label: str
    kind: Kind
    status: Literal["ok", "error", "skipped"]
    output: str
    reasoning: str = ""


class RunResponse(BaseModel):
    mock: bool
    auto_routed: bool = False
    routed_tools: list[str] = []
    protocol_content: str | None = None
    results: list[ToolResult]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------
def _mock_enabled() -> bool:
    if os.getenv("AGENT_MOCK", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return not os.getenv("OPENAI_API_KEY")


def _mock_generate(ctx: dict) -> str:
    return (
        f"[MOCK] Generated protocol draft\n"
        f"Study Title: {ctx['study_title']}\n"
        f"Indication: {ctx['indication']}\n"
        f"Objectives: {ctx['objectives']}\n\n"
        "1. Introduction\n2. Study Objectives\n3. Study Design\n"
        "4. Study Population\n5. Study Procedures\n6. Statistical Considerations\n"
        "7. Safety Reporting\n8. Ethical Considerations\n"
        "(Set OPENAI_API_KEY to generate a real draft.)"
    )


def _mock_review(label: str, ctx: dict) -> str:
    preview = (ctx.get("protocol_content") or "")[:80].replace("\n", " ")
    return (
        f"[MOCK] {label} review\n"
        f"Reviewed protocol starting with: \"{preview}...\"\n"
        "- Concern: this is a mock response (no LLM was called).\n"
        "- Recommendation: set OPENAI_API_KEY to get real agent feedback."
    )


class AgentExecutor:
    """Resolves tool dependencies and invokes the matching agents."""

    def __init__(self) -> None:
        self.mock = _mock_enabled()

    # -- routing ----------------------------------------------------------
    def _route(self, prompt: str) -> list[str]:
        """Pick tools for a free-form prompt: LLM planner first, keywords as fallback."""
        if not (prompt or "").strip():
            return []
        if not self.mock:
            try:
                picked = self._llm_route(prompt)
                if picked:
                    log.info("  router(llm): %s", picked)
                    return picked
                log.info("  router(llm): no tool chosen -> keyword fallback")
            except Exception:  # noqa: BLE001
                err = traceback.format_exc(limit=2)
                log.warning("  router(llm) failed, keyword fallback\n%s", err)
        else:
            log.info("  router: mock mode -> keyword routing")
        return auto_route(prompt)

    def _llm_route(self, prompt: str) -> list[str]:
        """Ask the LLM which (supported) tools are needed for this request."""
        from openai import OpenAI

        valid = {k for k, s in TOOL_REGISTRY.items() if s.supported}
        catalog = "\n".join(
            f"- {k}: {ROUTING_DESCRIPTIONS.get(k, TOOL_REGISTRY[k].label)}"
            for k in TOOL_REGISTRY if k in valid
        )
        system = (
            "You are a tool router for a clinical-trial assistant. Given the user's "
            "request, choose ONLY the tools needed to fulfill it. Do NOT add "
            "prerequisite tools: dependencies are resolved automatically (a protocol "
            "is generated before reviewers; trial retrieval runs before matching/"
            "ranking). Return ONLY a JSON array of exact tool keys (e.g. "
            '["PI", "Health Authority"]). If nothing fits, return [].'
        )
        user = f"Available tools:\n{catalog}\n\nUser request:\n{prompt}\n\nJSON array of tool keys:"
        client = OpenAI()
        resp = client.chat.completions.create(
            model=AGENT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return _parse_tool_list(resp.choices[0].message.content or "", valid)

    # -- low level agent calls -------------------------------------------
    def _generate_protocol(self, ctx: dict, context: str = "") -> str:
        if self.mock:
            return _mock_generate(ctx)
        from agents.protocol_generator import ProtocolGenerator

        generator = ProtocolGenerator(llm_model=AGENT_MODEL)
        return generator.generate_protocol_draft(
            study_title=ctx["study_title"],
            indication=ctx["indication"],
            objectives=ctx["objectives"],
            template_path=ICH_TEMPLATE_PATH,
            context=context,
        )

    def _review_protocol(self, key: str, label: str, ctx: dict, context: str = "") -> str:
        if self.mock:
            return _mock_review(label, ctx)
        from importlib import import_module
        from mcp_interface.protocol_server import ProtocolServer

        module_name, class_name = REVIEWER_AGENTS[key]
        agent_cls = getattr(import_module(module_name), class_name)
        agent = agent_cls(llm_model=AGENT_MODEL)
        server = ProtocolServer(ctx["protocol_content"])
        return agent.review_protocol(server, context=context)

    # -- orchestration ----------------------------------------------------
    def iter_events(self, req: RunRequest):
        """Yield progress events (routed → result* → done) as work happens."""
        ctx = {
            "prompt": req.prompt,
            "study_title": req.study_title or "AI-assisted Clinical Trial Protocol",
            "indication": req.indication or req.prompt or "Not specified",
            "objectives": req.objectives or req.prompt or "Not specified",
            "protocol_content": req.protocol_content,
        }

        selected = [k for k in req.tools if k in TOOL_REGISTRY]

        # No (valid) tool selected -> infer them from the prompt (LLM planner,
        # with keyword routing as a fallback).
        auto_routed = False
        if not selected:
            selected = self._route(req.prompt)
            auto_routed = bool(selected)

        # Auto-add any missing prerequisites (e.g. a reviewer pulls in the
        # Protocol Generator; matching/ranking pull in a retriever).
        if selected:
            selected = expand_prerequisites(
                selected, has_protocol=bool(ctx["protocol_content"]))

        mode = "mock" if self.mock else f"live({AGENT_MODEL})"
        log.info("▶ run | mode=%s | %s tools=%s", mode,
                 "auto-routed" if auto_routed else "selected", selected or "[]")
        run_started = time.time()

        # Shared vector memory for this run: every tool reads/writes here so
        # later tools can retrieve relevant context from earlier ones.
        memory = VectorMemory(EmbeddingProvider(self.mock))
        memory.add(req.prompt, "user", "user_message")
        if ctx["protocol_content"]:
            memory.add(ctx["protocol_content"], "user", "protocol")

        # Announce the routing decision before any work starts.
        yield {"type": "routed", "auto_routed": auto_routed, "tools": selected}

        counts = {"ok": 0, "total": 0}

        def result_event(spec: ToolSpec, status: str, output: str,
                          reasoning: str = "") -> dict:
            counts["total"] += 1
            if status == "ok":
                counts["ok"] += 1
            return {
                "type": "result", "tool": spec.key, "label": spec.label,
                "kind": spec.kind, "status": status, "output": output,
                "reasoning": reasoning,
            }

        def reasoning_for(tool_key: str, label: str):
            """Reasoning step: retrieve shared context before a tool runs."""
            return reason_before_tool(memory, tool_key, label, req.prompt, k=MEMORY_TOP_K)

        wants_generation = "Protocol Generator" in selected
        reviewers = [k for k in selected if TOOL_REGISTRY[k].kind == "reviewer"]
        need_protocol = wants_generation or bool(reviewers)

        # 1) Ensure we have protocol content (generate when needed/missing).
        if need_protocol and not ctx["protocol_content"]:
            spec = TOOL_REGISTRY["Protocol Generator"]
            reasoning = reasoning_for(spec.key, spec.label)
            try:
                log.info("  ⟳ generating protocol draft…")
                t0 = time.time()
                ctx["protocol_content"] = self._generate_protocol(ctx, reasoning.context_block)
                log.info("  ✓ protocol draft ready (%d chars, %.1fs)",
                         len(ctx["protocol_content"]), time.time() - t0)
                # Share the draft so downstream reviewers can retrieve from it.
                memory.add(ctx["protocol_content"], spec.key, "protocol")
                if wants_generation:
                    yield result_event(spec, "ok", ctx["protocol_content"], reasoning.note)
            except Exception:  # noqa: BLE001
                err = traceback.format_exc(limit=2)
                log.error("  ✗ protocol generation failed\n%s", err)
                if wants_generation:
                    yield result_event(spec, "error", f"Generation failed:\n{err}", reasoning.note)
        elif wants_generation and ctx["protocol_content"]:
            spec = TOOL_REGISTRY["Protocol Generator"]
            yield result_event(spec, "skipped", "기존 프로토콜이 제공되어 생성 단계를 건너뜀.")

        # 2) Run reviewers (one event each, as they finish).
        for key in reviewers:
            spec = TOOL_REGISTRY[key]
            if not ctx["protocol_content"]:
                yield result_event(spec, "skipped", "검토할 프로토콜 본문이 없습니다.")
                continue
            reasoning = reasoning_for(spec.key, spec.label)
            try:
                log.info("  ⟳ reviewing: %s…", spec.label)
                t0 = time.time()
                output = self._review_protocol(key, spec.label, ctx, reasoning.context_block)
                log.info("  ✓ review done: %s (%.1fs)", spec.label, time.time() - t0)
                # Share this review so later tools can build on it.
                memory.add(output, spec.key, "tool_output")
                yield result_event(spec, "ok", output, reasoning.note)
            except Exception:  # noqa: BLE001
                err = traceback.format_exc(limit=2)
                log.error("  ✗ review failed: %s\n%s", spec.label, err)
                yield result_event(spec, "error", f"Review failed:\n{err}", reasoning.note)

        # 3) Live ClinicalTrials.gov retrieval via a ReAct loop. Runs before
        #    TrialGPT so its findings land in shared memory for downstream tools.
        if "CTG Retrieval" in selected:
            spec = TOOL_REGISTRY["CTG Retrieval"]
            reasoning = reasoning_for(spec.key, spec.label)
            try:
                from ctg_retriever import CTGRetriever

                log.info("  ⟳ CTG retrieval (ReAct)…")
                t0 = time.time()
                retriever = CTGRetriever(self.mock, AGENT_MODEL)
                output = retriever.run(req.prompt, reasoning.context_block)
                # Hand the live CTG trials to TrialGPT matching/ranking.
                ctx["ctg_candidates"] = retriever.candidates
                log.info("  ✓ CTG retrieval done (%d trial(s), %.1fs)",
                         len(retriever.candidates), time.time() - t0)
                memory.add(output, spec.key, "tool_output")
                yield result_event(spec, "ok", output, reasoning.note)
            except Exception:  # noqa: BLE001
                err = traceback.format_exc(limit=2)
                log.error("  ✗ CTG retrieval failed\n%s", err)
                yield result_event(spec, "error", f"CTG retrieval failed:\n{err}", reasoning.note)

        # 4) Run the TrialGPT pipeline (one event per step, as they finish).
        tg_kinds = {"retriever", "matcher", "ranker"}
        tg_selected = [k for k in selected if TOOL_REGISTRY[k].kind in tg_kinds]
        if tg_selected:
            # One reasoning step seeds the whole TrialGPT pipeline (it shares a
            # single retrieval); steered by the first selected TrialGPT tool.
            tg_reasoning = reasoning_for(tg_selected[0], TOOL_REGISTRY[tg_selected[0]].label)
            try:
                from trialgpt_tools import TrialGPTPipeline

                pipeline = TrialGPTPipeline(self.mock, AGENT_MODEL)
                ctg_candidates = ctx.get("ctg_candidates") or None
                if ctg_candidates:
                    log.info("  ⟳ TrialGPT pipeline: %s (on %d CTG trial(s))…",
                             tg_selected, len(ctg_candidates))
                else:
                    log.info("  ⟳ TrialGPT pipeline: %s…", tg_selected)
                for step in pipeline.iter_pipeline(
                    note=req.prompt,
                    want_retrieval="TrialGPT Retrieval" in tg_selected,
                    want_matching="TrialGPT Matching" in tg_selected,
                    want_ranking="TrialGPT Ranking" in tg_selected,
                    extra_context=tg_reasoning.context_block,
                    external_candidates=ctg_candidates,
                ):
                    spec = TOOL_REGISTRY[step["key"]]
                    if step["status"] == "ok":
                        memory.add(step["output"], spec.key, "tool_output")
                    yield result_event(spec, step["status"], step["output"], tg_reasoning.note)
            except Exception:  # noqa: BLE001
                err = traceback.format_exc(limit=2)
                log.error("  ✗ TrialGPT pipeline failed\n%s", err)
                for key in tg_selected:
                    spec = TOOL_REGISTRY[key]
                    yield result_event(spec, "error", f"TrialGPT pipeline failed:\n{err}", tg_reasoning.note)

        # 5) Tools that are registered but not implemented yet.
        for key in selected:
            spec = TOOL_REGISTRY[key]
            if not spec.supported:
                log.info("  • skipped (not wired): %s", spec.label)
                yield result_event(spec, "skipped", "아직 서버에 연결되지 않은 도구입니다.")

        log.info("■ run done | %d ok / %d total | %d memory chunk(s) | %.1fs",
                 counts["ok"], counts["total"], len(memory), time.time() - run_started)
        yield {
            "type": "done", "mock": self.mock, "auto_routed": auto_routed,
            "routed_tools": selected, "ok": counts["ok"], "total": counts["total"],
            "protocol_content": ctx["protocol_content"],
            "memory_chunks": len(memory),
        }

    def run(self, req: RunRequest) -> RunResponse:
        """Non-streaming wrapper: drain iter_events into a single response."""
        results: list[ToolResult] = []
        auto_routed = False
        routed: list[str] = []
        protocol_content = None
        for ev in self.iter_events(req):
            kind = ev.get("type")
            if kind == "routed":
                auto_routed = ev.get("auto_routed", False)
                routed = ev.get("tools", [])
            elif kind == "result":
                results.append(ToolResult(
                    tool=ev["tool"], label=ev["label"], kind=ev["kind"],
                    status=ev["status"], output=ev["output"],
                    reasoning=ev.get("reasoning", ""),
                ))
            elif kind == "done":
                protocol_content = ev.get("protocol_content")
        return RunResponse(
            mock=self.mock, auto_routed=auto_routed, routed_tools=routed,
            protocol_content=protocol_content, results=results,
        )


# ---------------------------------------------------------------------------
# HTTP router (frontend connection)
# ---------------------------------------------------------------------------
app = FastAPI(title="DATAIZEAI - Trial Agent Server", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mock": _mock_enabled()}


@app.get("/tools")
def list_tools() -> dict:
    return {
        "tools": [
            {"key": s.key, "label": s.label, "kind": s.kind, "supported": s.supported}
            for s in TOOL_REGISTRY.values()
        ]
    }


def _apply_api_key(req: RunRequest) -> None:
    """Apply a request-supplied OPENAI_API_KEY to the process environment.

    OpenAI / LangChain clients read the key from the environment at
    construction time, so setting it here (before AgentExecutor is created)
    switches the run out of mock mode and into the real models.
    """
    key = (req.openai_api_key or "").strip()
    if key:
        os.environ["OPENAI_API_KEY"] = key


@app.post("/agent/run", response_model=RunResponse)
def agent_run(req: RunRequest) -> RunResponse:
    _apply_api_key(req)
    return AgentExecutor().run(req)


@app.post("/agent/run/stream")
def agent_run_stream(req: RunRequest) -> StreamingResponse:
    """Stream progress as newline-delimited JSON (routed → result* → done)."""
    _apply_api_key(req)

    def gen():
        for ev in AgentExecutor().iter_events(req):
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("AGENT_HOST", "127.0.0.1"),
        port=int(os.getenv("AGENT_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
