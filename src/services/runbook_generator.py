"""
Incident Runbook Generator Service — Production-ready runbook generation.

Takes an incident description and generates a structured, client-deliverable
runbook following Rob's strict standards:
  Problem → Symptoms → Impact → Root Cause → Fix → Prevention → Evidence

Usage:
    from src.services.runbook_generator import generate_runbook
    result = generate_runbook(
        incident="ADFS authentication failing for external users",
        client="GR Energy",
        severity="High",
    )
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("services.runbook")


RUNBOOK_SYSTEM_PROMPT = """You are a senior IT infrastructure consultant generating a production-ready incident runbook.

OUTPUT FORMAT (strict — follow this exactly):

# Incident Runbook: [Title]

## Metadata
- **Date:** [YYYY-MM-DD]
- **Severity:** [Critical/High/Medium/Low]
- **Client:** [Client name]
- **Author:** AI Agent (reviewed by Rob Loftin, 143IT)

## Problem Statement
[1-2 sentences describing the issue]

## Symptoms
- [Observable symptoms as bullet points]

## Impact
- [Business/technical impact]

## Root Cause Analysis
[Technical root cause with evidence]

## Resolution Steps
1. [Step-by-step fix with exact commands/actions]
2. [Include rollback instructions for each step]

## Verification
- [How to confirm the fix worked]

## Prevention
- [What to do to prevent recurrence]

## Evidence
- [Logs, screenshots, config excerpts referenced]

## Rollback Plan
[Complete rollback procedure if the fix causes issues]

---

RULES:
- Every command must be copy-paste ready
- Include parameter descriptions for scripts
- Use PowerShell for Windows, Bash for Linux
- Include error handling in all scripts
- No placeholders — fill in realistic values based on the incident context
- Be specific to the client's environment when context is provided"""


def generate_runbook(
    incident: str,
    *,
    client: Optional[str] = None,
    severity: str = "Medium",
    additional_context: Optional[str] = None,
    use_memory: bool = True,
    use_research: bool = True,
) -> dict:
    """
    Generate a structured incident runbook.

    Args:
        incident: Description of the incident
        client: Client name for context
        severity: Severity level (Critical/High/Medium/Low)
        additional_context: Extra context (logs, error messages, etc.)
        use_memory: Whether to search Pinecone for similar past incidents
        use_research: Whether to search Perplexity for latest docs

    Returns:
        dict with:
            - "runbook": str — the full Markdown runbook
            - "title": str — generated title
            - "context_used": list — what sources were consulted
            - "metadata": dict — generation metadata
    """
    logger.info("[Runbook] Generating for: %s", incident[:80])
    context_parts = []
    context_used = []

    # Retrieve past similar incidents from memory
    if use_memory:
        try:
            from src.tools.query_pinecone import query_memory
            memories = query_memory(incident, top_k=3, filter_metadata={"category": "runbook"} if client else None)
            if memories:
                context_parts.append("## Similar Past Incidents")
                for m in memories:
                    context_parts.append(f"- [{m['score']:.2f}] {m['content'][:300]}")
                context_used.append("pinecone_memory")
        except Exception as e:
            logger.debug("Memory retrieval skipped: %s", e)

    # Research latest docs
    if use_research:
        try:
            from src.tools.search_perplexity import search_perplexity
            research = search_perplexity(f"troubleshooting {incident}")
            if research.get("answer"):
                context_parts.append(f"\n## Latest Research\n{research['answer'][:1000]}")
                context_used.append("perplexity_research")
        except Exception as e:
            logger.debug("Research skipped: %s", e)

    # Build the prompt
    user_parts = [
        f"Generate a complete incident runbook for the following:",
        f"\n**Incident:** {incident}",
        f"**Severity:** {severity}",
    ]
    if client:
        user_parts.append(f"**Client:** {client}")
    if additional_context:
        user_parts.append(f"\n**Additional Context:**\n{additional_context}")
    if context_parts:
        user_parts.append("\n" + "\n".join(context_parts))

    # Call the orchestrator's LLM
    from src.orchestrator import _llm_call, ModelTier
    runbook = _llm_call(
        ModelTier.ENGINEER,
        [
            {"role": "system", "content": RUNBOOK_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_parts)},
        ],
        max_tokens=4096,
        temperature=0.2,
    )

    # Extract title
    title = incident[:80]
    for line in runbook.split("\n"):
        if line.startswith("# Incident Runbook:"):
            title = line.replace("# Incident Runbook:", "").strip()
            break

    # Distill the experience
    try:
        from src.memory.distill import distill_experience
        distill_experience(
            query=incident,
            solution=runbook,
            route="runbook-service",
            score=8,
            category="runbook",
            client=client,
        )
    except Exception:
        pass

    return {
        "runbook": runbook,
        "title": title,
        "context_used": context_used,
        "metadata": {
            "client": client,
            "severity": severity,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": ModelTier.ENGINEER,
            "chars": len(runbook),
        },
    }
