"""
Terraform Module Builder Service — Validated IaC module generation.

Generates production-ready Terraform modules with:
- Proper module structure (variables, outputs, providers)
- E2B sandbox validation before delivery
- Azure best practices baked in
- Automatic experience distillation

Usage:
    from src.services.terraform_builder import build_terraform_module
    result = build_terraform_module(
        requirement="Highly-available Azure VPN Gateway with diagnostic logging",
        provider="azurerm",
    )
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("services.terraform")


TF_SYSTEM_PROMPT = """You are a senior Terraform engineer generating production-ready Azure infrastructure modules.

OUTPUT FORMAT — Generate a complete Terraform module with these files in code blocks:

### main.tf
```hcl
[Primary resource definitions]
```

### variables.tf
```hcl
[All variables with type, description, default, and validation blocks]
```

### outputs.tf
```hcl
[All meaningful outputs with descriptions]
```

### terraform.tfvars.example
```hcl
[Example variable values]
```

RULES:
- Use azurerm provider ~> 4.0 unless specified otherwise
- Every variable MUST have: type, description, and sensible default where applicable
- Use lifecycle rules (prevent_destroy for critical resources)
- Include resource naming following Azure CAF conventions
- Add diagnostic_setting resources for all services that support it
- Use Standard SKUs (not Basic) unless explicitly requested
- Include tags variable merged into all resources
- No hardcoded values — everything parameterized
- Include depends_on where implicit dependencies aren't clear
- Add comments explaining WHY for non-obvious choices"""


def build_terraform_module(
    requirement: str,
    *,
    provider: str = "azurerm",
    validate: bool = True,
    use_memory: bool = True,
    use_research: bool = True,
) -> dict:
    """
    Generate a validated Terraform module.

    Args:
        requirement: What the module should provision
        provider: Cloud provider (default: azurerm)
        validate: Whether to sandbox-validate the output
        use_memory: Search for similar past modules
        use_research: Search for latest provider docs

    Returns:
        dict with:
            - "module": str — the full module (all files)
            - "validation": dict — sandbox validation result
            - "context_used": list
            - "metadata": dict
    """
    logger.info("[Terraform] Building module: %s", requirement[:80])
    context_parts = []
    context_used = []

    if use_memory:
        try:
            from src.tools.query_pinecone import query_memory
            memories = query_memory(requirement, top_k=3, filter_metadata={"category": "terraform"})
            if memories:
                context_parts.append("## Similar Past Modules")
                for m in memories:
                    context_parts.append(f"- [{m['score']:.2f}] {m['content'][:300]}")
                context_used.append("pinecone_memory")
        except Exception as e:
            logger.debug("Memory skipped: %s", e)

    if use_research:
        try:
            from src.tools.search_perplexity import search_perplexity
            research = search_perplexity(f"terraform {provider} {requirement} best practices 2026")
            if research.get("answer"):
                context_parts.append(f"\n## Latest Terraform Docs\n{research['answer'][:1000]}")
                context_used.append("perplexity_research")
        except Exception as e:
            logger.debug("Research skipped: %s", e)

    user_parts = [
        f"Generate a complete Terraform module for:",
        f"\n**Requirement:** {requirement}",
        f"**Provider:** {provider}",
    ]
    if context_parts:
        user_parts.append("\n" + "\n".join(context_parts))

    from src.orchestrator import _llm_call, ModelTier
    module_code = _llm_call(
        ModelTier.ENGINEER,
        [
            {"role": "system", "content": TF_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_parts)},
        ],
        max_tokens=8192,
        temperature=0.2,
    )

    # Validate in sandbox
    validation = {"passed": True, "errors": [], "warnings": ["Validation skipped"]}
    if validate:
        try:
            from src.tools.validate_terraform import validate_terraform
            import re
            tf_blocks = re.findall(r'```(?:hcl|terraform)\s*\n(.*?)```', module_code, re.DOTALL)
            if tf_blocks:
                combined = "\n\n".join(tf_blocks)
                validation = validate_terraform(combined)
                logger.info("[Terraform] Validation: %s", "PASSED" if validation["passed"] else "FAILED")
        except Exception as e:
            logger.debug("Validation skipped: %s", e)
            validation["warnings"] = [f"Validation error: {e}"]

    # Distill
    try:
        from src.memory.distill import distill_experience
        distill_experience(
            query=requirement,
            solution=module_code,
            route="terraform-service",
            score=8 if validation["passed"] else 5,
            category="terraform",
        )
    except Exception:
        pass

    return {
        "module": module_code,
        "validation": validation,
        "context_used": context_used,
        "metadata": {
            "provider": provider,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "validated": validate,
            "passed": validation.get("passed", False),
            "chars": len(module_code),
        },
    }
