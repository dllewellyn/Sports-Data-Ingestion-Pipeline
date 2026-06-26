#!/usr/bin/env pwsh
# Deterministic helpers for the ticket-formatter agent skill (PowerShell parity).
# The agent authors ticket bodies and writes the agreed content into the local
# user_stories/ backlog plus derived output. This script does discovery + mechanical
# work only: validate a spec, print the canonical template, and diff two files.
# It never calls az, never mutates the spec, and never pushes anywhere.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$GitRoot = (& git -C $ScriptDir rev-parse --show-toplevel 2>$null)
if (-not $GitRoot) { $GitRoot = $ScriptDir }
$StoriesDir = Join-Path $GitRoot 'user_stories'
$OutDir = Join-Path (Join-Path $GitRoot 'temp') 'ticket_formatter'

if ($args.Count -lt 1) {
    Write-Error "Usage: ./ticket-formatter.ps1 <validate|diff|template|status> [options]"
    exit 1
}
$Action = $args[0]
$rest = @()
if ($args.Count -gt 1) { $rest = $args[1..($args.Count - 1)] }

# Pull --stories/--out (and -Stories/-Out) out of the argument list; keep positionals.
$Positional = @()
for ($i = 0; $i -lt $rest.Count; $i++) {
    switch ($rest[$i]) {
        { $_ -in '--stories', '-Stories' } { $StoriesDir = $rest[$i + 1]; $i++ }
        { $_ -in '--out', '-Out' } { $OutDir = $rest[$i + 1]; $i++ }
        default { $Positional += $rest[$i] }
    }
}

$Template = @'
{
  "epic": {
    "id": null,
    "work_item_type": "Epic",
    "title": "<epic title>",
    "state": null,
    "parent": null,
    "sections": {
      "overview": "## Overview\n\n<plain-language epic narrative>",
      "glossary": "## Glossary\n\n| Term | Definition |\n| --- | --- |\n| <term> | <definition from source material> |",
      "component_architecture": "## Component Architecture Overview\n\n<components, responsibilities, data flows>",
      "definition_of_ready": "## Definition of Ready\n\n- [ ] <DOR item>",
      "definition_of_done": "## Definition of Done\n\n- [ ] <DOD item>"
    }
  },
  "stories": [
    {
      "id": null,
      "work_item_type": "User Story",
      "title": "<story title>",
      "state": null,
      "sections": {
        "user_story": "As a <role>, I want <capability>, so that <benefit>.",
        "description": "## Description\n\n<full detail>",
        "acceptance_criteria": "## Acceptance Criteria\n\n- [ ] Given <context>, when <action>, then <outcome>",
        "dependencies": "## Dependencies\n\n- <other story / external dependency>",
        "notes": "## Notes\n\n<implementation notes, evidence references>"
      }
    }
  ]
}
'@

function Invoke-Validate {
    if ($Positional.Count -lt 1) { throw "validate requires a spec path. See: template" }
    $spec = $Positional[0]
    if (-not (Test-Path $spec)) { throw "Spec not found: $spec" }

    try {
        $data = Get-Content -Raw -Path $spec | ConvertFrom-Json
    } catch {
        throw "Invalid JSON: $($_.Exception.Message)"
    }

    $errors = @()
    $epic = $data.PSObject.Properties['epic'].Value
    if (-not $epic) { $errors += "missing top-level 'epic' object" }

    $requiredEpicSections = @('overview', 'glossary', 'component_architecture',
        'definition_of_ready', 'definition_of_done')
    if ($epic) {
        if (-not $epic.title) { $errors += "epic.title is required" }
        if (-not $epic.work_item_type) { $errors += "epic.work_item_type is required" }
        $sections = $epic.sections
        foreach ($k in $requiredEpicSections) {
            if (-not ($sections -and $sections.$k)) { $errors += "epic.sections.$k is required" }
        }
    }

    $stories = @()
    if ($data.PSObject.Properties['stories']) { $stories = @($data.stories) }
    $requiredStorySections = @('user_story', 'acceptance_criteria')
    for ($i = 0; $i -lt $stories.Count; $i++) {
        $s = $stories[$i]
        if (-not $s.title) { $errors += "stories[$i].title is required" }
        if (-not $s.work_item_type) { $errors += "stories[$i].work_item_type is required" }
        foreach ($k in $requiredStorySections) {
            if (-not ($s.sections -and $s.sections.$k)) { $errors += "stories[$i].sections.$k is required" }
        }
    }

    if ($errors.Count -gt 0) {
        Write-Error ("Spec INVALID:`n" + (($errors | ForEach-Object { "  - $_" }) -join "`n"))
        exit 1
    }

    function Get-Verb($item) {
        if ($item.id) { return "UPDATE id=$($item.id)" } else { return "CREATE (new)" }
    }

    Write-Output "Spec OK."
    Write-Output "Plan:"
    Write-Output "  Epic: $(Get-Verb $epic)  — `"$($epic.title)`""
    foreach ($s in $stories) {
        Write-Output "  Story: $(Get-Verb $s)  — `"$($s.title)`" (link → epic)"
    }
    Write-Output "  $($stories.Count) story/stories total."
}

function Invoke-Diff {
    if ($Positional.Count -lt 2) { throw "diff requires two file paths: <before> <after>" }
    $before = $Positional[0]
    $after = $Positional[1]
    $beforeLines = if (Test-Path $before) { Get-Content $before } else { @() }
    $afterLines = if (Test-Path $after) { Get-Content $after } else { @() }
    $cmp = Compare-Object -ReferenceObject $beforeLines -DifferenceObject $afterLines -IncludeEqual:$false
    if (-not $cmp) {
        Write-Output "(no differences)"
        return
    }
    foreach ($row in $cmp) {
        $sign = if ($row.SideIndicator -eq '=>') { '+' } else { '-' }
        Write-Output "$sign $($row.InputObject)"
    }
}

function Invoke-Status {
    Write-Output "user_stories dir: $StoriesDir"
    if (Test-Path $StoriesDir) {
        $n = (Get-ChildItem -Path $StoriesDir -Filter '*.json' -File -ErrorAction SilentlyContinue).Count
        Write-Output "  state: $n story file(s)"
    } else {
        Write-Output "  state: missing"
    }
    Write-Output "output dir: $OutDir"
    if (Test-Path $OutDir) {
        Write-Output "  bodies/diffs present:"
        Get-ChildItem -Path $OutDir -File -ErrorAction SilentlyContinue | Sort-Object Name |
            ForEach-Object { Write-Output "    $($_.FullName)" }
    } else {
        Write-Output "  state: not yet created (regenerated on apply)"
    }
}

switch ($Action.ToLowerInvariant()) {
    'validate' { Invoke-Validate }
    'diff'     { Invoke-Diff }
    'template' { Write-Output $Template }
    'status'   { Invoke-Status }
    default {
        Write-Error "Unknown command: $Action. Supported: validate, diff, template, status"
        exit 1
    }
}
