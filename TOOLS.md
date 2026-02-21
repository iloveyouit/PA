# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

## Advanced Cognitive Tools (Self-Improving Agent Stack)

Your execution is augmented by the APIs wrapped in `src/tools/`. These are **real, functional integrations** — not stubs.

### `search_perplexity.py` — Live Web Research
- **What:** Calls Perplexity API (sonar-pro) for real-time web search grounded in latest docs.
- **Fallback:** If `PERPLEXITY_API_KEY` is missing, auto-falls back to OpenRouter.
- **When to use:** Before writing Terraform/PowerShell for new Azure features; to verify deprecation status; to find community workarounds.
- **Usage:** `from src.tools.search_perplexity import search_perplexity`

### `query_pinecone.py` — Semantic Memory
- **What:** Queries/upserts vectors in Pinecone. Stores past incidents, runbooks, KB articles as embeddings.
- **Auto-setup:** Creates the index automatically if it doesn't exist.
- **When to use:** Before any troubleshooting (recall similar past incidents); after successful resolution (distill the experience).
- **Functions:** `query_memory()`, `upsert_memory()`, `bulk_upsert()`
- **Usage:** `from src.tools.query_pinecone import query_memory, upsert_memory`

### `validate_terraform.py` — Sandboxed Code Validation
- **What:** Spins up E2B micro-VM, runs `terraform validate` / `PSScriptAnalyzer`, reports structured pass/fail.
- **Fallback:** Basic local syntax checks if `E2B_API_KEY` is missing.
- **When to use:** Always before delivering .tf or .ps1 code. The Critic node calls this automatically.
- **Functions:** `validate_terraform()`, `validate_powershell()`
- **Usage:** `from src.tools.validate_terraform import validate_terraform, validate_powershell`

---

Add whatever helps you do your job. This is your cheat sheet.
