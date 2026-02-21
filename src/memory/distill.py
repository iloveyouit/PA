"""
Experience Distillation — Post-task learning for self-improvement.

After the orchestrator completes a task, this module compresses the full
interaction into a concise "lesson learned" and stores it as a semantic
memory vector. This is the core self-improvement mechanism.

The distillation process:
1. Takes the full task context (query, route, context, draft, validation, final output)
2. Uses an LLM to synthesize a compressed lesson (key decision, root cause, fix pattern)
3. Upserts the lesson into Pinecone with rich metadata for future retrieval

Usage:
    from src.memory.distill import distill_experience
    distill_experience(
        query="Fix ADFS auth for external users",
        solution="Root cause was expired SAML cert...",
        route="engineer",
        score=8,
        context_used=["Pinecone memory", "Perplexity research"],
    )
"""
import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = logging.getLogger("memory.distill")


def distill_experience(
    query: str,
    solution: str,
    *,
    route: str = "unknown",
    score: int = 0,
    iterations: int = 1,
    context_used: Optional[list[str]] = None,
    validation_errors: Optional[list[str]] = None,
    client: Optional[str] = None,
    category: Optional[str] = None,
    use_llm_compression: bool = True,
) -> Optional[str]:
    """
    Distill a completed task into a semantic memory vector.

    Args:
        query: The original user request
        solution: The final delivered output (code, runbook, etc.)
        route: Which orchestrator route was used (basic/engineer/reasoner)
        score: Critic's quality score (1-10)
        iterations: How many engineer↔critic iterations were needed
        context_used: Which context sources were used (e.g., ["pinecone_memories", "perplexity_research"])
        validation_errors: Errors that were found and fixed during iteration
        client: Client name if applicable
        category: Category tag (e.g., "terraform", "powershell", "runbook", "troubleshooting")
        use_llm_compression: Whether to use LLM to compress the lesson (vs raw concat)

    Returns:
        The doc_id of the stored vector, or None if storage failed
    """
    logger.info("💾 [Distill] Compressing experience: %s", query[:60])

    # Generate the lesson content
    if use_llm_compression and len(solution) > 500:
        lesson = _llm_compress(query, solution, route, score, validation_errors)
    else:
        lesson = _raw_compress(query, solution, route, score, validation_errors)

    if not lesson:
        logger.warning("💾 [Distill] No lesson generated — skipping storage")
        return None

    # Generate doc_id
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    doc_id = f"exp-{timestamp}-{route}"

    # Build metadata
    metadata = {
        "type": "experience",
        "route": route,
        "score": score,
        "iterations": iterations,
        "query": query[:300],
        "context_sources": ",".join(context_used) if context_used else "",
        "had_errors": bool(validation_errors),
        "distilled_at": datetime.now(timezone.utc).isoformat(),
    }
    if client:
        metadata["client"] = client
    if category:
        metadata["category"] = category
    if validation_errors:
        metadata["error_summary"] = "; ".join(validation_errors)[:500]

    # Auto-detect category from content
    if not category:
        lower = (query + " " + solution[:500]).lower()
        if "terraform" in lower or ".tf" in lower:
            metadata["category"] = "terraform"
        elif "powershell" in lower or ".ps1" in lower or "get-" in lower:
            metadata["category"] = "powershell"
        elif "runbook" in lower or "incident" in lower:
            metadata["category"] = "runbook"
        elif "ansible" in lower or "playbook" in lower:
            metadata["category"] = "ansible"
        elif "entra" in lower or "ad " in lower or "active directory" in lower:
            metadata["category"] = "identity"
        elif "azure" in lower:
            metadata["category"] = "azure"

    # Upsert to Pinecone
    try:
        from src.tools.query_pinecone import upsert_memory
        success = upsert_memory(doc_id=doc_id, content=lesson, metadata=metadata)
        if success:
            logger.info("💾 [Distill] Stored as '%s' (%d chars)", doc_id, len(lesson))
            return doc_id
        else:
            logger.error("💾 [Distill] Upsert returned false for '%s'", doc_id)
            return None
    except Exception as e:
        logger.error("💾 [Distill] Storage failed: %s", e)
        return None


