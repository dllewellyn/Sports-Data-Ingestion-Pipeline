# Azure DevOps CLI Skill

A deterministic, scriptable CLI for Azure DevOps work item operations.

## Quick Start

### 1. Initialize Configuration

Run this once to store your organization and project:

```bash
./scripts/bash/ado-ticket.sh init
```

Or on PowerShell:

```powershell
./scripts/powershell/ado-ticket.ps1 init
```

### 2. List Open Tickets

```bash
./scripts/bash/ado-ticket.sh list
```

### 3. Get a Specific Ticket

```bash
./scripts/bash/ado-ticket.sh get --id 12345
```

### 4. Create a Ticket

```bash
./scripts/bash/ado-ticket.sh create --type "User Story" --title "My Feature" --description "Details here"
```

### 5. Update a Ticket

```bash
./scripts/bash/ado-ticket.sh update --id 12345 --field "System.State=Active"
```

## Documentation

See [SKILL.md](./SKILL.md) for complete API documentation.

## Requirements

- Azure CLI (`az`)
- Azure DevOps extension for Azure CLI
- Bash 4+ (for Bash scripts) or PowerShell 5+ (for PowerShell scripts)

## Scripts

- **Bash**: `scripts/bash/ado-ticket.sh`
- **PowerShell**: `scripts/powershell/ado-ticket.ps1`

## Configuration

Configuration is stored in `.ado-cli-config` at the project root. This file should not be committed to version control.

## License

Proprietary
