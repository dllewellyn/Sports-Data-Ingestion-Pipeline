#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Locate repo root from this script's location (scripts/powershell -> skill root -> repo root)
$ScriptDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$GitRoot = (git -C $ScriptDir rev-parse --show-toplevel 2>$null) ?? $ScriptDir
$GitRoot = $GitRoot.Trim()
$LastSyncFile = Join-Path $GitRoot '.last-sync'
$TempBase = Join-Path $GitRoot 'temp'
$DefaultPatterns = @('architecture', 'transcripts')

function Show-Usage {
    Write-Host @"
Usage: git-sync-extractor.ps1 [run|reset|status] [options]

Commands:
  run     Extract diffs for commits since last sync (default)
  reset   Clear .last-sync so next run reprocesses all commits
  status  Show current sync state without processing

Options:
  -Pattern <prefix>    Path prefix to match (repeatable)
                       Default: architecture transcripts
  -Temp <dir>          Output directory (default: <repo_root>/temp)
  -LastSync <file>     .last-sync file path (default: <repo_root>/.last-sync)
  -From <commit>       Override starting commit (skips .last-sync prompt)
"@ -ForegroundColor Cyan
    exit 1
}

function ConvertTo-FlatPath {
    param([string]$FilePath)
    return $FilePath -replace '/', '__'
}

function Test-MatchesPattern {
    param([string]$FilePath, [string[]]$Patterns)
    foreach ($pattern in $Patterns) {
        $trimmed = $pattern.TrimEnd('/')
        if ($FilePath -eq $trimmed -or $FilePath.StartsWith("$trimmed/")) {
            return $true
        }
    }
    return $false
}

function Read-LastSync {
    param([string]$Path)
    if (Test-Path $Path) {
        return (Get-Content $Path -Raw).Trim()
    }
    return ''
}

function Write-LastSync {
    param([string]$Path, [string]$Commit)
    Set-Content -Path $Path -Value $Commit -Encoding UTF8 -NoNewline
}

function Get-CommitMeta {
    param([string]$Commit)
    $lines = git -C $GitRoot log -1 --format="%H%n%h%n%an%n%ae%n%aI%n%s" $Commit
    return @{
        FullSha     = $lines[0]
        ShortSha    = $lines[1]
        AuthorName  = $lines[2]
        AuthorEmail = $lines[3]
        Timestamp   = $lines[4]
        Subject     = $lines[5]
    }
}

function Get-ChangedFiles {
    param([string]$Commit)
    # Returns objects with Status and Path
    $raw = git -C $GitRoot diff-tree --no-commit-id -r --name-status $Commit 2>$null
    $result = [System.Collections.Generic.List[hashtable]]::new()
    foreach ($line in $raw) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split "`t", 2
        if ($parts.Count -ge 2) {
            $result.Add(@{ Status = $parts[0].Trim(); Path = $parts[1].Trim() })
        }
    }
    return $result
}

function Get-FileDiff {
    param([string]$Commit, [string]$FilePath)
    $diff = git -C $GitRoot diff "${Commit}^" $Commit -- $FilePath 2>$null
    if (-not $diff) {
        # First commit or no parent — produce a pseudo-diff from show
        $content = git -C $GitRoot show "${Commit}:${FilePath}" 2>$null
        return $content
    }
    return $diff
}

function Get-FileContent {
    param([string]$Commit, [string]$FilePath)
    return git -C $GitRoot show "${Commit}:${FilePath}" 2>$null
}

