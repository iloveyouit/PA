"""
Super-Agent Orchestrator — Multi-agent cognitive architecture.

Implements the Triage → Engineer → Critic supervised loop with real LLM calls
via litellm, tool integration (Perplexity, Pinecone, E2B), and experience
distillation for self-improvement.

Architecture:
    1. Triage Router (fast model) — classifies request complexity and routes
    2. Engineer Agent (Sonnet) — retrieves context, drafts solution
    3. Critic Agent (validates) — sandbox-validates code, scores against standards
    4. Experience Distillation — stores successful resolutions for future recall

Usage:
    from src.orchestrator import run_orchestrator
    result = run_orchestrator("Create a highly-available Azure VPN Gateway terraform module")
"""
import os
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv

# Load env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("orchestrator")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


# ---------------------------------------------------------------------------
# Models — tiered per MEMORY.md engineering standard v2.0
# ---------------------------------------------------------------------------
class ModelTier:
    """Model routing tiers aligned with token cost optimization standards."""
    TRIAGE = os.getenv("MODEL_TRIAGE", "anthropic/claude-3-haiku-20240307")
    ENGINEER = os.getenv("MODEL_ENGINEER", "anthropic/claude-sonnet-4-20250514")
    CRITIC = os.getenv("MODEL_CRITIC", "anthropic/claude-sonnet-4-20250514")
    REASONER = os.getenv("MODEL_REASONER", "openai/o3-mini")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class Route(str, Enum):
    BASIC = "basic"
    ENGINEER = "engineer"
    REASONER = "reasoner"


@dataclass
class AgentState:
    """Tracks the full lifecycle of a request through the orchestrator."""
    query: str
    route: Optional[Route] = None
    context: dict = field(default_factory=dict)
    draft_code: Optional[str] = None
    validation_result: Optional[dict] = None
    validation_errors: list = field(default_factory=list)
    final_deliverable: Optional[str] = None
    iteration: int = 0
    max_iterations: int = 3  # Per MEMORY.md: cap retries to 3
    metadata: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LLM Call Helper
