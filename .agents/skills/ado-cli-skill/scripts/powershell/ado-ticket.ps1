#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Configuration file location
$ScriptDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ConfigFile = Join-Path $ScriptDir '.ado-cli-config'

if ($args.Count -lt 1) {
    Write-Error "Usage: ./ado-ticket.ps1 <init|get|list|create|update> [options]"
    exit 1
}

$Action = $args[0]
$remaining = @()
if ($args.Count -gt 1) {
    $remaining = $args[1..($args.Count - 1)]
}

function Ensure-Az {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw "Azure CLI (az) is not installed or not in PATH."
    }

    $ext = az extension show --name azure-devops 2>$null
    if (-not $ext) {
        Write-Host "Installing Azure DevOps extension..."
        az extension add --name azure-devops | Out-Null
    }
}

function Test-AzLogin {
    $account = az account show 2>$null
    if (-not $account) {
        throw "Not logged in to Azure CLI. Run: az login"
    }
    Write-Host "✓ Azure CLI found and authenticated" -ForegroundColor Green
}

function Load-Config {
    if (-not (Test-Path $ConfigFile)) {
        throw "Configuration not found at $ConfigFile`nPlease run: $($MyInvocation.ScriptName) init"
    }

    $config = @{}
    Get-Content $ConfigFile | ForEach-Object {
        if ($_ -match '^([A-Z_]+)="?(.*?)"?\s*$') {
            $config[$Matches[1]] = $Matches[2]
        }
    }

    if (-not $config['ORG'] -or -not $config['PROJECT']) {
        throw "Invalid configuration. Please run: $($MyInvocation.ScriptName) init"
    }

    return @{
        Org     = $config['ORG']
        Project = $config['PROJECT']
    }
}

function Init-Config {
    Test-AzLogin
    Write-Host "=== Azure DevOps CLI Initialization ===" -ForegroundColor Cyan

    $org = Read-Host "Enter your Azure DevOps organization URL (e.g., https://dev.azure.com/myorg)"
    $project = Read-Host "Enter your project name"

    if (-not $org -or -not $project) {
        throw "Error: Organization and project are required"
    }

    $configContent = @"
# Azure DevOps CLI Configuration
# Generated: $(Get-Date -Format 'u')
ORG="$org"
PROJECT="$project"
"@

    Set-Content -Path $ConfigFile -Value $configContent -Encoding UTF8
    Write-Host "✓ Configuration saved to $ConfigFile" -ForegroundColor Green
}

function Parse-Common {
    param(
        [string[]]$InputArgs
    )

    $result = [ordered]@{
        Org      = $null
        Project  = $null
        Output   = 'json'
        Remaining = @()
    }

    $i = 0
    while ($i -lt $InputArgs.Count) {
        switch ($InputArgs[$i]) {
            '--org' {
                $result.Org = $InputArgs[$i + 1]
                $i += 2
            }
            '--project' {
                $result.Project = $InputArgs[$i + 1]
                $i += 2
            }
            '--output' {
                $result.Output = $InputArgs[$i + 1]
                $i += 2
            }
            default {
                $result.Remaining = $InputArgs[$i..($InputArgs.Count - 1)]
                return $result
            }
        }
    }

    return $result
}

function Build-ScopeArgs {
    param(
        [string]$Org,
        [string]$Project
    )

    $scope = @()
    if ($Org) {
        $scope += @('--organization', $Org)
    }
    if ($Project) {
        $scope += @('--project', $Project)
    }
    return $scope
}

function Invoke-Get {
    param(
        [string[]]$InputArgs,
        [string[]]$Scope,
        [string]$Output
    )

    $id = $null
    for ($i = 0; $i -lt $InputArgs.Count; $i++) {
        switch ($InputArgs[$i]) {
            '--id' {
                $id = $InputArgs[$i + 1]
                $i++
            }
            '-Id' {
                $id = $InputArgs[$i + 1]
                $i++
            }
            default {
                throw "Unknown argument for get: $($InputArgs[$i])"
            }
        }
    }

    if (-not $id) {
        throw "Missing required argument: --id or -Id"
    }

    az boards work-item show --id $id @Scope --output $Output
}

