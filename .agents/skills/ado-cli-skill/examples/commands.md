# Azure DevOps CLI Examples

## Prerequisites

Initialize the CLI first:

```bash
./scripts/bash/ado-ticket.sh init
```

## Common Operations

### List all tickets in a project

```bash
./scripts/bash/ado-ticket.sh list
```

### List only open tickets

```bash
./scripts/bash/ado-ticket.sh list --wiql \
  "Select [System.Id], [System.Title], [System.State] From WorkItems \
   Where [System.State] <> 'Done' AND [System.State] <> 'Closed' \
   Order By [System.ChangedDate] Desc"
```

### Get a single ticket

```bash
./scripts/bash/ado-ticket.sh get --id 42
```

### Create a bug

```bash
./scripts/bash/ado-ticket.sh create \
  --type "Bug" \
  --title "Login page broken on Safari" \
  --description "Users report login fails on Safari 15+"
```

### Create a user story with description

```bash
./scripts/bash/ado-ticket.sh create \
  --type "User Story" \
  --title "Add dark mode support" \
  --description "As a user, I want to enable dark mode for comfortable nighttime browsing"
```

### Update ticket state

```bash
./scripts/bash/ado-ticket.sh update \
  --id 42 \
  --field "System.State=Active"
```

### Update multiple fields

```bash
./scripts/bash/ado-ticket.sh update \
  --id 42 \
  --field "System.State=Resolved" \
  --field "System.AssignedTo=john@example.com"
```

## PowerShell Examples

All commands support PowerShell equivalents with `-` prefix:

```powershell
./scripts/powershell/ado-ticket.ps1 init
./scripts/powershell/ado-ticket.ps1 get -Id 42
./scripts/powershell/ado-ticket.ps1 create -Type "Bug" -Title "Issue" -Description "Details"
./scripts/powershell/ado-ticket.ps1 update -Id 42 -Field "System.State=Active"
```

## Override Organization/Project

To use different org/project than configured:

```bash
./scripts/bash/ado-ticket.sh list \
  --org "https://dev.azure.com/other-org" \
  --project "other-project"
```

## Output Formats

### JSON (default)

```bash
./scripts/bash/ado-ticket.sh list
```

### Table format

```bash
./scripts/bash/ado-ticket.sh list --output table
```

## WIQL Query Examples

### Bugs assigned to current user

```bash
./scripts/bash/ado-ticket.sh list --wiql \
  "Select [System.Id], [System.Title], [System.AssignedTo] From WorkItems \
   Where [System.WorkItemType] = 'Bug' AND [System.AssignedTo] = @Me"
```

### High-priority tasks due this sprint

```bash
./scripts/bash/ado-ticket.sh list --wiql \
  "Select [System.Id], [System.Title], [System.Priority] From WorkItems \
   Where [System.Priority] = 1 AND [System.IterationPath] = @CurrentIteration"
```

### Recently modified items

```bash
./scripts/bash/ado-ticket.sh list --wiql \
  "Select [System.Id], [System.Title], [System.ChangedDate] From WorkItems \
   Where [System.ChangedDate] > @Today - 7 \
   Order By [System.ChangedDate] Desc"
```
