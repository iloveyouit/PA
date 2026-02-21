"""
Perplexity Search Tool — Live web research via Perplexity API.

Resolves missing context against the latest MS Docs, CVEs, deprecation notices,
and community fixes. Prevents Azure/infrastructure hallucinations by grounding
the agent in real, current documentation.

Usage:
    from src.tools.search_perplexity import search_perplexity
    result = search_perplexity("Azure Load Balancer standard SKU limitations 2026")
"""
import os
import json
import logging
import requests
from typing import Optional

logger = logging.getLogger("tools.perplexity")

# Perplexity API endpoint (direct, not via OpenRouter)
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Default model — sonar-pro for deep search with citations
DEFAULT_MODEL = "sonar-pro"


def search_perplexity(
    query: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
    focus: str = "internet",
    return_citations: bool = True,
) -> dict:
    """
    Search the web via Perplexity API and return AI-synthesized results.

    Args:
        query: The search query (e.g., "Azure VPN Gateway terraform module best practices")
        model: Perplexity model to use (sonar, sonar-pro, sonar-reasoning)
        max_tokens: Max tokens for the response
        focus: Search focus area ("internet", "scholar", "writing", "wolfram")
        return_citations: Whether to include source citations

    Returns:
        dict with keys:
            - "answer": str — synthesized answer text
            - "citations": list[str] — source URLs (if return_citations=True)
            - "model": str — model used
            - "usage": dict — token usage stats

    Raises:
        EnvironmentError: If PERPLEXITY_API_KEY is not set
        requests.HTTPError: If the API call fails
    """
    api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        # Fallback: try OpenRouter with perplexity model
        return _search_via_openrouter(query, max_tokens=max_tokens)

    logger.info("[Perplexity] Searching: %s", query[:80])

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a technical research assistant specializing in "
                    "Microsoft Azure, Windows Server, Active Directory, Entra ID, "
                    "Terraform, and enterprise IT infrastructure. "
                    "Provide precise, current, and actionable answers. "
                    "Always cite your sources."
                ),
            },
            {"role": "user", "content": query},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "return_citations": return_citations,
    }

    resp = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    citations = data.get("citations", [])
    usage = data.get("usage", {})

    logger.info(
        "[Perplexity] Got %d chars, %d citations, %d tokens",
        len(answer), len(citations), usage.get("total_tokens", 0),
    )

    return {
        "answer": answer,
        "citations": citations,
        "model": model,
        "usage": usage,
    }


def _search_via_openrouter(query: str, max_tokens: int = 1024) -> dict:
    """Fallback: use OpenRouter to access Perplexity models."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "Neither PERPLEXITY_API_KEY nor OPENROUTER_API_KEY is set. "
            "Cannot perform web research."
        )

    logger.info("[Perplexity via OpenRouter] Searching: %s", query[:80])

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "perplexity/sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a technical research assistant specializing in "
                    "Microsoft Azure, Windows Server, Active Directory, Entra ID, "
                    "Terraform, and enterprise IT infrastructure. "
                    "Provide precise, current, and actionable answers with citations."
                ),
            },
            {"role": "user", "content": query},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers, json=payload, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})

    return {
        "answer": answer,
        "citations": [],
        "model": "perplexity/sonar-pro (via OpenRouter)",
        "usage": usage,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

    result = search_perplexity("Azure Load Balancer standard SKU limitations 2026")
    print(f"Answer ({len(result['answer'])} chars):")
    print(result["answer"][:500])
    if result["citations"]:
        print(f"\nCitations: {result['citations'][:5]}")
    print(f"\nUsage: {result['usage']}")
