#!/usr/bin/env pwsh
# Read-only commit auditor — PowerShell mirror of git-audit-commits.sh.
# STRICTLY READ-ONLY. Exit non-zero if any commit fails the conventional gate
# or is a merge, so it doubles as a gate.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$GitRoot = (git -C $ScriptDir rev-parse --show-toplevel 2>$null)
if (-not $GitRoot) { $GitRoot = (git rev-parse --show-toplevel 2>$null) }
if (-not $GitRoot) { Write-Error 'Not inside a git repository.'; exit 1 }
$GitRoot = $GitRoot.Trim()
function G { git -C $GitRoot @args }

$ConvRe = '^(feat|fix|refactor|build|ci|chore|docs|style|perf|test)(\([a-zA-Z0-9._/-]+\))?!?: .+'
$BaseOverride = ''
$FileWarn = 15

function Show-Usage {
    Write-Host @"
Usage: git-audit-commits.ps1 [options]

Options:
  -Base <ref>      Audit base..HEAD (default: auto-detected default branch).
  -FileWarn <n>    Flag commits touching > n files as possibly non-atomic (default 15).
  -h | --help
"@ -ForegroundColor Cyan
    exit 1
}

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i].ToLower()) {
        { $_ -in '-base','--base' }          { $BaseOverride = $args[++$i] }
        { $_ -in '-filewarn','--file-warn' } { $FileWarn = [int]$args[++$i] }
        { $_ -in '-h','--help' }             { Show-Usage }
        default { Write-Error "Unknown option: $($args[$i])"; Show-Usage }
    }
}

function Test-Ref { param([string]$Ref) (G rev-parse --verify --quiet $Ref) | Out-Null; return $LASTEXITCODE -eq 0 }

$BaseRef = $BaseOverride
if (-not $BaseRef) {
    $d = (G symbolic-ref --quiet refs/remotes/origin/HEAD 2>$null)
    if ($d) { $BaseRef = 'origin/' + ($d -replace '^refs/remotes/origin/','') }
    if (-not $BaseRef) { foreach ($c in 'main','master','develop','trunk') { if (Test-Ref "refs/heads/$c") { $BaseRef = $c; break } } }
}
if (-not $BaseRef -or -not (Test-Ref $BaseRef)) { Write-Error 'Could not resolve a base branch; pass -Base <ref>.'; exit 1 }

$MergeBase = (G merge-base $BaseRef HEAD 2>$null)
if (-not $MergeBase) { Write-Error "No common ancestor with $BaseRef."; exit 1 }
$MergeBase = $MergeBase.Trim()

$Commits = (G rev-list --reverse "$MergeBase..HEAD") | Where-Object { $_ }
Write-Output ("# Commit audit  (base: $BaseRef, range: " + $MergeBase.Substring(0,8) + "..HEAD, " + (@($Commits).Count) + " commit(s))")
Write-Output ''

$total = 0; $convFail = 0; $merges = 0; $fat = 0
foreach ($sha in $Commits) {
    $total++
    $subject = (G log -1 --format='%s' $sha)
    $parents = (G log -1 --format='%P' $sha)
    $nparents = (@($parents -split '\s+' | Where-Object { $_ })).Count
    $files = (G show --no-commit-id -r --name-only --format='' $sha) | Where-Object { $_ }
    $fcount = (@($files)).Count
    $topdirs = (@($files | ForEach-Object { ($_ -split '/')[0] } | Sort-Object -Unique) -join ',')

    $conv = 'PASS'; if ($subject -notmatch $ConvRe) { $conv = 'FAIL'; $convFail++ }
    $isMerge = 'no'; if ($nparents -gt 1) { $isMerge = 'yes'; $merges++ }
    $fatflag = ''; if ($fcount -gt $FileWarn) { $fatflag = ' (possibly non-atomic)'; $fat++ }

    Write-Output ("- " + $sha.Substring(0,8) + "  conventional:$conv  merge:$isMerge  files:$fcount$fatflag")
    Write-Output "    subject:  $subject"
    Write-Output ("    topdirs:  " + ($(if ($topdirs) { $topdirs } else { '<none>' })))
}

Write-Output ''
Write-Output '## Summary'
Write-Output "commits:            $total"
Write-Output "conventional fails: $convFail"
Write-Output "merge commits:      $merges"
Write-Output "fat (> $FileWarn files):    $fat"
Write-Output ''
Write-Output "Note: 'one commit per task' and 'message traces to the plan step' are semantic —"
Write-Output 'the reviewing agent judges those against the plan; this tool checks only mechanics.'

if ($convFail -gt 0 -or $merges -gt 0) { exit 1 }
