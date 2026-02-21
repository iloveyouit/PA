# MEMORY.md - Long-term Memory (Curated)

## People
- **User:** “uncle rob” (Rob Loftin) — Senior IT Infrastructure & Cloud Consultant at 143IT (MSP); leads ~8–10 specialists

## Preferences
- User calls the assistant: **“side kick”**
- Assistant vibe preference: **super-brief**
- Assistant signature emoji: 🦅
- User prefers: direct, technical, structured answers; automation-first; deployable solutions; no vague advice; no beginner explanations unless requested

## Work / Stack (high level)
- Hybrid Azure + on-prem; Windows Server primary; Entra ID + AD; Hyper-V; LogicMonitor; Azure networking (vNet/NSG/Bastion)
- Automation: PowerShell, Terraform, Ansible (WinRM), n8n; GitHub Enterprise Cloud in implementation (Entra integration); moving ADO Pipelines → GitHub Actions
- Docs: Notion “Incident HeadQuarter”; Obsidian vault; GitHub repos for artifacts

## Current priorities (as of 2026-02-01)
1) Context-aware infrastructure assistant MVP (parallel MCP queries: Notion + Azure + Obsidian)
2) GitHub Enterprise Cloud + Entra ID integration unblock
3) Azure migration framework rollout
4) n8n Gmail categorization automation (prod test)

## Reference dumps
- Full profile dump: memory/profile-rob-loftin_v1_2026-02-01.md

## Setup
- Workspace initialized on 2026-02-01.

## OpenClaw Token Cost Optimization — Engineering Standard v2.0
- Daily awareness of guidelines covering session hygiene, /compact at 60%, /new flushing, and memoryFlush=true to preserve sensitive details.
- Keep bootstrap injections lean (<5k tokens, <2k tokens per bootstrap file); move procedural docs into skills; audit with /context detail.
- Output discipline: no filler, only report exceptions/results, and use concise one-line statuses for progress.
- Heartbeat/cron architecture: avoid LLM polling, rely on local scripts for checking, align intervals with cache TTL, run monitoring in isolated sessions.
- Model routing tiers: flash-lite for triage, haiku for summarization, sonnet for engineering, opus for deep debugging (spawn sub-agent when needed).
- Tool/sub-agent handling: delegate heavy directory/log exploration to /spawn; restrict outputs to manageable slices and summarize returns.
- Prompt caching: keep system prompts/static header stable, set cacheRetention long, and avoid frequent top-of-file edits.
- Loop/runaway mitigation: cap retries to 3, enforce wallet/session spend limits, require 24h attended mode before enabling always-on.
- Thinking models default off (enabled only for complex refactors/architecture); ensure usage visibility via /usage footer settings.

## Secrets
- Store secrets under .secrets/ (e.g., .secrets/openrouter_api_key.txt with chmod 600); record paths here for future reference.
