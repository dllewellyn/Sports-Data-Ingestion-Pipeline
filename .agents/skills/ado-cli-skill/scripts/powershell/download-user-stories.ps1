#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ConfigFile = Join-Path $ScriptDir '.ado-cli-config'
$OutputDir = Join-Path $PWD 'user_stories'

function Ensure-Az {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw "Azure CLI (az) is not installed or not in PATH."
    }

    $ext = az extension show --name azure-devops 2>$null
    if (-not $ext) {
        Write-Host "Installing Azure DevOps extension..." -ForegroundColor Yellow
        az extension add --name azure-devops | Out-Null
    }
}

function Load-Config {
    if (-not (Test-Path $ConfigFile)) {
        throw "Configuration not found at $ConfigFile`nPlease run: ado-ticket.ps1 init"
    }

    $config = @{}
    Get-Content $ConfigFile | ForEach-Object {
        if ($_ -match '^([A-Z_]+)="?(.*?)"?\s*$') {
            $config[$Matches[1]] = $Matches[2]
        }
    }

    if (-not $config['ORG'] -or -not $config['PROJECT']) {
        throw "Invalid configuration. Please run: ado-ticket.ps1 init"
    }

    return @{
        Org     = $config['ORG']
        Project = $config['PROJECT']
    }
}

Ensure-Az
$config = Load-Config
$Org = $config.Org
$Project = $config.Project

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "Fetching user story IDs from $Project..." -ForegroundColor Cyan

$wiql = "Select [System.Id] From WorkItems Where [System.WorkItemType] = 'User Story' And [System.TeamProject] = @project Order By [System.ChangedDate] Desc"

$queryResult = az boards query `
    --wiql $wiql `
    --organization $Org `
    --project $Project `
    --output json | ConvertFrom-Json

if (-not $queryResult -or $queryResult.Count -eq 0) {
    Write-Host "No user stories found." -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($queryResult.Count) user stories. Downloading..." -ForegroundColor Cyan

$count = 0
foreach ($item in $queryResult) {
    $id = $item.id
    $outFile = Join-Path $OutputDir "$id.json"
    az boards work-item show `
        --id $id `
        --organization $Org `
        --project $Project `
        --output json | Set-Content -Path $outFile -Encoding UTF8
    Write-Host "  ✓ $id → user_stories/$id.json" -ForegroundColor Green
    $count++
}

Write-Host ""
Write-Host "✓ Downloaded $count user stories to $OutputDir" -ForegroundColor Green
