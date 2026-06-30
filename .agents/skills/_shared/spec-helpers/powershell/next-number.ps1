#!/usr/bin/env pwsh
# next-number.ps1 — PowerShell mirror of next-number.sh.
# Print the next zero-padded NNN for a numbered-doc directory; --Count pre-allocates
# a consecutive block (for parallel spec writers in missing-specification).
#   next-number.ps1 <dir>            -> 004
#   next-number.ps1 <dir> -Count 3   -> three lines
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)][string]$Dir,
  [int]$Count = 1
)
$ErrorActionPreference = 'Stop'

if ($Count -lt 1) { Write-Error 'Count must be a positive integer'; exit 2 }

$max = 0
if (Test-Path -LiteralPath $Dir -PathType Container) {
  Get-ChildItem -LiteralPath $Dir -Filter *.md -File | ForEach-Object {
    if ($_.Name -match '^(\d+)-') {
      $n = [int]$Matches[1]
      if ($n -gt $max) { $max = $n }
    }
  }
}

for ($i = 1; $i -le $Count; $i++) {
  '{0:D3}' -f ($max + $i)
}