function Invoke-EscapeJson {
    param([string]$Text)
    # Minimal JSON string escaping
    $escaped = $Text `
        -replace '\\', '\\' `
        -replace '"', '\"' `
        -replace "`n", '\n' `
        -replace "`r", '' `
        -replace "`t", '\t'
    return "`"$escaped`""
}

function Invoke-ProcessCommit {
    param([string]$Commit, [string[]]$Patterns)

    $meta = Get-CommitMeta -Commit $Commit
    $commitDir = Join-Path $TempBase $meta.ShortSha

    $changedFiles = Get-ChangedFiles -Commit $Commit
    $matched = $changedFiles | Where-Object { Test-MatchesPattern -FilePath $_.Path -Patterns $Patterns }

    if (-not $matched -or $matched.Count -eq 0) {
        return
    }

    New-Item -ItemType Directory -Path $commitDir -Force | Out-Null

    $jsonFiles = [System.Collections.Generic.List[string]]::new()

    foreach ($entry in $matched) {
        $status   = $entry.Status
        $filePath = $entry.Path
        $flatPath = ConvertTo-FlatPath -FilePath $filePath

        switch -Wildcard ($status) {
            'A' {
                $outFile = Join-Path $commitDir "new_$flatPath"
                $content = Get-FileContent -Commit $Commit -FilePath $filePath
                if ($null -ne $content) {
                    Set-Content -Path $outFile -Value $content -Encoding UTF8
                    $jsonFiles.Add("{`"path`":$(Invoke-EscapeJson $filePath),`"status`":`"added`",`"output`":$(Invoke-EscapeJson "new_$flatPath")}")
                } else {
                    Write-Warning "Could not read new file content for $filePath"
                }
            }
            { $_ -eq 'M' -or $_ -like 'R*' -or $_ -like 'C*' } {
                $outFile = Join-Path $commitDir "changed_${flatPath}.diff"
                $diff = Get-FileDiff -Commit $Commit -FilePath $filePath
                if ($null -ne $diff -and $diff.Count -gt 0) {
                    Set-Content -Path $outFile -Value $diff -Encoding UTF8
                } else {
                    Set-Content -Path $outFile -Value '' -Encoding UTF8
                }
                $jsonFiles.Add("{`"path`":$(Invoke-EscapeJson $filePath),`"status`":`"modified`",`"output`":$(Invoke-EscapeJson "changed_${flatPath}.diff")}")
            }
            'D' {
                $jsonFiles.Add("{`"path`":$(Invoke-EscapeJson $filePath),`"status`":`"deleted`",`"output`":null}")
            }
        }
    }

    $patternsJson = '[' + (($Patterns | ForEach-Object { Invoke-EscapeJson $_ }) -join ',') + ']'
    $filesJson    = '[' + ($jsonFiles -join ',') + ']'

    $manifest = @"
{
  "commit": "$($meta.FullSha)",
  "short_commit": "$($meta.ShortSha)",
  "author": "$($meta.AuthorName)",
  "author_email": "$($meta.AuthorEmail)",
  "timestamp": "$($meta.Timestamp)",
  "message": $(Invoke-EscapeJson $meta.Subject),
  "patterns": $patternsJson,
  "files": $filesJson
}
"@
    Set-Content -Path (Join-Path $commitDir 'changed_files.json') -Value $manifest -Encoding UTF8
    Write-Host "  -> $($matched.Count) file(s) in $commitDir" -ForegroundColor DarkGray
}

function Resolve-StartCommit {
    param([string]$LastSync, [string]$FromOverride)

    if ($FromOverride) {
        return $FromOverride
    }

    if ($LastSync) {
        $valid = git -C $GitRoot cat-file -t $LastSync 2>$null
        if ($valid) {
            return $LastSync
        }
        Write-Warning ".last-sync commit '$LastSync' not found in repo, ignoring."
    }

    Write-Host ""
    Write-Host "No previous sync point found." -ForegroundColor Yellow
    Write-Host "Options:"
    Write-Host "  1) Start from the very beginning (first commit)"
    Write-Host "  2) Start from a specific commit or ref"
    $choice = Read-Host "Choice [1/2]"

    if ($choice -eq '2') {
        $ref = Read-Host "Enter commit hash or ref"
        if (-not $ref) {
            Write-Error "No commit provided, aborting."
            exit 1
        }
        $valid = git -C $GitRoot cat-file -t $ref 2>$null
        if (-not $valid) {
            Write-Error "Commit/ref '$ref' not found in repository."
            exit 1
        }
        return $ref
    }
    return ''
}

