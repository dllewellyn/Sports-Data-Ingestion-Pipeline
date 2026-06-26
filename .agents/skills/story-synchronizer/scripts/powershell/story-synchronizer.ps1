#!/usr/bin/env pwsh
# Discovery and status helper for the story-synchronizer agent skill.
# Synthesis is performed by the agent (Claude) — this script handles file-system queries only.
# It never reads, edits, or deletes findings, user stories, or the changeset; it only reports state.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$GitRoot     = (git -C $ScriptDir rev-parse --show-toplevel 2>$null) ?? $ScriptDir
$GitRoot     = $GitRoot.Trim()
$TempBase    = Join-Path $GitRoot 'temp'
$StoriesDir  = Join-Path $GitRoot 'user_stories'

function Show-Usage {
    Write-Host @"
Usage: story-synchronizer.ps1 <status|findings|stories> [options]

Commands:
  status     Summary: counts of findings, user stories, and whether a changeset exists
  findings   List every extracted finding (tab-separated: sha  type  finding_file)
             type is "transcript" (extracted_*.json) or "architecture" (arch_extracted_*.json)
  stories    Report the user_stories dir state: "missing", "empty", or one line per story
             (tab-separated: id  filename)

Options:
  -Temp <dir>      Temp base dir holding the processors' output (default: <repo_root>/temp)
  -Stories <dir>   User stories dir (default: <repo_root>/user_stories)
"@ -ForegroundColor Cyan
    exit 1
}

function Get-Changeset { Join-Path $TempBase 'story_changeset.json' }

function Get-Findings {
    if (-not (Test-Path $TempBase)) { return @() }
    $results = @()
    foreach ($commitDir in (Get-ChildItem -Path $TempBase -Directory | Sort-Object Name)) {
        $shortSha = $commitDir.Name
        foreach ($f in (Get-ChildItem -Path $commitDir.FullName -File -Filter 'extracted_*.json' -ErrorAction SilentlyContinue)) {
            $results += [pscustomobject]@{ Sha = $shortSha; Type = 'transcript'; File = $f.FullName }
        }
        foreach ($f in (Get-ChildItem -Path $commitDir.FullName -File -Filter 'arch_extracted_*.json' -ErrorAction SilentlyContinue)) {
            $results += [pscustomobject]@{ Sha = $shortSha; Type = 'architecture'; File = $f.FullName }
        }
    }
    return $results
}

# ── Entry point ────────────────────────────────────────────────────────────────

$Action = if ($args.Count -ge 1) { $args[0] } else { 'status' }
$rest   = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

$i = 0
while ($i -lt $rest.Count) {
    switch ($rest[$i].ToLower()) {
        { $_ -in '-temp',    '--temp'    } { $TempBase   = $rest[$i+1]; $i += 2 }
        { $_ -in '-stories', '--stories' } { $StoriesDir = $rest[$i+1]; $i += 2 }
        { $_ -in '-h',       '--help'    } { Show-Usage }
        default { Write-Error "Unknown option: $($rest[$i])"; Show-Usage }
    }
}

switch ($Action.ToLowerInvariant()) {

    'findings' {
        $findings = Get-Findings
        if ($findings.Count -eq 0) {
            Write-Host "No findings. Run transcript-processor / architecture-processor first." -ForegroundColor DarkGray
            break
        }
        foreach ($r in $findings) { Write-Output "$($r.Sha)`t$($r.Type)`t$($r.File)" }
    }

    'stories' {
        if (-not (Test-Path $StoriesDir)) {
            Write-Output 'missing'
            break
        }
        $files = Get-ChildItem -Path $StoriesDir -File -Filter '*.json' -ErrorAction SilentlyContinue | Sort-Object Name
        if (-not $files -or $files.Count -eq 0) {
            Write-Output 'empty'
            break
        }
        foreach ($f in $files) {
            Write-Output "$([System.IO.Path]::GetFileNameWithoutExtension($f.Name))`t$($f.Name)"
        }
    }

    'status' {
        $findings    = Get-Findings
        $transcriptN = ($findings | Where-Object { $_.Type -eq 'transcript' }).Count
        $archN       = ($findings | Where-Object { $_.Type -eq 'architecture' }).Count

        if (-not (Test-Path $StoriesDir)) {
            $storiesState = 'missing (greenfield: propose new stories)'
        } else {
            $storyFiles = Get-ChildItem -Path $StoriesDir -File -Filter '*.json' -ErrorAction SilentlyContinue
            $storiesN   = if ($storyFiles) { $storyFiles.Count } else { 0 }
            if ($storiesN -eq 0) {
                $storiesState = 'empty (greenfield: propose new stories)'
            } else {
                $storiesState = "$storiesN story file(s) (update mode)"
            }
        }

        Write-Host "Findings"
        Write-Host "  transcript (extracted_*.json):    $transcriptN"
        Write-Host "  architecture (arch_extracted_*):  $archN"
        Write-Host ""
        Write-Host "User stories"
        Write-Host "  dir:    $StoriesDir"
        Write-Host "  state:  $storiesState"
        Write-Host ""
        $changeset = Get-Changeset
        if (Test-Path $changeset) {
            Write-Host "Changeset: EXISTS at $changeset (will be overwritten unless you intend otherwise)"
        } else {
            Write-Host "Changeset: not yet generated (target: $changeset)"
        }
    }

    { $_ -in '-h', '--help', 'help' } { Show-Usage }

    default {
        Write-Error "Unknown command: $Action"
        Show-Usage
    }
}
