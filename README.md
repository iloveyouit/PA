# 🦅 PA — Self-Improving AI Agent

A production-ready **multi-agent cognitive architecture** that generates IT infrastructure deliverables — incident runbooks, validated Terraform modules, and security audit reports — powered by a self-improving loop that learns from every engagement.

> **Status:** ✅ Phase 1–4 Complete · 13 Python modules · ~3,800 lines · Ready for API keys

---

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Usage](#usage)
  - [CLI Mode](#cli-mode)
  - [API Server](#api-server)
  - [Memory Ingest](#memory-ingest)
  - [Weekly Reports](#weekly-reports)
- [API Reference](#api-reference)
- [Services](#services)
- [Technology Stack](#technology-stack)
- [Development Phases](#development-phases)
- [Roadmap](#roadmap)

---

## Architecture

Every request flows through a **5-stage supervised loop** that gets smarter with each engagement:

```
┌─────────────┐     ┌───────────────┐     ┌────────────┐     ┌──────────┐     ┌──────────┐
│  🔀 Triage  │ ──▶ │ 📚 Context    │ ──▶ │ 🔧 Engneer │ ──▶ │ 🔍 Critic│ ──▶ │ 💾 Distill│
│  (Haiku)    │     │ Pinecone +    │     │  (Sonnet)  │     │ Sandbox  │     │ Learn +  │
│  Route req  │     │ Perplexity    │     │  Draft sol │     │ Validate │     │ Remember │
└─────────────┘     └───────────────┘     └────────────┘     └────┬─────┘     └──────────┘
                                                                  │
                                                          ┌───────▼───────┐
                                                          │ ❌ Failed?    │
                                                          │ Loop back to  │
                                                          │ Engineer (3x) │
                                                          └───────────────┘
```

**Key design decisions:**

| Decision | Rationale |
|----------|-----------|
| **Tiered LLM routing** | Haiku for triage (fast/cheap), Sonnet for engineering (capable), o3-mini for deep reasoning |
| **Dual-storage tracing** | Local JSONL always available + Langfuse cloud when configured |
| **Graceful degradation** | Every tool has a local fallback if API keys aren't set |
| **Experience distillation** | Successful resolutions → compressed lessons → Pinecone vectors → future recall |
| **Lazy client loading** | Pinecone/OpenAI clients loaded on first use, not at import time |

---

## Features

### 🧠 Multi-Agent Orchestrator
- Triage → Context → Engineer → Critic → Distill pipeline
- Automatic retry loop (max 3 iterations) when validation fails
- Configurable model tiers via environment variables
- Full observability tracing on every run

### 📌 Semantic Memory
- **Ingest pipeline** — Scans `.md` files from Obsidian vaults, Notion exports, or local directories
- Heading-aware chunking with configurable overlap
- YAML frontmatter extraction
- Bulk upsert to Pinecone with deterministic IDs
- **Experience distillation** — LLM-compressed lessons from every resolved task
- Auto-categorization (terraform, powershell, runbook, identity, azure)
- Daily memory file batch processor

### 🔍 Live Research
- Perplexity API with `sonar-pro` model for real-time web search
- Automatic fallback to OpenRouter if Perplexity key isn't set
- Tuned system prompt for Azure/infrastructure domain

### ✅ Sandboxed Validation
- E2B micro-VM for `terraform validate` and `PSScriptAnalyzer`
- Structured pass/fail results with error details
- Local syntax fallback when E2B isn't configured

### 📊 Observability
- Langfuse integration for cloud tracing
- Local JSONL trace storage (always active, zero config)
- Context managers for traces, spans, LLM calls, and tool calls
- Quality score recording from Critic evaluations

### 📈 Weekly Improvement Reports
- Automated analysis of local trace data
- Failure pattern detection and error clustering
- Token spend and cost trending
- Quality score distribution and trajectory
- Actionable improvement recommendations

### 🚀 REST API (FastAPI)
- API key authentication with auto-generated keys
- Sliding window rate limiting
- 4 service endpoints (query, runbook, terraform, audit)
- Stripe webhook handler for billing
- Interactive Swagger docs at `/docs`
- Client-facing web portal at `/`

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USER/PA.git
cd PA
cp .env.example .env
```

Edit `.env` and add your API keys. **Minimum to start:** just `ANTHROPIC_API_KEY`.

### 2. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run

```bash
# CLI mode — direct orchestrator
python src/orchestrator.py "Create a Terraform module for HA Azure VPN Gateway"

# API mode — full REST server + portal
uvicorn src.api.main:app --reload --port 8000
# Visit http://localhost:8000       → Client portal
# Visit http://localhost:8000/docs  → Swagger API docs
```

---

## Project Structure

```
PA/
├── README.md                 # This file
├── .env.example              # API key template (12 keys, 3 tiers)
├── .gitignore                # Protects .env, .secrets/, __pycache__
├── requirements.txt          # 17 Python dependencies
│
├── AGENTS.md                 # Agent operational procedures + architecture docs
├── SOUL.md                   # Core identity and values
├── IDENTITY.md               # Name, vibe, emoji (🦅)
├── MEMORY.md                 # Long-term curated memory + engineering standards
├── TOOLS.md                  # Tool documentation and cheat sheet
├── USER.md / USER_UPDATED.md # User profile (Rob Loftin, 143IT)
├── HEARTBEAT.md              # Periodic check policies
├── BOOTSTRAP.md.done         # Initial setup (completed)
│
├── memory/                   # Daily logs and profiles
│   ├── 2026-02-01.md
│   ├── 2026-02-19.md
│   └── profile-rob-loftin_v1_2026-02-01.md
│
├── src/
│   ├── config.py                        # Centralized env loader
│   ├── orchestrator.py                  # 🧠 Multi-agent loop (655 lines)
│   │
│   ├── tools/
│   │   ├── search_perplexity.py         # 🔍 Perplexity API + OpenRouter fallback
│   │   ├── query_pinecone.py            # 📌 Pinecone query/upsert/bulk
│   │   └── validate_terraform.py        # ✅ E2B sandbox for TF + PS1
│   │
│   ├── memory/
│   │   ├── ingest.py                    # 📥 Vault → chunks → Pinecone pipeline
│   │   └── distill.py                   # 💾 Experience distillation
│   │
│   ├── observability/
│   │   ├── tracer.py                    # 📊 Langfuse + local JSONL tracer
│   │   └── weekly_report.py             # 📈 Automated improvement reports
│   │
│   ├── services/
│   │   ├── runbook_generator.py         # 📋 Incident → structured runbook
│   │   ├── terraform_builder.py         # 🏗️ Requirement → validated TF module
│   │   └── security_audit.py            # 🔒 Scope → CIS-referenced audit report
│   │
│   └── api/
│       └── main.py                      # 🚀 FastAPI REST server + Stripe
│
├── web/
│   └── index.html                       # 🌐 Client-facing portal (dark theme)
│
├── traces/                              # Auto-created trace storage (JSONL)
│
├── perplexity-search-plugin/            # OpenClaw plugin (legacy)
│   ├── index.js
│   └── openclaw.plugin.json
│
└── scripts/
    └── switch-model.sh                  # Model switching utility
```

---

## Configuration

### API Keys (Tiered Priority)

| Tier | Key | Purpose | Where to Get |
|------|-----|---------|--------------|
| **Must-Have** | `ANTHROPIC_API_KEY` | Primary LLM (Sonnet/Haiku) | [console.anthropic.com](https://console.anthropic.com) |
| Must-Have | `OPENROUTER_API_KEY` | Model router (200+ models) | [openrouter.ai](https://openrouter.ai) |
| Must-Have | `PERPLEXITY_API_KEY` | Live web research | [docs.perplexity.ai](https://docs.perplexity.ai) |
| Must-Have | `PINECONE_API_KEY` | Semantic memory (free: 100K vectors) | [pinecone.io](https://www.pinecone.io) |
| **High-Impact** | `OPENAI_API_KEY` | Deep reasoning (o3-mini) + embeddings | [platform.openai.com](https://platform.openai.com) |
| High-Impact | `E2B_API_KEY` | Sandbox validation (free: 100 hrs/mo) | [e2b.dev](https://e2b.dev) |
| High-Impact | `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` | LLM tracing | [langfuse.com](https://langfuse.com) |
| **Edge** | `STRIPE_API_KEY` | Payment processing | [stripe.com](https://stripe.com) |

### Model Configuration

Override default models via environment variables:

```bash
MODEL_TRIAGE=anthropic/claude-3-haiku-20240307   # Fast classifier
MODEL_ENGINEER=anthropic/claude-sonnet-4-20250514       # Primary brain
MODEL_CRITIC=anthropic/claude-sonnet-4-20250514         # Quality gate
MODEL_REASONER=openai/o3-mini                    # Deep reasoning
```

---

## Usage

### CLI Mode

```bash
# General query (full orchestrator loop)
python src/orchestrator.py "Create a Terraform module for HA Azure VPN Gateway"

# The orchestrator will:
# 1. Triage → classify as ENGINEER route
# 2. Pull context from Pinecone + Perplexity
# 3. Engineer drafts the module
# 4. Critic validates in E2B sandbox
# 5. Retry if failed (max 3x)
# 6. Distill the experience to Pinecone
# 7. Output the final deliverable
```

### API Server

```bash
# Start the server
uvicorn src.api.main:app --reload --port 8000

# Your API key auto-generates at .secrets/api_keys.json on first run

# Example: generate a runbook
curl -X POST http://localhost:8000/v1/runbook \
  -H "Content-Type: application/json" \
  -H "X-API-Key: pa-YOUR_KEY_HERE" \
  -d '{"incident": "ADFS auth failing for external users", "severity": "High"}'
```

### Memory Ingest

```bash
# Dry run — see what would be ingested
python -m src.memory.ingest --source memory/ --dry-run

# Ingest PA memory files
python -m src.memory.ingest --source memory/

# Ingest an Obsidian vault
python -m src.memory.ingest --source /path/to/obsidian/vault

# Ingest with verbose logging
python -m src.memory.ingest --source memory/ -v
```

### Weekly Reports

```bash
# Generate weekly improvement report (saved to memory/)
python -m src.observability.weekly_report

# Analyze last 30 days
python -m src.observability.weekly_report 30
```

---

## API Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Health check + API key status |
| `GET` | `/usage` | API Key | Usage statistics |
| `POST` | `/v1/query` | API Key | General orchestrator query |
| `POST` | `/v1/runbook` | API Key | Generate incident runbook |
| `POST` | `/v1/terraform` | API Key | Generate validated Terraform module |
| `POST` | `/v1/security-audit` | API Key | Generate security audit report |
| `POST` | `/webhooks/stripe` | Stripe Sig | Billing webhook handler |
| `GET` | `/` | None | Client-facing web portal |
| `GET` | `/docs` | None | Interactive Swagger documentation |

**Rate limit:** 10 requests per 60-second window per API key.

---

## Services

### 📋 Incident Runbook Generator

Produces structured runbooks following the format:
**Problem → Symptoms → Impact → Root Cause → Fix → Verification → Prevention → Rollback**

- Recalls similar past incidents from Pinecone
- Researches latest docs via Perplexity
- All commands are copy-paste ready
- Auto-distills the resolution for future recall

### 🏗️ Terraform Module Builder

Generates production-ready Azure modules with:
- `main.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars.example`
- E2B sandbox validation (`terraform validate`)
- Azure CAF naming, lifecycle rules, diagnostic settings
- Full parameterization — no hardcoded values

### 🔒 Security Audit Report Generator

Creates comprehensive audit reports covering:
- RBAC and privileged group analysis
- Policy coverage gaps and CIS benchmark compliance
- Conditional access review
- Risk-prioritized remediation with PowerShell scripts
- Executive summary for leadership

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| LLM Interface | [litellm](https://github.com/BerriAI/litellm) | Unified API for Anthropic/OpenAI/OpenRouter |
| Vector Memory | [Pinecone](https://www.pinecone.io) + [OpenAI Embeddings](https://platform.openai.com) | Semantic search over past experiences |
| Sandbox | [E2B](https://e2b.dev) | Isolated code validation (Terraform, PowerShell) |
| Observability | [Langfuse](https://langfuse.com) | LLM call tracing, analytics, scoring |
| Web Research | [Perplexity](https://docs.perplexity.ai) | Real-time search grounded in latest docs |
| API Server | [FastAPI](https://fastapi.tiangolo.com) + [Uvicorn](https://www.uvicorn.org) | REST endpoints with auth and rate limiting |
| Billing | [Stripe](https://stripe.com) | Payment processing via webhooks |
| Models | Claude Sonnet (engineer/critic), Haiku (triage), o3-mini (reasoning) | Tiered by task complexity |

---

## Development Phases

### ✅ Phase 1 — Wire Up the Stubs
Replaced all stub implementations with real API integrations:
- `orchestrator.py` → 655-line multi-agent loop with litellm
- `search_perplexity.py` → Perplexity API + OpenRouter fallback
- `query_pinecone.py` → Full Pinecone client with auto-index creation
- `validate_terraform.py` → E2B sandbox with local fallback
- `config.py` → Centralized environment loader
- `.env.example` + `requirements.txt` + `.gitignore`
- Updated `AGENTS.md` and `TOOLS.md`

### ✅ Phase 2 — Semantic Memory Pipeline
Built the "remember everything" layer:
- `ingest.py` → Heading-aware chunking → embeddings → Pinecone bulk upsert (CLI with `--dry-run`)
- `distill.py` → Post-task LLM-compressed lessons with auto-categorization and daily batch processing

### ✅ Phase 3 — Observability & Self-Improvement
Built "The Mirror" for performance analysis:
- `tracer.py` → Dual-storage (Langfuse cloud + local JSONL) with context managers and decorators
- `weekly_report.py` → Automated analytics with failure patterns, cost trends, score analysis, and actionable recommendations
- Wired all 5 orchestrator nodes with trace spans

### ✅ Phase 4 — Productization
Exposed the agent as a paid service platform:
- 3 service modules (runbook, terraform, security audit) with memory recall and distillation
- FastAPI REST server with API key auth, rate limiting, and Stripe webhooks
- Client-facing web portal with premium dark UI
- Auto-generated API keys on first run

---

## Roadmap

| Priority | Feature | Status |
|----------|---------|--------|
| 🟢 | Core orchestrator (Triage → Engineer → Critic → Distill) | ✅ Complete |
| 🟢 | Semantic memory (Pinecone ingest + distillation) | ✅ Complete |
| 🟢 | Observability (Langfuse + weekly reports) | ✅ Complete |
| 🟢 | REST API + client portal | ✅ Complete |
| 🟡 | End-to-end test suite with live API keys | 🔜 Next |
| 🟡 | Obsidian vault + Notion ingestion testing | 🔜 Next |
| 🟡 | Stripe checkout flow + subscription management | 🔜 Next |
| 🟡 | Multi-tenant API key management (database-backed) | 📋 Planned |
| 🟡 | Firecrawl integration for vendor doc ingestion | 📋 Planned |
| 🟡 | Ansible playbook generation service | 📋 Planned |
| 🟡 | Client dashboard with usage analytics | 📋 Planned |
| 🟡 | Automated nightly memory maintenance cron | 📋 Planned |

---

## License

Private — © 2026 Rob Loftin / 143IT. All rights reserved.

---

*Last updated: 2026-02-21*
