---
name: ado-cli-skill
description: Deterministic Azure DevOps work-item operations (init, get, list via WIQL, create, update) plus bulk download of user stories to local user_stories/<id>.json, via the az CLI from Bash or PowerShell. Use when asked to read, query, create, update, or download Azure DevOps tickets/work items.
compatibility: Requires the Azure CLI (az) with the azure-devops extension (auto-installed if missing) and an authenticated Azure DevOps org; bulk download needs jq.
---

# Skill: Azure DevOps Ticket CLI Operator

## Purpose

Provide deterministic, scriptable operations for Azure DevOps work items using Azure CLI from either Bash or PowerShell.

## When invoked

This is a **deterministic CLI** — the script already implements everything below. Your job is to **run the right subcommand and report the result**, not to build or change it.

1. Map the user's request to a subcommand (`init`, `get`, `list`, `create`, `update`, or the bulk `download-user-stories`) and run the entrypoint:
   ```bash
   ./scripts/bash/ado-ticket.sh <subcommand> [--flags]        # or the .ps1 equivalent
   ```
2. If `.ado-cli-config` is missing, run `init` first (see Initialization).
3. Pass the user's arguments through to the matching flags (see Operation Mapping) and report the command's output — the created/updated ID, the listed items, or the fetched fields.

**Do NOT** read, audit, "verify against the contract", or edit the scripts unless the user explicitly asks you to change the tool itself. Everything below is the **behavioural contract the script already satisfies** — reference material, not a task list.

## Capabilities

- **Initialize** configuration (org/project)
- Read ticket by ID
- List tickets via WIQL query
- Create ticket (type/title/description)
- Update ticket fields

## Required Tools

- `az` CLI
- `az` extension: `azure-devops`

## Initialization

**Required on first use.** The CLI stores organization and project in `.ado-cli-config` at the project root.

### First-time setup:

```bash
# Bash
./scripts/bash/ado-ticket.sh init

# PowerShell
./scripts/powershell/ado-ticket.ps1 init
```

This prompts you for:
- Azure DevOps organization URL (e.g., `https://dev.azure.com/myorg`)
- Project name

Configuration is saved to `.ado-cli-config` (project root).

### Re-initialize configuration:

Run `init` again anytime to update stored org/project.

## Command Entrypoints

- Bash: `scripts/bash/ado-ticket.sh`
- PowerShell: `scripts/powershell/ado-ticket.ps1`
- Download user stories (Bash): `scripts/bash/download-user-stories.sh`
- Download user stories (PowerShell): `scripts/powershell/download-user-stories.ps1`

## Operation Mapping

- Initialize:
  - Bash: `ado-ticket.sh init`
  - PowerShell: `ado-ticket.ps1 init`
- Read one ticket:
  - Bash: `ado-ticket.sh get --id <id>`
  - PowerShell: `ado-ticket.ps1 get -Id <id>`
- Read many tickets:
  - Bash: `ado-ticket.sh list [--wiql <query>]`
  - PowerShell: `ado-ticket.ps1 list [-Wiql <query>]`
- Create ticket:
  - Bash: `ado-ticket.sh create --type <type> --title <title> [--description <text>]`
  - PowerShell: `ado-ticket.ps1 create -Type <type> -Title <title> [-Description <text>]`
- Update ticket:
  - Bash: `ado-ticket.sh update --id <id> --field "System.State=Active"`
  - PowerShell: `ado-ticket.ps1 update -Id <id> -Field "System.State=Active"`

- Download all user stories:
  - Bash: `download-user-stories.sh` (requires `jq`)
  - PowerShell: `download-user-stories.ps1`
  - Writes one `user_stories/<id>.json` file per story to the current working directory

## Output Conventions

- Default output is `json`.
- Use `table` for human readability.
- Prefer `json` for automation.

## Configuration Override

All operations (except `init`) support CLI overrides for org/project:

```bash
# Override org/project from CLI
./scripts/bash/ado-ticket.sh list --org https://dev.azure.com/other-org --project other-project
```

The config file values are used as defaults if not overridden.

## Guardrails

- Configuration is **required** before any operation.
- Never print secrets or tokens.
- Fail fast when required arguments are missing.
- Configuration is loaded from `.ado-cli-config` — this file should not be shared or committed to version control.
- Config format is `KEY="VALUE"` (plain text), readable by both Bash (`source`) and PowerShell (parsed line-by-line). Do not edit manually.
- Surface Azure CLI errors verbatim for troubleshooting.