def _llm_compress(
    query: str,
    solution: str,
    route: str,
    score: int,
    validation_errors: Optional[list[str]] = None,
) -> str:
    """Use an LLM to compress the experience into a concise, searchable lesson."""
    try:
        import litellm

        error_section = ""
        if validation_errors:
            error_section = f"\n\nErrors that were fixed during iteration:\n" + "\n".join(f"- {e}" for e in validation_errors)

        prompt = f"""Compress this IT infrastructure task into a concise lesson for future reference.
Focus on: the problem pattern, the key solution technique, and any gotchas discovered.
Keep it under 500 words. Make it searchable — someone with a similar problem should find this useful.

TASK: {query}
ROUTE: {route}
QUALITY SCORE: {score}/10{error_section}

SOLUTION (first 3000 chars):
{solution[:3000]}

Write the compressed lesson:"""

        model = os.getenv("MODEL_TRIAGE", "anthropic/claude-3-haiku-20240307")
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    except Exception as e:
        logger.warning("LLM compression failed (%s), using raw compression", e)
        return _raw_compress(query, solution, route, score, validation_errors)


def _raw_compress(
    query: str,
    solution: str,
    route: str,
    score: int,
    validation_errors: Optional[list[str]] = None,
) -> str:
    """Fallback: concatenate key fields into a structured lesson."""
    parts = [
        f"Query: {query}",
        f"Route: {route} | Score: {score}/10",
    ]
    if validation_errors:
        parts.append(f"Errors fixed: {'; '.join(validation_errors)}")
    parts.append(f"Solution (summary): {solution[:1500]}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Batch distillation from memory files
# ---------------------------------------------------------------------------
def distill_daily_files(
    memory_dir: str = "memory/",
    *,
    days_back: int = 7,
) -> int:
    """
    Review recent daily memory files and distill any significant entries
    into semantic memory. This is the automated "memory maintenance"
    described in AGENTS.md.

    Args:
        memory_dir: Path to memory directory
        days_back: How many days back to review

    Returns:
        Number of experiences distilled
    """
    logger.info("📅 [Distill] Reviewing daily files from last %d days...", days_back)
    count = 0
    mem_path = Path(memory_dir)

    if not mem_path.exists():
        logger.warning("Memory directory not found: %s", memory_dir)
        return 0

    for md_file in sorted(mem_path.glob("2*.md")):  # Match YYYY-*.md files
        try:
            content = md_file.read_text(encoding="utf-8")
            if len(content.strip()) < 50:
                continue

            # Each bullet point could be a distinct experience
            entries = [
                line.strip().lstrip("- ")
                for line in content.split("\n")
                if line.strip().startswith("- ") and len(line.strip()) > 20
            ]

            for entry in entries:
                doc_id = distill_experience(
                    query=f"Daily log entry from {md_file.stem}",
                    solution=entry,
                    route="daily-log",
                    score=5,
                    category="daily-log",
                    use_llm_compression=False,
                )
                if doc_id:
                    count += 1

        except Exception as e:
            logger.error("Failed to process %s: %s", md_file, e)

    logger.info("📅 [Distill] Distilled %d entries from daily files", count)
    return count


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if "--daily" in sys.argv:
        count = distill_daily_files()
        print(f"Distilled {count} daily entries")
    else:
        # Demo distillation
        doc_id = distill_experience(
            query="Create Terraform module for Azure VPN Gateway",
            solution="# VPN Gateway Module\nresource azurerm_virtual_network_gateway...",
            route="engineer",
            score=8,
            iterations=2,
            context_used=["pinecone_memories", "perplexity_research"],
            validation_errors=["Missing diagnostic_setting resource"],
        )
        print(f"Distilled experience: {doc_id}")
