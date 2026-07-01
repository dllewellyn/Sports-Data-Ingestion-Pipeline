#!/usr/bin/env pwsh
# Discovery and status helper for the architecture-processor agent skill.
# Extraction is performed by the agent (Claude) — this script handles file-system queries only.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$GitRoot      = (git -C $ScriptDir rev-parse --show-toplevel 2>$null) ?? $ScriptDir
$GitRoot      = $GitRoot.Trim()
$TempBase     = Join-Path $GitRoot 'temp'
$CommitFilter = ''
$PathFilter   = 'architecture'   # default: only architecture files

# Output prefix — distinct from transcript-processor's "extracted_" so both skills coexist
$OutPrefix = 'arch_extracted_'

function Show-Usage {
    Write-Host @"
Usage: architecture-processor.ps1 <list|status> [options]

Commands:
  list     Print pending new_* files (tab-separated: sha  flat_path  source_path)
  status   Show done vs pending counts per commit

Options:
  -Commit <short_sha>   Scope to a single commit dir
  -Filter <substring>   Override the default "architecture" filter
  -Temp <dir>           Temp base dir (default: <repo_root>/temp)
"@ -ForegroundColor Cyan
    exit 1
}

function Get-ExtractedPath {
    param([string]$NewFilePath)
    $dir  = Split-Path -Parent $NewFilePath
    $base = Split-Path -Leaf $NewFilePath
    $stem = $base -replace '^new_', ''
    return Join-Path $dir "${OutPrefix}${stem}.json"
}

function Get-OriginalPath {
    param([string]$FlatBase)
    # new_architecture__payment-service.puml -> architecture/payment-service.puml
    return ($FlatBase -replace '^new_', '') -replace '__', '/'
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

function Get-NewFiles {
    param([string]$CommitDir)
    $files = Get-ChildItem -Path $CommitDir -File |
        Where-Object { $_.Name -like 'new_*' -and $_.Extension -ne '.json' }
    if ($PathFilter) {
        $files = $files | Where-Object { $_.Name -like "*$PathFilter*" }
    }
    return $files
}

# ── Entry point ────────────────────────────────────────────────────────────────

$Action = if ($args.Count -ge 1) { $args[0] } else { 'list' }
$rest   = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

# Parse shared options
$i = 0
while ($i -lt $rest.Count) {
    switch ($rest[$i].ToLower()) {
        { $_ -in '-commit',  '--commit'  } { $CommitFilter = $rest[$i+1]; $i += 2 }
        { $_ -in '-filter',  '--filter'  } { $PathFilter   = $rest[$i+1]; $i += 2 }
        { $_ -in '-temp',    '--temp'    } { $TempBase     = $rest[$i+1]; $i += 2 }
        { $_ -in '-h',       '--help'    } { Show-Usage }
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

            foreach ($f in Get-NewFiles -CommitDir $commitDir) {
                $outFile = Get-ExtractedPath -NewFilePath $f.FullName
                if (-not (Test-Path $outFile)) {
                    $orig = Get-OriginalPath -FlatBase $f.Name
                    Write-Output "$shortSha`t$($f.Name)`t$orig"
                    $found++
                }
            }
        }

        if ($found -eq 0) {
            Write-Host "No pending files." -ForegroundColor DarkGray
        }
    }

    'status' {
        if (-not (Test-Path $TempBase)) {
            Write-Error "Temp directory not found: $TempBase"
            exit 1
        }

        $totalPending = 0
        $totalDone    = 0

        foreach ($commitDir in Get-CommitDirs) {
            $shortSha     = Split-Path -Leaf $commitDir
            $manifestPath = Join-Path $commitDir 'changed_files.json'
            if (-not (Test-Path $manifestPath)) { continue }

            $commitPending = 0
            $commitDone    = 0

            foreach ($f in Get-NewFiles -CommitDir $commitDir) {
                $outFile = Get-ExtractedPath -NewFilePath $f.FullName
                $orig    = Get-OriginalPath -FlatBase $f.Name
                if (Test-Path $outFile) {
                    $commitDone++
                    Write-Host "  ✓ $orig" -ForegroundColor Green
                } else {
                    $commitPending++
                    Write-Host "  ○ $orig" -ForegroundColor Yellow
                }
            }

            if (($commitPending + $commitDone) -gt 0) {
                Write-Host "$shortSha  ($commitDone done, $commitPending pending)"
            }

            $totalPending += $commitPending
            $totalDone    += $commitDone
        }

        Write-Host ""
        Write-Host "Total: $totalDone done, $totalPending pending"
    }

    { $_ -in '-h', '--help', 'help' } { Show-Usage }

    default {
        Write-Error "Unknown command: $Action"
        Show-Usage
    }
}
