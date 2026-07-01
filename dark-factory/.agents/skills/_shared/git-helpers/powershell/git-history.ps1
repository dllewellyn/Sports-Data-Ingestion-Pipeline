#!/usr/bin/env pwsh
# Read-only git history walker — shared by missing-specification.
# PowerShell mirror of git-history.sh. STRICTLY READ-ONLY.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$GitRoot = (git -C $ScriptDir rev-parse --show-toplevel 2>$null)
if (-not $GitRoot) { $GitRoot = (git rev-parse --show-toplevel 2>$null) }
if (-not $GitRoot) { Write-Error 'Not inside a git repository.'; exit 1 }
$GitRoot = $GitRoot.Trim()
function G { git -C $GitRoot @args }

function Show-Usage {
    Write-Host @"
Usage: git-history.ps1 <list|show> [options]

Commands:
  list                 Enumerate commits oldest -> newest: <full_sha>\t<iso_date>\t<subject>
  show <sha>           Print <sha>'s metadata + name-status + --stat.

Options:
  -Since <ref>         list: only commits after <ref> (exclusive). Default: all.
  -Diff                show: also print the full patch (default: --stat only).
  -h | --help
"@ -ForegroundColor Cyan
    exit 1
}

$Action = if ($args.Count -ge 1) { $args[0] } else { 'list' }
$rest   = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

function Test-Ref { param([string]$Ref) (G rev-parse --verify --quiet $Ref) | Out-Null; return $LASTEXITCODE -eq 0 }

switch ($Action.ToLower()) {
    'list' {
        $since = ''
        for ($i = 0; $i -lt $rest.Count; $i++) {
            switch ($rest[$i].ToLower()) {
                { $_ -in '-since','--since' } { $since = $rest[++$i] }
                { $_ -in '-h','--help' }      { Show-Usage }
                default { Write-Error "Unknown option: $($rest[$i])"; Show-Usage }
            }
        }
        if ($since) {
            if (-not (Test-Ref $since)) { Write-Error "Ref not found: $since"; exit 1 }
            G log --reverse --format='%H%x09%aI%x09%s' "$since..HEAD"
        } else {
            G log --reverse --format='%H%x09%aI%x09%s'
        }
    }
    'show' {
        if ($rest.Count -lt 1) { Write-Error 'show requires a <sha>'; Show-Usage }
        $sha = $rest[0]
        $withDiff = $false
        for ($i = 1; $i -lt $rest.Count; $i++) {
            switch ($rest[$i].ToLower()) {
                { $_ -in '-diff','--diff' } { $withDiff = $true }
                { $_ -in '-h','--help' }    { Show-Usage }
                default { Write-Error "Unknown option: $($rest[$i])"; Show-Usage }
            }
        }
        (G cat-file -e "$sha^{commit}" 2>$null) | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Error "Commit not found: $sha"; exit 1 }
        Write-Output ("## COMMIT " + (G rev-parse --short $sha))
        G log -1 --format='sha:     %H%nauthor:  %an <%ae>%ndate:    %aI%nsubject: %s%n%nbody:%n%b' $sha
        Write-Output ''
        Write-Output '## FILES (name-status)'
        G diff-tree --no-commit-id -r --name-status $sha
        Write-Output ''
        Write-Output '## STAT'
        G show --stat --format='' $sha
        if ($withDiff) {
            Write-Output ''
            Write-Output '## DIFF'
            G show --format='' $sha
        }
    }
    { $_ -in '-h','--help','help' } { Show-Usage }
    default { Write-Error "Unknown command: $Action"; Show-Usage }
}