# ---------------------------------------------------------------------------
def _llm_call(
    model: str,
    messages: list[dict],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    """
    Unified LLM call via litellm. Supports Anthropic, OpenAI, OpenRouter.
    """
    try:
        import litellm

        params = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            params["response_format"] = {"type": "json_object"}

        response = litellm.completion(**params)
        return response.choices[0].message.content or ""

    except ImportError:
        logger.error("litellm not installed. Run: pip install litellm")
        raise
    except Exception as e:
        logger.error("LLM call to %s failed: %s", model, e)
        raise


# ---------------------------------------------------------------------------
# NODE 1: Triage Router
# ---------------------------------------------------------------------------
def triage_node(state: AgentState) -> AgentState:
    """
    Classifies the request and routes to the appropriate sub-agent.
    Uses a fast/cheap model for classification.
    """
    t0 = time.time()
    logger.info("🔀 [Triage] Classifying request...")

    classification_prompt = f"""Classify this IT infrastructure request into exactly one category.

REQUEST: {state.query}

Categories:
- BASIC: Simple questions, documentation lookups, explanations, no code needed
- ENGINEER: Needs code generation (Terraform, PowerShell, Ansible, scripts), runbook creation, architecture design, IaC modules
- REASONER: Complex troubleshooting, debugging, root cause analysis, multi-step reasoning about failures

Respond with ONLY the category name (BASIC, ENGINEER, or REASONER) and nothing else."""

    try:
        result = _llm_call(
            ModelTier.TRIAGE,
            [{"role": "user", "content": classification_prompt}],
            max_tokens=10,
            temperature=0.0,
        )
        route_str = result.strip().upper()

        if "ENGINEER" in route_str:
            state.route = Route.ENGINEER
        elif "REASONER" in route_str:
            state.route = Route.REASONER
        else:
            state.route = Route.BASIC

    except Exception as e:
        logger.warning("Triage LLM failed (%s), defaulting to ENGINEER", e)
        state.route = Route.ENGINEER

    state.timings["triage"] = round(time.time() - t0, 2)
    logger.info("🔀 [Triage] Route: %s (%.1fs)", state.route.value, state.timings["triage"])
    return state


# ---------------------------------------------------------------------------
# NODE 2: Context Retrieval
# ---------------------------------------------------------------------------
def context_node(state: AgentState) -> AgentState:
    """
    Retrieves relevant context from Pinecone (semantic memory) and
    Perplexity (live web research) before the Engineer drafts a solution.
    """
    t0 = time.time()
    logger.info("📚 [Context] Retrieving relevant context...")

    # --- Pinecone: Past experiences ---
    try:
        from src.tools.query_pinecone import query_memory
        memories = query_memory(state.query, top_k=3)
        if memories:
            state.context["pinecone_memories"] = [
                {"score": m["score"], "content": m["content"][:500]}
                for m in memories
            ]
            logger.info("📚 [Context] Found %d relevant memories from Pinecone", len(memories))
    except Exception as e:
        logger.warning("📚 [Context] Pinecone retrieval failed: %s", e)
        state.context["pinecone_memories"] = []

    # --- Perplexity: Live research ---
    try:
        from src.tools.search_perplexity import search_perplexity
        research = search_perplexity(state.query)
        if research.get("answer"):
            state.context["perplexity_research"] = {
                "answer": research["answer"][:1500],
                "citations": research.get("citations", [])[:5],
            }
            logger.info("📚 [Context] Got research from Perplexity (%d chars)", len(research["answer"]))
    except Exception as e:
        logger.warning("📚 [Context] Perplexity research failed: %s", e)
        state.context["perplexity_research"] = {}

    state.timings["context"] = round(time.time() - t0, 2)
    logger.info("📚 [Context] Retrieval complete (%.1fs)", state.timings["context"])
    return state


# ---------------------------------------------------------------------------
# NODE 3: Engineer Agent
# ---------------------------------------------------------------------------
ENGINEER_SYSTEM_PROMPT = """You are "The Engineer" — part of a multi-agent system serving Rob Loftin, a Senior IT Infrastructure & Cloud Consultant at 143IT (MSP).

Your standards:
- Direct, technical, structured output. No filler. No beginner explanations.
- Automation-first: idempotent, safe defaults, rollback paths, error handling.
- Deliverables must be production-ready: .tf, .ps1, runbooks with Problem/RCA/Fix/Rollback/Evidence.
- Always include comments explaining WHY, not just WHAT.
- Use Azure best practices (latest API versions, Standard SKUs, resource naming conventions).
- PowerShell: parameters, logging, error handling, CSV/JSON output.
- Terraform: modules, variables with descriptions, outputs, lifecycle rules.

If you are iterating on a previous draft that was rejected by the Critic, incorporate the validation feedback to fix the issues."""


def engineer_node(state: AgentState) -> AgentState:
    """
    The primary builder. Generates code, runbooks, or architecture using
    Anthropic Sonnet with full context augmentation.
    """
    t0 = time.time()
    iteration_label = f"(iteration {state.iteration + 1}/{state.max_iterations})"
    logger.info("🔧 [Engineer] Drafting solution %s...", iteration_label)

    # Build context block
    context_parts = []
    if state.context.get("pinecone_memories"):
        context_parts.append("## Past Relevant Experiences (from memory)")
        for mem in state.context["pinecone_memories"]:
            context_parts.append(f"- [Score: {mem['score']}] {mem['content']}")

    if state.context.get("perplexity_research", {}).get("answer"):
        context_parts.append("\n## Latest Research (from live web search)")
        context_parts.append(state.context["perplexity_research"]["answer"])
        if state.context["perplexity_research"].get("citations"):
            context_parts.append("\nSources:")
            for url in state.context["perplexity_research"]["citations"]:
                context_parts.append(f"- {url}")

    if state.validation_errors:
        context_parts.append("\n## ❌ Previous Validation Errors (FIX THESE)")
        for err in state.validation_errors:
            context_parts.append(f"- {err}")
        context_parts.append("\nYou MUST fix all the above errors in your revised output.")

    context_block = "\n".join(context_parts) if context_parts else "(No additional context available)"

    user_msg = f"""## Request
{state.query}

## Available Context
{context_block}

## Instructions
Generate a complete, production-ready deliverable. If the request involves code, include the full script — no placeholders, no "TODO" comments, no truncation."""

    model = ModelTier.REASONER if state.route == Route.REASONER else ModelTier.ENGINEER

    state.draft_code = _llm_call(
        model,
        [
            {"role": "system", "content": ENGINEER_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=8192,
        temperature=0.3,
    )

    state.iteration += 1
    state.timings[f"engineer_{state.iteration}"] = round(time.time() - t0, 2)
    logger.info(
        "🔧 [Engineer] Draft complete: %d chars (%.1fs)",
        len(state.draft_code), state.timings[f"engineer_{state.iteration}"],
    )
    return state


# ---------------------------------------------------------------------------
# NODE 4: Critic Agent
# ---------------------------------------------------------------------------
CRITIC_SYSTEM_PROMPT = """You are "The Critic" — the quality gate in a multi-agent system serving an MSP senior infrastructure consultant.

Your job is to evaluate the Engineer's output against these strict standards:

1. **Correctness**: Does the code/runbook actually solve the stated problem?
2. **Completeness**: Are all edge cases handled? Missing error handling? Incomplete parameters?
3. **Safety**: Are there rollback paths? Safe defaults? No destructive operations without confirmation?
4. **Best Practices**: Latest API versions? Proper naming? Idempotent operations?
5. **Production Readiness**: Can this be deployed as-is by a senior engineer?

If the output contains code (Terraform, PowerShell, etc.), look for:
- Syntax errors, invalid resource arguments, deprecated features
- Missing required parameters
- Hardcoded values that should be variables
- Missing outputs or documentation

Respond with a JSON object:
{
  "passed": true/false,
  "score": 1-10,
  "errors": ["list of critical issues that MUST be fixed"],
  "warnings": ["list of non-critical suggestions"],
  "summary": "one-line verdict"
}"""


def critic_node(state: AgentState) -> AgentState:
    """
    Evaluates the Engineer's draft against quality standards.
    Optionally validates code in an E2B sandbox.
    """
    t0 = time.time()
    logger.info("🔍 [Critic] Reviewing draft...")

    # --- Step 1: LLM-based review ---
    critic_result = _llm_call(
        ModelTier.CRITIC,
        [
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"## Original Request\n{state.query}\n\n## Engineer's Output\n{state.draft_code}",
            },
        ],
        max_tokens=2048,
        temperature=0.1,
        json_mode=True,
    )

    try:
        review = json.loads(critic_result)
    except json.JSONDecodeError:
        logger.warning("Critic returned non-JSON, attempting extraction...")
        # Try to extract JSON from the response
        import re
        json_match = re.search(r'\{.*\}', critic_result, re.DOTALL)
        if json_match:
            try:
                review = json.loads(json_match.group())
            except json.JSONDecodeError:
                review = {"passed": True, "score": 6, "errors": [], "warnings": ["Critic response parsing failed"], "summary": "Unable to parse review"}
        else:
            review = {"passed": True, "score": 6, "errors": [], "warnings": ["Critic response parsing failed"], "summary": "Unable to parse review"}

    state.validation_result = review
    logger.info(
        "🔍 [Critic] LLM Review: score=%s, passed=%s, errors=%d",
        review.get("score"), review.get("passed"), len(review.get("errors", [])),
    )

    # --- Step 2: Sandbox validation (if code detected) ---
    if state.draft_code and state.route == Route.ENGINEER:
        # Check for Terraform code blocks
        if "resource " in state.draft_code or "```hcl" in state.draft_code or "```terraform" in state.draft_code:
            logger.info("🔍 [Critic] Detected Terraform — running sandbox validation...")
            try:
                from src.tools.validate_terraform import validate_terraform
                import re

                # Extract terraform code from markdown code blocks
                tf_blocks = re.findall(
                    r'```(?:hcl|terraform)\s*\n(.*?)```',
                    state.draft_code, re.DOTALL,
                )
                tf_code = "\n\n".join(tf_blocks) if tf_blocks else state.draft_code

                sandbox_result = validate_terraform(tf_code)
                if not sandbox_result["passed"]:
                    review["passed"] = False
                    review["errors"] = review.get("errors", []) + [
                        f"[Sandbox] {e}" for e in sandbox_result["errors"]
                    ]
                    logger.info("🔍 [Critic] Sandbox validation FAILED: %s", sandbox_result["errors"])

            except Exception as e:
                logger.warning("🔍 [Critic] Sandbox validation skipped: %s", e)

        # Check for PowerShell code blocks
        if "```powershell" in state.draft_code or "```ps1" in state.draft_code:
            logger.info("🔍 [Critic] Detected PowerShell — running lint...")
            try:
                from src.tools.validate_terraform import validate_powershell
                import re

                ps_blocks = re.findall(
                    r'```(?:powershell|ps1)\s*\n(.*?)```',
                    state.draft_code, re.DOTALL,
                )
                if ps_blocks:
                    ps_code = ps_blocks[0]
                    ps_result = validate_powershell(ps_code)
                    if not ps_result["passed"]:
                        review["passed"] = False
                        review["errors"] = review.get("errors", []) + [
                            f"[PSScriptAnalyzer] {e}" for e in ps_result["errors"]
                        ]

            except Exception as e:
                logger.warning("🔍 [Critic] PS validation skipped: %s", e)

    # Update state
    state.validation_result = review
    if not review.get("passed", True):
        state.validation_errors = review.get("errors", [])
    else:
        state.validation_errors = []
        state.final_deliverable = state.draft_code

    state.timings["critic"] = round(time.time() - t0, 2)
    logger.info(
        "🔍 [Critic] Review complete (%.1fs): %s",
        state.timings["critic"],
        "✅ PASSED" if review.get("passed") else "❌ FAILED — sending back to Engineer",
    )
    return state


# ---------------------------------------------------------------------------
# NODE 5: Experience Distillation
# ---------------------------------------------------------------------------
def distill_node(state: AgentState) -> AgentState:
    """
    After a successful resolution, distill the experience into a semantic
    memory vector for future recall. This is how the agent self-improves.
    """
    if not state.final_deliverable:
        return state

    logger.info("💾 [Distill] Storing experience for future recall...")

    try:
        from src.tools.query_pinecone import upsert_memory
        from datetime import datetime

        # Create a compressed lesson from the full interaction
        lesson = (
            f"Query: {state.query}\n"
            f"Route: {state.route.value if state.route else 'unknown'}\n"
            f"Iterations: {state.iteration}\n"
            f"Score: {state.validation_result.get('score', 'N/A') if state.validation_result else 'N/A'}\n"
            f"Solution summary (first 1000 chars): {state.final_deliverable[:1000]}"
        )

        doc_id = f"exp-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        upsert_memory(
            doc_id=doc_id,
            content=lesson,
            metadata={
                "type": "experience",
                "route": state.route.value if state.route else "unknown",
                "iterations": state.iteration,
                "score": state.validation_result.get("score", 0) if state.validation_result else 0,
                "query": state.query[:200],
            },
        )
        logger.info("💾 [Distill] Experience '%s' stored successfully", doc_id)

    except Exception as e:
        logger.warning("💾 [Distill] Experience storage failed (non-fatal): %s", e)

    return state


# ---------------------------------------------------------------------------
# MAIN ORCHESTRATOR
# ---------------------------------------------------------------------------
def run_orchestrator(query: str, *, max_iterations: int = 3) -> dict:
    """
    Main entry point. Runs the full Triage → Engineer → Critic loop
    with automatic retry on validation failure.

    Args:
        query: The user's request
        max_iterations: Max Engineer↔Critic loops (default: 3 per MEMORY.md standard)

    Returns:
        dict with keys:
            - "deliverable": str — the final output (code, runbook, answer)
            - "route": str — which route was taken
            - "iterations": int — how many Engineer↔Critic rounds
            - "score": int — Critic's quality score (1–10)
            - "timings": dict — timing breakdown per node
            - "context_sources": list — what context was used
    """
    t_total = time.time()
    logger.info("=" * 60)
    logger.info("🚀 Orchestrator starting for: %s", query[:80])
    logger.info("=" * 60)

    state = AgentState(query=query, max_iterations=max_iterations)

    # --- Initialize tracer ---
    try:
        from src.observability.tracer import get_tracer
        tracer = get_tracer()
    except Exception:
        tracer = None

    trace_ctx = None
    if tracer:
        trace_ctx = tracer.trace("orchestrator", input_data={"query": query})
        trace_ctx.__enter__()

    try:
        # Step 1: Triage
        if tracer and trace_ctx:
            with trace_ctx.span("triage", input_data={"query": query[:200]}) as s:
                state = triage_node(state)
                s.set_output({"route": state.route.value if state.route else "unknown"})
        else:
            state = triage_node(state)

        # Step 2: Context retrieval (skip for BASIC)
        if state.route != Route.BASIC:
            if tracer and trace_ctx:
                with trace_ctx.span("context_retrieval") as s:
                    state = context_node(state)
                    s.set_output({"sources": list(state.context.keys())})
            else:
                state = context_node(state)

        # Step 3: Engineer ↔ Critic loop
        if state.route == Route.BASIC:
            if tracer and trace_ctx:
                with trace_ctx.llm_call("basic_response", model=ModelTier.TRIAGE) as lc:
                    state.final_deliverable = _llm_call(
                        ModelTier.TRIAGE,
                        [
                            {
                                "role": "system",
                                "content": "You are a concise IT infrastructure assistant. Be direct and technical.",
                            },
                            {"role": "user", "content": query},
                        ],
                        max_tokens=2048,
                    )
                    lc.set_output({"length": len(state.final_deliverable)})
            else:
                state.final_deliverable = _llm_call(
                    ModelTier.TRIAGE,
                    [
                        {
                            "role": "system",
                            "content": "You are a concise IT infrastructure assistant. Be direct and technical.",
                        },
                        {"role": "user", "content": query},
                    ],
                    max_tokens=2048,
                )
            state.validation_result = {"passed": True, "score": 7}
        else:
            # Engineer ↔ Critic loop with retry
            while state.iteration < state.max_iterations:
                if tracer and trace_ctx:
                    with trace_ctx.span(f"engineer_iteration_{state.iteration + 1}") as s:
                        state = engineer_node(state)
                        s.set_output({"draft_length": len(state.draft_code or "")})
                    with trace_ctx.span(f"critic_iteration_{state.iteration}") as s:
                        state = critic_node(state)
                        s.set_output({
                            "passed": state.validation_result.get("passed") if state.validation_result else None,
                            "score": state.validation_result.get("score") if state.validation_result else None,
                        })
                else:
                    state = engineer_node(state)
                    state = critic_node(state)

                if state.final_deliverable:
                    break  # Critic approved

                logger.info(
                    "🔄 [Loop] Iteration %d/%d failed. Retrying with error feedback...",
                    state.iteration, state.max_iterations,
                )

            if not state.final_deliverable:
                logger.warning("⚠️ Max iterations reached. Delivering last draft with warnings.")
                state.final_deliverable = state.draft_code
                state.metadata["max_iterations_reached"] = True

        # Step 4: Experience distillation
        if state.final_deliverable:
            if tracer and trace_ctx:
                with trace_ctx.span("distill") as s:
                    state = distill_node(state)
                    s.set_output({"distilled": True})
            else:
                state = distill_node(state)

        # Record quality score in trace
        if tracer and state.validation_result:
            tracer.score(
                float(state.validation_result.get("score", 0)),
                name="quality",
                comment=state.validation_result.get("summary", ""),
            )

    finally:
        if trace_ctx:
            trace_ctx.__exit__(None, None, None)

    total_time = round(time.time() - t_total, 2)
    state.timings["total"] = total_time

    logger.info("=" * 60)
    logger.info(
        "✅ Orchestrator complete: route=%s, iterations=%d, score=%s, time=%.1fs",
        state.route.value if state.route else "?",
        state.iteration,
        state.validation_result.get("score", "?") if state.validation_result else "?",
        total_time,
    )
    logger.info("=" * 60)

    return {
        "deliverable": state.final_deliverable or "No deliverable generated.",
        "route": state.route.value if state.route else "unknown",
        "iterations": state.iteration,
        "score": state.validation_result.get("score") if state.validation_result else None,
        "validation": state.validation_result,
        "timings": state.timings,
        "context_sources": list(state.context.keys()),
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
    else:
        user_query = "Create a Terraform module for a highly-available Azure VPN Gateway with diagnostic logging"

    result = run_orchestrator(user_query)

    print("\n" + "=" * 60)
    print("📋 ORCHESTRATOR RESULT")
    print("=" * 60)
    print(f"Route:      {result['route']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Score:      {result['score']}")
    print(f"Timings:    {result['timings']}")
    print(f"Context:    {result['context_sources']}")
    print(f"\n--- Deliverable ({len(result['deliverable'])} chars) ---")
    print(result["deliverable"][:2000])
    if len(result["deliverable"]) > 2000:
        print(f"\n... [{len(result['deliverable']) - 2000} more chars]")
