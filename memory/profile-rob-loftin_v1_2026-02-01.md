# AI Agent Profile — Rob Loftin (v1.0)
Date: 2026-02-01

## Identity & Role
- Name: Rob Loftin ("uncle rob")
- Title: Senior IT Infrastructure & Cloud Consultant
- Experience: 20+ years (Dell field tech → financial services → startups → MSP leadership)
- Company: 143IT (MSP) | Domain: 143it.com | support@143it.com
- Team: leads ~8–10 specialists
- Scope: ~500+ endpoints | ~600+ servers | hybrid Azure + on-prem
- Primary clients: GR Energy, McLeod

## Environment / Stack
- OS: Windows Server (primary), Linux (syslog/secondary)
- Cloud: Microsoft Azure (hybrid)
- Identity: Entra ID + on-prem AD
- Virtualization: Hyper-V, Azure VMs
- Monitoring: LogicMonitor
- Networking: Azure vNets, NSGs, Azure Bastion

## Automation / DevOps
- IaC: Terraform, Ansible (WinRM)
- Scripting: PowerShell (primary), Bash
- Workflow automation: n8n at https://n8n.srv659289.hstgr.cloud/
- CI/CD: Azure DevOps Pipelines → transitioning to GitHub Actions
- VCS: GitHub Enterprise Cloud (implementing; Entra integration)

## AI / MCP
- MCP servers: Azure, GitHub, Notion, Obsidian, Context7, Perplexity, Playwright (+ n8n via supergateway)
- n8n MCP note: supergateway streamableHttp + Bearer token; workflows require MCP access enabled in n8n

## Documentation Systems
- Notion: “Incident HeadQuarter” database (primary incident tracking)
- Obsidian vault: /Users/me/Documents/Universal_Vault (KB under 2-KB-Articles/)
- GitHub: repos for IaC/automation/project artifacts

## Active Projects (status as of 2026-02-01)
1) Context-Aware Infrastructure Assistant
   - Artifact created 2025-12-28; MVP pending
   - Goal: answer infra questions <30s via parallel MCP queries (Notion + Azure + Obsidian)
   - Next: repo, data source inventory, 3 query patterns, MVP build (1–2h), test 5 scenarios

2) GitHub Enterprise Cloud + Entra ID Integration
   - In progress; 8-component effort
   - Pain points: SAML attribute mapping, conditional access conflicts, team sync, branch protection, repo visibility
   - Approach: 4 phases (Planning → Foundation → Security → Migration/Testing)

3) Azure Infrastructure Migration Framework
   - 690-line framework doc created 2026-02-01 (Notion + Markdown)
   - Includes governance→subscription resources; integrates Terraform/Ansible/GHEC; includes CVE-2025-49752 Bastion findings

4) MSP Incident Response Skill
   - Built/tested 2026-01-16; prod-ready
   - Validated on Event ID 23 / Kerberos KDC (JE-PRD-ADDS-002) matched prior incident LME34780240

5) n8n Email Automation (Gmail categorization)
   - Designed + JSON created 2025-12-25
   - Poll 5m → Claude Sonnet 4.5 categorize → labels → optional Notion logging

6) Rapid Incident Response Claude Project
   - Production; documentation time 42m → 3m

7) Multi-LLM Orchestration Framework
   - Architecture designed 2025-11; 50+ page doc
   - Python/AsyncIO, GitPython, multi-provider APIs, Vault; Typer+Rich UI

## Personal / Other
- Roblox FPS tutorial for child: complete 2026-01-18; 75+ page guide; intends to share publicly

## PowerShell Library (notable)
- INC0615134_WinRM_Investigation.ps1
- Fix-NTLMAuth.ps1
- Diagnose-AzureADAppForLogicMonitor.ps1
- New-AzureADAppSecret.ps1
- Get-AdminSDHolderProtectedUsers.ps1
- Remove-OrphanedAdminCount.ps1
- Test-DomainAccess.ps1
- CVE-2025-49752 verification scripts
- GR Energy Term Hold script analysis

## Priorities (next)
1) Context-aware assistant MVP
2) GHEC + Entra ID unblock
3) Azure migration framework walkthrough/execution planning
4) Investment rebalancing (add Healthcare/Industrials)
5) n8n email automation production test
6) Multi-LLM orchestration (longer-term)
