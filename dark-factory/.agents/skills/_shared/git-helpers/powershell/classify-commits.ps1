#!/usr/bin/env pwsh
# classify-commits.ps1 — PowerShell mirror of classify-commits.sh.
# PRE-FILTER for missing-specification §2: tag each commit by changed-path footprint
# only (AUTO-NONSUBSTANTIVE / DEP / CANDIDATE / MERGE / EMPTY). Read-only. Prints
# `<sha>\t<class>\t<subject>` oldest-first; summary to stderr. NOT a covered/unspecified verdict.
[CmdletBinding()]
param([string]$Since)
$ErrorActionPreference = 'Stop'

$range = if ($Since) { "$Since..HEAD" } else { 'HEAD' }

function Get-Class([string[]]$paths) {
  $hasCode = $false; $hasDep = $false; $hasMeta = $false; $any = $false
  foreach ($p in $paths) {
    if (-not $p) { continue }
    $any = $true
    switch -Wildcard ($p) {
      'uv.lock'            { $hasDep = $true; continue }
      'poetry.lock'        { $hasDep = $true; continue }
      'Pipfile.lock'       { $hasDep = $true; continue }
      'Pipfile'            { $hasDep = $true; continue }
      'package-lock.json'  { $hasDep = $true; continue }
      'pnpm-lock.yaml'     { $hasDep = $true; continue }
      'yarn.lock'          { $hasDep = $true; continue }
      'requirements*.txt'  { $hasDep = $true; continue }
      'requirements*.in'   { $hasDep = $true; continue }
      'pyproject.toml'     { $hasDep = $true; continue }
      'setup.cfg'          { $hasDep = $true; continue }
      'setup.py'           { $hasDep = $true; continue }
      'package.json'       { $hasDep = $true; continue }
      '.agents/*'              { $hasMeta = $true; continue }
      '.github/*'              { $hasMeta = $true; continue }
      '.gitignore'             { $hasMeta = $true; continue }
      '.gitattributes'         { $hasMeta = $true; continue }
      '.editorconfig'          { $hasMeta = $true; continue }
      '.pre-commit-config.yaml' { $hasMeta = $true; continue }
      'LICENSE'                { $hasMeta = $true; continue }
      'docs/*'                 { $hasMeta = $true; continue }
      '*.md'                   { $hasMeta = $true; continue }
      '.vscode/*'              { $hasMeta = $true; continue }
      '.idea/*'                { $hasMeta = $true; continue }
      default              { $hasCode = $true }
    }
  }
  if (-not $any) { return 'EMPTY' }
  if ($hasCode)  { return 'CANDIDATE' }
  if ($hasDep)   { return 'DEP' }
  return 'AUTO-NONSUBSTANTIVE'
}

$counts = @{}
$log = git log --reverse --format='%H%x09%s' $range
foreach ($line in $log) {
  if (-not $line) { continue }
  $sha, $subject = $line -split "`t", 2
  $parents = (git rev-list --parents -n1 $sha).Split(' ').Count
  if ($parents -gt 2) {
    $cls = 'MERGE'
  } else {
    $files = git diff-tree --root --no-commit-id --name-only -r $sha
    $cls = Get-Class @($files)
  }
  $counts[$cls] = ([int]$counts[$cls]) + 1
  "{0}`t{1}`t{2}" -f $sha, $cls, $subject
}

$summary = "--- footprint pre-filter summary (agent still judges DEP / CANDIDATE) ---`n"
foreach ($k in 'AUTO-NONSUBSTANTIVE', 'DEP', 'CANDIDATE', 'MERGE', 'EMPTY') {
  if ($counts.ContainsKey($k)) { $summary += ('{0,-20} {1}`n' -f $k, $counts[$k]) }
}
[Console]::Error.Write($summary)
