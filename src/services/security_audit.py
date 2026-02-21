"""
Security Audit Report Service — Azure tenant security posture analysis.

Generates structured security audit reports covering:
- RBAC hygiene (overprivileged accounts, orphaned assignments)
- Policy coverage gaps
- Privileged group analysis (AdminSDHolder, Domain Admins)
- Conditional access review
- Recommendations prioritized by risk

Usage:
    from src.services.security_audit import generate_security_audit
    result = generate_security_audit(
        scope="Azure tenant + on-prem AD",
        client="GR Energy",
        focus_areas=["RBAC", "privileged_groups", "conditional_access"],
    )
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("services.security_audit")


AUDIT_SYSTEM_PROMPT = """You are a senior security consultant generating a structured Azure/AD security audit report.

OUTPUT FORMAT:

# Security Audit Report

## Executive Summary
[2-3 sentence summary of findings for leadership]

## Scope
- **Client:** [Name]
- **Environment:** [Azure tenant, on-prem AD, hybrid]
- **Date:** [YYYY-MM-DD]
- **Auditor:** AI Agent (reviewed by Rob Loftin, 143IT)

## Critical Findings (Action Required)
### Finding 1: [Title]
- **Risk:** Critical/High/Medium/Low
- **Description:** [What's wrong]
- **Impact:** [What could happen]
- **Remediation:** [Exact steps to fix, with commands]
- **Effort:** [Time estimate]

## RBAC Analysis
[Analysis of role assignments, overprivileged accounts, orphaned assignments]

## Privileged Group Hygiene
[AdminSDHolder, Domain Admins, Enterprise Admins, Schema Admins analysis]

## Policy & Compliance
[Azure Policy coverage, Conditional Access gaps, baseline compliance]

## Recommendations (Prioritized)
| Priority | Finding | Risk | Effort | Remediation |
|----------|---------|------|--------|-------------|

## Appendix: Scripts
[PowerShell/CLI scripts for verification and remediation]

RULES:
- All remediation steps must include exact commands
- PowerShell scripts must have error handling and -WhatIf support
- Prioritize findings by risk × ease-of-exploit
- Reference CIS benchmarks / Microsoft Security Baselines where applicable
- Include Azure CLI and PowerShell alternatives for all checks"""


def generate_security_audit(
    scope: str,
    *,
    client: Optional[str] = None,
    focus_areas: Optional[list[str]] = None,
    additional_context: Optional[str] = None,
    use_memory: bool = True,
    use_research: bool = True,
) -> dict:
    """
    Generate a security audit report.

    Args:
        scope: What to audit (e.g., "Azure tenant + on-prem AD")
        client: Client name
        focus_areas: Specific areas to focus on
        additional_context: Existing findings, tenant info, etc.
        use_memory: Search for past audit patterns
        use_research: Search for latest security advisories

    Returns:
        dict with:
            - "report": str — the full Markdown audit report
            - "findings_count": int
            - "critical_count": int
            - "context_used": list
            - "metadata": dict
    """
    logger.info("[Audit] Generating for: %s", scope[:80])
    context_parts = []
    context_used = []

    if use_memory:
        try:
            from src.tools.query_pinecone import query_memory
            memories = query_memory(f"security audit {scope}", top_k=3)
            if memories:
                context_parts.append("## Past Audit Patterns")
                for m in memories:
                    context_parts.append(f"- [{m['score']:.2f}] {m['content'][:300]}")
                context_used.append("pinecone_memory")
        except Exception:
            pass

    if use_research:
        try:
            from src.tools.search_perplexity import search_perplexity
            research = search_perplexity(f"Azure AD security best practices CIS benchmark 2026 {scope}")
            if research.get("answer"):
                context_parts.append(f"\n## Latest Security Advisories\n{research['answer'][:1000]}")
                context_used.append("perplexity_research")
        except Exception:
            pass

    user_parts = [
        f"Generate a comprehensive security audit report:",
        f"\n**Scope:** {scope}",
    ]
    if client:
        user_parts.append(f"**Client:** {client}")
    if focus_areas:
        user_parts.append(f"**Focus Areas:** {', '.join(focus_areas)}")
    if additional_context:
        user_parts.append(f"\n**Existing Context:**\n{additional_context}")
    if context_parts:
        user_parts.append("\n" + "\n".join(context_parts))

    from src.orchestrator import _llm_call, ModelTier
    report = _llm_call(
        ModelTier.ENGINEER,
        [
            {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_parts)},
        ],
        max_tokens=8192,
        temperature=0.2,
    )

    # Count findings
    critical_count = report.lower().count("**risk:** critical")
    high_count = report.lower().count("**risk:** high")
    findings_count = critical_count + high_count + report.lower().count("**risk:** medium") + report.lower().count("**risk:** low")

    # Distill
    try:
        from src.memory.distill import distill_experience
        distill_experience(
            query=f"Security audit: {scope}",
            solution=report,
            route="audit-service",
            score=8,
            category="security-audit",
            client=client,
        )
    except Exception:
        pass

    return {
        "report": report,
        "findings_count": findings_count,
        "critical_count": critical_count,
        "context_used": context_used,
        "metadata": {
            "client": client,
            "scope": scope,
            "focus_areas": focus_areas or [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "chars": len(report),
        },
    }