function Invoke-List {
    param(
        [string[]]$InputArgs,
        [string[]]$Scope,
        [string]$Output
    )

    $wiql = 'Select [System.Id], [System.Title], [System.State] From WorkItems Where [System.TeamProject] = @project Order By [System.ChangedDate] Desc'

    for ($i = 0; $i -lt $InputArgs.Count; $i++) {
        switch ($InputArgs[$i]) {
            '--wiql' {
                $wiql = $InputArgs[$i + 1]
                $i++
            }
            '-Wiql' {
                $wiql = $InputArgs[$i + 1]
                $i++
            }
            default {
                throw "Unknown argument for list: $($InputArgs[$i])"
            }
        }
    }

    az boards query --wiql $wiql @Scope --output $Output
}

function Invoke-Create {
    param(
        [string[]]$InputArgs,
        [string[]]$Scope,
        [string]$Output
    )

    $type = $null
    $title = $null
    $description = $null

    for ($i = 0; $i -lt $InputArgs.Count; $i++) {
        switch ($InputArgs[$i]) {
            '--type' { $type = $InputArgs[$i + 1]; $i++ }
            '-Type' { $type = $InputArgs[$i + 1]; $i++ }
            '--title' { $title = $InputArgs[$i + 1]; $i++ }
            '-Title' { $title = $InputArgs[$i + 1]; $i++ }
            '--description' { $description = $InputArgs[$i + 1]; $i++ }
            '-Description' { $description = $InputArgs[$i + 1]; $i++ }
            default { throw "Unknown argument for create: $($InputArgs[$i])" }
        }
    }

    if (-not $type -or -not $title) {
        throw "Missing required arguments: --type/-Type and --title/-Title"
    }

    $cmd = @('boards', 'work-item', 'create', '--type', $type, '--title', $title)
    if ($description) {
        $cmd += @('--description', $description)
    }
    $cmd += $Scope
    $cmd += @('--output', $Output)

    az @cmd
}

function Invoke-Update {
    param(
        [string[]]$InputArgs,
        [string[]]$Scope,
        [string]$Output
    )

    $id = $null
    $fields = @()

    for ($i = 0; $i -lt $InputArgs.Count; $i++) {
        switch ($InputArgs[$i]) {
            '--id' { $id = $InputArgs[$i + 1]; $i++ }
            '-Id' { $id = $InputArgs[$i + 1]; $i++ }
            '--field' { $fields += $InputArgs[$i + 1]; $i++ }
            '-Field' { $fields += $InputArgs[$i + 1]; $i++ }
            default { throw "Unknown argument for update: $($InputArgs[$i])" }
        }
    }

    if (-not $id) {
        throw "Missing required argument: --id or -Id"
    }

    if ($fields.Count -eq 0) {
        throw "At least one --field/-Field key=value is required"
    }

    $cmd = @('boards', 'work-item', 'update', '--id', $id)
    foreach ($field in $fields) {
        $cmd += @('--fields', $field)
    }
    $cmd += $Scope
    $cmd += @('--output', $Output)

    az @cmd
}

Ensure-Az

# Handle init action separately (doesn't need config)
if ($Action -eq 'init') {
    Init-Config
    exit 0
}

# For all other actions, load config
$config = Load-Config
$org = $config.Org
$project = $config.Project

$parsed = Parse-Common -InputArgs $remaining

# Allow org/project override via CLI args, otherwise use config
if (-not $parsed.Org) {
    $parsed.Org = $org
}
if (-not $parsed.Project) {
    $parsed.Project = $project
}

# Validate config
if (-not $parsed.Org -or -not $parsed.Project) {
    throw "Organization and project must be configured`nRun: $($MyInvocation.ScriptName) init"
}

$scope = Build-ScopeArgs -Org $parsed.Org -Project $parsed.Project

switch ($Action.ToLowerInvariant()) {
    'get' {
        Invoke-Get -InputArgs $parsed.Remaining -Scope $scope -Output $parsed.Output
    }
    'list' {
        Invoke-List -InputArgs $parsed.Remaining -Scope $scope -Output $parsed.Output
    }
    'create' {
        Invoke-Create -InputArgs $parsed.Remaining -Scope $scope -Output $parsed.Output
    }
    'update' {
        Invoke-Update -InputArgs $parsed.Remaining -Scope $scope -Output $parsed.Output
    }
    default {
        throw "Unsupported action: $Action. Supported actions: init, get, list, create, update"
    }
}
