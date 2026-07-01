#!/usr/bin/env pwsh
# Guarded atomic commit — PowerShell mirror of git-commit-safe.sh.
# Stages ONLY the named paths, enforces Conventional Commits, appends the Claude
# co-author trailer, lets hooks run (never --no-verify), and exposes none of the
# forbidden git verbs. It can only add + commit.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$GitRoot = (git -C $ScriptDir rev-parse --show-toplevel 2>$null)
if (-not $GitRoot) { $GitRoot = (git rev-parse --show-toplevel 2>$null) }
if (-not $GitRoot) { Write-Error 'Not inside a git repository.'; exit 1 }
$GitRoot = $GitRoot.Trim()
function G { git -C $GitRoot @args }

$Trailer = 'Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>'
$ConvRe  = '^(feat|fix|refactor|build|ci|chore|docs|style|perf|test)(\([a-zA-Z0-9._/-]+\))?!?: .+'

$Message = ''
$Paths = @()
$AllowDefaultBranch = $false
$NoTrailer = $false
$DryRun = $false

function Show-Usage {
    Write-Host @"
Usage: git-commit-safe.ps1 -m "<conventional message>" [options] <path> [<path> ...]

Stages exactly the given paths and makes ONE atomic Conventional Commit.

Required:
  -m, --message <msg>      First line must be Conventional Commits.
  <path> ...               The task footprint — only these paths are staged.

Options:
  --allow-default-branch   Permit committing on the default branch.
  --no-trailer             Do not append the Claude co-author trailer.
  --dry-run                Show what would happen; make no changes.
  -h | --help

NEVER bypasses hooks.
"@ -ForegroundColor Cyan
    exit 1
}

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i].ToLower()) {
        { $_ -in '-m','--message' }            { $Message = $args[++$i] }
        { $_ -in '--allow-default-branch' }    { $AllowDefaultBranch = $true }
        { $_ -in '--no-trailer' }              { $NoTrailer = $true }
        { $_ -in '--dry-run' }                 { $DryRun = $true }
        { $_ -in '-h','--help' }               { Show-Usage }
        default {
            if ($args[$i].StartsWith('-')) { Write-Error "Unknown option: $($args[$i])"; Show-Usage }
            $Paths += $args[$i]
        }
    }
}

if (-not $Message) { Write-Error 'Error: -m/--message is required.'; Show-Usage }
if ($Paths.Count -eq 0) { Write-Error 'Error: at least one path to stage is required.'; Show-Usage }

# 1. Conventional Commits gate (first line only)
$Subject = ($Message -split "`n")[0]
if ($Subject -notmatch $ConvRe) {
    Write-Error "Error: subject is not a Conventional Commit:`n  $Subject`nExpected: <type>(<scope>): <summary>"
    exit 1
}

# 2. Refuse staged changes OUTSIDE the named paths.
$PreStaged = (G diff --cached --name-only) | Where-Object { $_ }
if ($PreStaged) {
    $normPaths = $Paths | ForEach-Object { $_.TrimEnd('/') }
    $outOfScope = @()
    foreach ($f in $PreStaged) {
        $covered = $false
        foreach ($p in $normPaths) { if ($f -eq $p -or $f.StartsWith("$p/")) { $covered = $true; break } }
        if (-not $covered) { $outOfScope += $f }
    }
    if ($outOfScope.Count -gt 0) {
        Write-Error ("Error: the index has staged changes outside the paths you named:`n  " + ($outOfScope -join "`n  ") + "`nRefusing to fold them into this commit. Handle them separately first.")
        exit 1
    }
}

# 3. Default-branch guard (the branch decision is the user's; we never switch).
$CurBranch = (G rev-parse --abbrev-ref HEAD 2>$null); if (-not $CurBranch) { $CurBranch = 'DETACHED' }
$DefaultBranch = (G symbolic-ref --quiet refs/remotes/origin/HEAD 2>$null)
if ($DefaultBranch) { $DefaultBranch = $DefaultBranch -replace '^refs/remotes/origin/','' }
if (-not $DefaultBranch) {
    foreach ($c in 'main','master') { (G rev-parse --verify --quiet "refs/heads/$c") | Out-Null; if ($LASTEXITCODE -eq 0) { $DefaultBranch = $c; break } }
}
if ($DefaultBranch -and $CurBranch -eq $DefaultBranch -and -not $AllowDefaultBranch) {
    Write-Error "Error: HEAD is on the default branch '$DefaultBranch'.`nRaise the feature-branch question with the user (this script never switches branches).`nRe-run with --allow-default-branch to commit here intentionally."
    exit 1
}

# 4. Stage exactly the named paths.
G add -- @Paths

$Staged = (G diff --cached --name-only) | Where-Object { $_ }
if (-not $Staged) { Write-Error 'Nothing to commit — the given paths have no staged changes.'; exit 1 }

# 5. Assemble final message (+ trailer unless suppressed / already present).
$FinalMsg = $Message
if (-not $NoTrailer -and ($Message -notlike '*Co-Authored-By: Claude*')) {
    $FinalMsg = "$Message`n`n$Trailer"
}

if ($DryRun) {
    Write-Output "[dry-run] would commit on branch '$CurBranch' with subject:"
    Write-Output "  $Subject"
    Write-Output '[dry-run] staged files:'
    $Staged | ForEach-Object { Write-Output "  $_" }
    Write-Output '[dry-run] no changes made (index left staged).'
    exit 0
}

# 6. Commit — hooks run. No --no-verify, ever.
$MsgFile = New-TemporaryFile
try {
    Set-Content -Path $MsgFile -Value $FinalMsg
    G commit -F $MsgFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "`nCommit failed (a hook rejected it or modified files). The task is NOT green.`nFix the cause and re-review — do NOT retry with --no-verify/--skip."
        exit 1
    }
} finally {
    Remove-Item -Path $MsgFile -ErrorAction SilentlyContinue
}

Write-Output ("Committed: " + (G log -1 --format='%h %s'))
