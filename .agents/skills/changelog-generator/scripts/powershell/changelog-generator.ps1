#!/usr/bin/env pwsh
# Discovery and status helper for the changelog-generator agent skill.
# Authoring of CHANGELOG.md is performed by the agent (Claude) — this script
# handles file-system queries only: which commits in temp/ are not yet logged.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$GitRoot      = (git -C $ScriptDir rev-parse --show-toplevel 2>$null) ?? $ScriptDir
$GitRoot      = $GitRoot.Trim()
$TempBase     = Join-Path $GitRoot 'temp'
$Changelog    = Join-Path $GitRoot 'CHANGELOG.md'
$CommitFilter = ''

function Show-Usage {
    Write-Host @"
Usage: changelog-generator.ps1 <list|status> [options]

Commands:
  list     Print commits present in temp/ that are NOT yet in CHANGELOG.md
           (tab-separated: short_sha  manifest_path)
  status   Show logged vs pending commits

Detection: a commit is "logged" when CHANGELOG.md contains the marker
  <!-- okf:commit=<short_sha> -->
which the agent writes once per commit entry.

Options:
  -Commit <short_sha>    Scope to a single commit dir
  -Changelog <path>      CHANGELOG file (default: <repo_root>/CHANGELOG.md)
  -Temp <dir>            Temp base dir (default: <repo_root>/temp)
"@ -ForegroundColor Cyan
    exit 1
}

function Test-Logged {
    param([string]$ShortSha)
    if (-not (Test-Path $Changelog)) { return $false }
    return [bool](Select-String -Path $Changelog -Pattern "okf:commit=$ShortSha" -SimpleMatch -Quiet)
}

function Get-CommitDirs {
    if ($CommitFilter) {
        $target = Join-Path $TempBase $CommitFilter
        if (-not (Test-Path $target)) {
            Write-Error "Commit dir not found: $target"
            exit 1
        }
        return @($target)
    }
    return Get-ChildItem -Path $TempBase -Directory |
        Sort-Object Name |
        ForEach-Object { $_.FullName }
}

# ── Entry point ────────────────────────────────────────────────────────────────

$Action = if ($args.Count -ge 1) { $args[0] } else { 'list' }
$rest   = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

$i = 0
while ($i -lt $rest.Count) {
    switch ($rest[$i].ToLower()) {
        { $_ -in '-commit',    '--commit'    } { $CommitFilter = $rest[$i+1]; $i += 2 }
        { $_ -in '-changelog', '--changelog' } { $Changelog    = $rest[$i+1]; $i += 2 }
        { $_ -in '-temp',      '--temp'      } { $TempBase     = $rest[$i+1]; $i += 2 }
        { $_ -in '-h',         '--help'      } { Show-Usage }
        default { Write-Error "Unknown option: $($rest[$i])"; Show-Usage }
    }
}

switch ($Action.ToLowerInvariant()) {

    'list' {
        if (-not (Test-Path $TempBase)) {
            Write-Error "Temp directory not found: $TempBase"
            exit 1
        }

        $found = 0
        foreach ($commitDir in Get-CommitDirs) {
            $shortSha     = Split-Path -Leaf $commitDir
            $manifestPath = Join-Path $commitDir 'changed_files.json'
            if (-not (Test-Path $manifestPath)) { continue }

            if (-not (Test-Logged -ShortSha $shortSha)) {
                Write-Output "$shortSha`t$manifestPath"
                $found++
            }
        }

        if ($found -eq 0) {
            Write-Host "No pending commits — CHANGELOG.md is up to date." -ForegroundColor DarkGray
        }
    }

    'status' {
        if (-not (Test-Path $TempBase)) {
            Write-Error "Temp directory not found: $TempBase"
            exit 1
        }

        $totalPending = 0
        $totalLogged  = 0

        foreach ($commitDir in Get-CommitDirs) {
            $shortSha     = Split-Path -Leaf $commitDir
            $manifestPath = Join-Path $commitDir 'changed_files.json'
            if (-not (Test-Path $manifestPath)) { continue }

            if (Test-Logged -ShortSha $shortSha) {
                $totalLogged++
                Write-Host "  ✓ $shortSha" -ForegroundColor Green
            } else {
                $totalPending++
                Write-Host "  ○ $shortSha" -ForegroundColor Yellow
            }
        }

        Write-Host ""
        Write-Host "Changelog: $Changelog"
        Write-Host "Total: $totalLogged logged, $totalPending pending"
    }

    { $_ -in '-h', '--help', 'help' } { Show-Usage }

    default {
        Write-Error "Unknown command: $Action"
        Show-Usage
    }
}
