# USER.md - About Your Human (Updated)

> Living profile for working sessions: preferences, context, toolchain, and “how we execute”.

## Identity

- **Name:** Rob Loftin
- **Preferred name / how to address:** Daddy (or Rob / Uncle Rob—use whichever matches the tone of the moment)
- **Pronouns:** (unspecified)
- **Timezone:** America/Toronto
- **Assistant nickname:** “side kick”

## Operating style (how to be useful)

- **Direct + technical.** Precision > politeness. No fluff.
- **Automation-first.** Reusable tooling, idempotent runs, safe defaults, rollback paths.
- **Documentation-first.** Every change/incident should produce a runbook/checklist + evidence artifacts.
- **Deliverables matter.** Prefer deployable outputs: `.ps1`, `.tf`, diagrams, checklists, Word/PDF, Markdown KB pages, CSV/JSON exports.
- **Assume senior context.** Skip beginner explanations unless asked.
- **Structure preference:** Markdown with clear headings, checklists, and copy/paste blocks.

## Role & scope

- **Primary role:** Senior IT Infrastructure & Cloud Consultant (MSP)
- **Experience:** 20+ years (Dell field tech → financial services → startups → MSP leadership)
- **Leadership:** Often leads ~8–10 specialists
- **Typical footprint:** ~500+ endpoints / ~600+ servers across hybrid environments
- **Common responsibilities:** AD/Entra, Azure, virtualization, patching, backups, monitoring, security ops coordination, automation enablement

## Current focus areas (last ~6 months)

- **Azure mastery & governance**
  - Tenant/subscription inventory, baseline governance (MGs/Policy/RBAC), operational hygiene
- **DevOps & automation**
  - Jenkins + Groovy, Azure DevOps Pipelines, transitioning to GitHub Actions
  - IaC with Terraform (Azure-first); configuration automation with Ansible (WinRM)
  - Building “one-button” operational automations (safe + auditable)
- **Identity depth**
  - Entra Connect / ADFS / Kerberos fundamentals; AD architecture/domain design
- **AI in IT ops**
  - AI-assisted incident/runbook generation
  - Building a personal MSP ops dashboard (“Second Brain” + automation orchestration)
  - n8n-based workflows (daily/weekly summaries, Notion sync, email reporting)
- **Professional leverage**
  - Resume/portfolio upgrades, Fiverr/consulting positioning, measurable impact projects
- **Side ventures (secondary)**
  - Transportation/tour service ops + web presence (when relevant)

## Technical stack (common environment)

### Cloud / identity / compute
- **Azure:** Hybrid Azure + on-prem; Azure VMs, vNets/NSGs, Bastion, Key Vault, Update Manager
- **Identity:** Entra ID + on-prem AD; (ADFS topics come up)
- **Virtualization:** Hyper-V (primary), plus Azure VMs

### Monitoring / security / ops tooling
- **Monitoring:** LogicMonitor
- **Security:** SOC coordination + hardening tasks; server security policies; privileged group hygiene

### Automation / engineering toolchain
- **Primary scripting:** PowerShell
- **Secondary:** Bash, Python (as needed), Terraform, Ansible (WinRM)
- **CI/CD:** Azure DevOps Pipelines → transitioning to GitHub Actions
- **Source control:** GitHub (including Enterprise Cloud plans + Entra integration work)
- **Workflow automation:** n8n (self-hosted)
  - Instance: https://n8n.srv659289.hstgr.cloud/

## Documentation & knowledge systems

- **Notion:** “Incident HeadQuarter” (incident tracking hub + templates)
- **Obsidian vault:** `/Users/me/Documents/Universal_Vault` (KB under `2-KB-Articles/`)
- **GitHub repos:** IaC / automation / project artifacts; reusable script library + KB exports

## Standard outputs (what “done” looks like)

- **Incident → Runbook workflow**
  - Problem statement, symptoms, impact, root cause, fix, prevention
  - Evidence: logs/screenshots/exports
  - A repeatable checklist + a reusable script (if applicable)
- **Automation deliverables**
  - Parameters, logging, error handling, safe defaults
  - Output: CSV/JSON/HTML/Markdown reports
  - Clear rollback/undo notes
- **Governance deliverables**
  - RBAC matrix, policy baseline, naming/tagging standards, subscription placement rules

## Common client/environment themes

- Hybrid Windows-heavy estates with Azure integration
- AD/Entra identity hygiene, patching reliability, monitoring coverage, and rapid incident resolution

## Topics that come up often

- Windows Server discovery and documentation (domain-wide inventory)
- AD architecture / privileged groups / GPOs / DHCP/DNS
- Azure subscription onboarding and baseline governance
- Patching strategy (WSUS vs Azure Update Manager vs PSWindowsUpdate)
- Key Vault certificates and certificate lifecycle management
- Automation orchestration (n8n, pipelines), “daily brief” dashboards

---

*This file should be updated whenever priorities, clients, or tooling shifts materially.*
