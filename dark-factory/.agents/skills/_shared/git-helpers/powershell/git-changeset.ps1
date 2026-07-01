#!/usr/bin/env pwsh
# Read-only changeset inspector — shared by the review / learning skills.
# PowerShell mirror of git-changeset.sh. STRICTLY READ-ONLY: only rev-parse,
# symbolic-ref, status, log, diff, merge-base. Never stages/commits/mutates.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$GitRoot = (git -C $ScriptDir rev-parse --show-toplevel 2>$null)
if (-not $GitRoot) { $GitRoot = (git rev-parse --show-toplevel 2>$null) }
if (-not $GitRoot) { Write-Error 'Not inside a git repository.'; exit 1 }
$GitRoot = $GitRoot.Trim()
function G { git -C $GitRoot @args }

$BaseOverride = ''
$Section      = 'all'    # all | log | status | diff
$DiffStyle    = 'full'   # full | stat
$LogLimit     = 20

function Show-Usage {
    Write-Host @"
Usage: git-changeset.ps1 [options]

Read-only inspector for "what changed on this branch / in the working tree".

Options:
  -Base <ref>      Compare against <ref> instead of the auto-detected default branch.
  -Section <s>     Limit output to: all (default) | log | status | diff
  -Stat            Use --stat for diffs (compact) instead of full patches.
  -LogLimit <n>    Max commits in the log section (default 20; 0 = all in range).
  -h | --help
"@ -ForegroundColor Cyan
    exit 1
}

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i].ToLower()) {
        { $_ -in '-base','--base' }         { $BaseOverride = $args[++$i] }
        { $_ -in '-section','--section' }    { $Section      = $args[++$i] }
        { $_ -in '-stat','--stat' }         { $DiffStyle    = 'stat' }
        { $_ -in '-loglimit','--log-limit' }{ $LogLimit     = [int]$args[++$i] }
        { $_ -in '-h','--help' }            { Show-Usage }
        default { Write-Error "Unknown option: $($args[$i])"; Show-Usage }
    }
}

function Test-Ref { param([string]$Ref) try { (G rev-parse --verify --quiet $Ref) | Out-Null; return $LASTEXITCODE -eq 0 } catch { return $false } }

function Get-DefaultBranch {
    $d = (G symbolic-ref --quiet refs/remotes/origin/HEAD 2>$null)
    if ($d) { $d = $d -replace '^refs/remotes/origin/','' ; if (Test-Ref "origin/$d") { return "origin/$d" } }
    foreach ($c in 'main','master','develop','trunk') { if (Test-Ref "refs/heads/$c") { return $c } }
    foreach ($c in 'main','master','develop','trunk') { if (Test-Ref "refs/remotes/origin/$c") { return "origin/$c" } }
    return ''
}

$CurBranch = (G rev-parse --abbrev-ref HEAD 2>$null); if (-not $CurBranch) { $CurBranch = 'DETACHED' }
$BaseRef = if ($BaseOverride) { $BaseOverride } else { Get-DefaultBranch }

$MergeBase = ''
$BaseNote  = ''
if ($BaseRef -and (Test-Ref $BaseRef)) {
    if ((G rev-parse $BaseRef).Trim() -eq (G rev-parse HEAD).Trim()) {
        $BaseNote = 'HEAD is at the base ref — no committed branch delta.'
    } else {
        $MergeBase = (G merge-base $BaseRef HEAD 2>$null)
        if ($MergeBase) { $MergeBase = $MergeBase.Trim() } else { $BaseNote = "No common ancestor with $BaseRef; committed-diff section skipped." }
    }
} else {
    $BaseNote = 'Could not resolve a base/default branch; showing uncommitted changes only.'
}

$Worktree = if ((G status --porcelain)) { 'dirty' } else { 'clean' }
$DiffArg  = if ($DiffStyle -eq 'stat') { '--stat' } else { '--patch' }

function Write-Header {
    Write-Output '# Changeset'
    Write-Output "repo:        $GitRoot"
    Write-Output "branch:      $CurBranch"
    Write-Output ("base:        " + ($(if ($BaseRef) { $BaseRef } else { '<none>' })))
    Write-Output ("merge-base:  " + ($(if ($MergeBase) { $MergeBase } else { '<none>' })))
    Write-Output "worktree:    $Worktree"
    if ($BaseNote) { Write-Output "note:        $BaseNote" }
    Write-Output ''
}
function Write-StatusSection { Write-Output '## STATUS (git status --short)'; G status --short; Write-Output '' }
function Write-LogSection {
    Write-Output '## LOG (commits on this branch since base)'
    if ($MergeBase) {
        if ($LogLimit -ne 0) { G log --oneline -n $LogLimit "$MergeBase..HEAD" } else { G log --oneline "$MergeBase..HEAD" }
    } else {
        Write-Output '(no base delta — showing recent history instead)'
        G log --oneline -n $LogLimit
    }
    Write-Output ''
}
function Write-DiffSection {
    Write-Output '## DIFF — UNCOMMITTED (working tree + index)'
    G diff $DiffArg HEAD
    Write-Output ''
    if ($MergeBase) {
        Write-Output '## DIFF — COMMITTED (base..HEAD)'
        G diff $DiffArg "$MergeBase..HEAD"
        Write-Output ''
    }
}

switch ($Section.ToLower()) {
    'all'    { Write-Header; Write-StatusSection; Write-LogSection; Write-DiffSection }
    'status' { Write-Header; Write-StatusSection }
    'log'    { Write-Header; Write-LogSection }
    'diff'   { Write-Header; Write-DiffSection }
    default  { Write-Error "Unknown section: $Section"; Show-Usage }
}