function Get-CommitsSince {
    param([string]$StartCommit)
    if ($StartCommit) {
        return git -C $GitRoot log --format="%H" --reverse "${StartCommit}..HEAD" 2>$null
    } else {
        return git -C $GitRoot log --format="%H" --reverse 2>$null
    }
}

# ── Entry point ────────────────────────────────────────────────────────────────

$Action = if ($args.Count -ge 1) { $args[0] } else { 'run' }
$rest   = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

switch ($Action.ToLowerInvariant()) {

    'run' {
        # Parse options from $rest
        $patterns      = [System.Collections.Generic.List[string]]::new()
        $fromOverride  = ''
        $i = 0
        while ($i -lt $rest.Count) {
            switch ($rest[$i].ToLower()) {
                '-pattern'   { $patterns.Add($rest[$i + 1]); $i += 2 }
                '--pattern'  { $patterns.Add($rest[$i + 1]); $i += 2 }
                '-temp'      { $TempBase = $rest[$i + 1]; $i += 2 }
                '--temp'     { $TempBase = $rest[$i + 1]; $i += 2 }
                '-lastsync'  { $LastSyncFile = $rest[$i + 1]; $i += 2 }
                '--lastsync' { $LastSyncFile = $rest[$i + 1]; $i += 2 }
                '-from'      { $fromOverride = $rest[$i + 1]; $i += 2 }
                '--from'     { $fromOverride = $rest[$i + 1]; $i += 2 }
                default      { Write-Error "Unknown option: $($rest[$i])"; Show-Usage }
            }
        }

        if ($patterns.Count -eq 0) { $patterns.AddRange($DefaultPatterns) }

        $lastSync    = Read-LastSync -Path $LastSyncFile
        $startCommit = Resolve-StartCommit -LastSync $lastSync -FromOverride $fromOverride

        Write-Host "Scanning commits..." -ForegroundColor Cyan
        $commits       = Get-CommitsSince -StartCommit $startCommit
        $latestCommit  = ''
        $processedCount = 0

        foreach ($commit in $commits) {
            if ([string]::IsNullOrWhiteSpace($commit)) { continue }
            $subject = (git -C $GitRoot log -1 --format="%s" $commit 2>$null) -join ''
            Write-Host "Processing $($commit.Substring(0,8)): $subject"
            Invoke-ProcessCommit -Commit $commit -Patterns $patterns
            $latestCommit = $commit
            $processedCount++
        }

        if (-not $latestCommit) {
            Write-Host "No new commits to process since last sync." -ForegroundColor Yellow
            exit 0
        }

        Write-LastSync -Path $LastSyncFile -Commit $latestCommit
        Write-Host ""
        Write-Host "Done. Processed $processedCount commit(s)." -ForegroundColor Green
        Write-Host "Updated .last-sync to $($latestCommit.Substring(0,8))" -ForegroundColor Green
        Write-Host "Output in: $TempBase" -ForegroundColor Green
    }

    'reset' {
        if (Test-Path $LastSyncFile) {
            Remove-Item $LastSyncFile -Force
            Write-Host "Cleared .last-sync" -ForegroundColor Green
        } else {
            Write-Host ".last-sync does not exist, nothing to clear." -ForegroundColor Yellow
        }
    }

    'status' {
        $lastSync = Read-LastSync -Path $LastSyncFile
        if (-not $lastSync) {
            Write-Host "No sync point recorded (.last-sync is absent or empty)." -ForegroundColor Yellow
        } else {
            $meta    = git -C $GitRoot log -1 --format="%s (%aI)" $lastSync 2>$null
            $pending = (git -C $GitRoot log --oneline "${lastSync}..HEAD" 2>$null | Measure-Object -Line).Lines
            Write-Host "Last sync : $($lastSync.Substring(0,8)) — $meta"
            Write-Host "Pending   : $pending commit(s)"
        }
    }

    { $_ -in @('-h', '--help', 'help') } {
        Show-Usage
    }

    default {
        Write-Error "Unknown command: $Action"
        Show-Usage
    }
}
