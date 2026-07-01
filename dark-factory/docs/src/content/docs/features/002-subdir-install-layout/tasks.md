---
title: "Tasks: Subdir Install Layout"
---

# Tasks: Subdir Install Layout

**Feature directory**: `specs/002-subdir-install-layout/`
**Date**: 2026-06-30
**Plan**: `plan.md`
**Status**: Draft

> **Single-file constraint on `[P]`.** Almost all production edits touch the **same** file
> (`install.sh`) and almost all tests touch the **same** file (`tests/test_install.py`), so they are
> **not** file-disjoint and run **serially**. TDD pairs each test (red) with the matching `install.sh`
> change (green), creating a hard dependency that further forbids `[P]`. `[P]` therefore appears on
> **no** task in this feature. See the Notes section for the full rationale.

## Phase 1: Setup (shared infrastructure)

- [X] T001 [S0] Confirm the S0 convention gate is satisfied: DRAFT RULE 1 (Bash) & DRAFT RULE 2 (shell-script pytest) are already user-approved and committed to `.specify/memory/constitution.md` (v1.1.0, commit 713d42d). This is a **satisfied precondition** — do NOT re-open or re-ask for approval. Verify the rules are present in the constitution before any `install.sh` edit begins.
- [X] T002 [S0] Create `tests/test_install.py` with the subprocess harness: a helper that runs `subprocess.run(["bash", str(INSTALL_SH), str(target)], capture_output=True, text=True)` where `INSTALL_SH` resolves to the repo-root `install.sh` (the real script, not a copy/mock) and SOURCE = repo root, plus the first failing assertion that `<target>/dark-factory/AGENTS.md` exists after a clean install. Run `uv run pytest tests/test_install.py -q` and confirm it is **red for the right reason** (today `AGENTS.md` lands at the target root, not under `dark-factory/`); `uv run ruff check tests/test_install.py` clean.

**Checkpoint**: harness wired, conventions confirmed committed, first red confirmed. No `install.sh` behaviour changed in Setup.

## Phase 2: Foundational (blocking prerequisites)

> No user-story work begins until this phase completes. This phase introduces the `dark-factory/`
> destination root that every later link, payload, and migration target depends on.

- [X] T003 [S1] Introduce the `SUBDIR="dark-factory"` constant in `install.sh` and root the payload-copy destination at `$TARGET/$SUBDIR` (foundational path prerequisite for all root/docs links and migration in later phases). No behaviour assertion lands here beyond what US1 T005 covers; this establishes the shared constant the rest of the feature builds on.

## Phase 3: User Story 1 — Install into a clean target without polluting its root (Priority: P1) 🎯 MVP

**Goal**: A fresh install lands all five payloads under `dark-factory/`, wires every required root symlink (incl. new `.agents`/`.specify` and the corrected-depth docs links) into the subdir, and keeps `specs/`/`plans/` real at root — staying usable by Claude Code and the helpers.
**Independent Test**: On a clean temp dir, run the installer; assert no real payload at root, payloads under `dark-factory/`, root symlinks resolve into `dark-factory/`, and `specs/`/`plans/` are real root dirs (plan units U1–U6, U17–U19).

- [X] T004 [US1] [S1] Write failing test U1 in `tests/test_install.py`: after a clean-target install, `dark-factory/{.agents,.specify,telemetry,docs,AGENTS.md}` are **real** and **no real** copy of any payload exists at the target root. Confirm red. (red — must fail before T005)
- [X] T005 [US1] [S1] Implement S1 in `install.sh`: change `copy_payload`'s `dest` to `"$TARGET/$SUBDIR/$relitem"` (using the T003 `SUBDIR` constant) so the five payloads land under `dark-factory/` and nothing real is written at root; keep `cp -RPp` (R6). **Handoff note for S3 (U3/U4/U19):** `cp -RPp` will copy SOURCE's three internal docs symlinks verbatim with stale 4-level text — do NOT fix that here; it is excluded/re-created in S3. Make U1 green; `uv run ruff check tests/` clean. (green)
- [X] T006 [US1] [S2] Write failing tests U2 + U6 in `tests/test_install.py`: U2 asserts `.claude/skills -> ../dark-factory/.agents/skills`, `CLAUDE.md -> dark-factory/AGENTS.md`, new `.agents -> dark-factory/.agents`, `.specify -> dark-factory/.specify`, each `realpath`-resolving to an existing path under `dark-factory/`; U6 asserts `.agents/skills/<a real skill dir>` and `.specify` resolve from the target root (assert **resolution**, not mere existence). Confirm red. (red)
- [X] T007 [US1] [S2] Implement S2 in `install.sh`: replace the `link_one` calls (~`install.sh:192-193`) with the corrected targets (`.claude/skills -> ../dark-factory/.agents/skills`, `CLAUDE.md -> dark-factory/AGENTS.md`) and **add** `link_one ".agents" "$SUBDIR/.agents"` and `link_one ".specify" "$SUBDIR/.specify"` (research R1); targets are literal strings (R6); drop no previously-wired link. Make U2 + U6 green; ruff clean. (green)
- [X] T008 [US1] [S3] Write failing tests U3 + U4 + **U19** in `tests/test_install.py`, all run on a **default (no-`--force`)** clean install: U3 — `dark-factory/docs/src/content/docs/{specs,plans}` have `readlink` text `../../../../../{specs,plans}` (5 levels) resolving to root `specs/`/`plans/`; U4 — when SOURCE carries it, `dark-factory/docs/CLAUDE.md` is a symlink with text `AGENTS.md` resolving to `dark-factory/docs/AGENTS.md`; U19 — pins that the docs-site links are the corrected **5-level** target on the **default path**, not the copied-in stale 4-level link. Confirm red. (red)
- [X] T009 [US1] [S3] Implement S3 in `install.sh` via **exclude-then-link-fresh (option c)** so the corrected links win on the **default (no-`--force`) path** — this is the docs-link default-path fix (U19) and MUST be done as this explicit step, not collapsed into target-string edits: (1) in `copy_payload`, **exclude the three exact docs symlink relitems** (`docs/CLAUDE.md`, `docs/src/content/docs/specs`, `docs/src/content/docs/plans`) from being copied (a path-skip alongside the existing `*.pyc`/`.DS_Store` skip, matched at the actual `relitem` form), so the link paths do NOT pre-exist; (2) wire `link_one "$SUBDIR/docs/src/content/docs/specs" "../../../../../specs"` and `link_one "$SUBDIR/docs/src/content/docs/plans" "../../../../../plans"`; (3) keep `[ -L "$SOURCE/docs/CLAUDE.md" ] && link_one "$SUBDIR/docs/CLAUDE.md" "AGENTS.md"` (conditional preserved, sibling target string **unchanged** — do NOT change to `../AGENTS.md`, research R1/R2); no-clobber of a real file at those paths still honoured by `link_one`. Make U3 + U4 + U19 green (U19 run **without** `--force`); ruff clean. (green)
- [X] T010 [US1] [S4] Write failing tests U5 + U17 + U18 in `tests/test_install.py`: U5 — root `specs/`/`plans/` are **real** dirs with `.gitkeep`, NOT symlinks, and `dark-factory/specs` is absent (assert the not-relocated negatives so they bite); U17 — post-install `.gitignore` contains `temp/`/`__pycache__/`/`*.pyc` once each, **no** `dark-factory/temp/` entry, user rules intact; U18 — post-install "Next steps" stdout references `dark-factory/docs` and `dark-factory/telemetry` (paths that exist). Confirm red (U18 prints root paths today; assert U5/U17 negatives). (red)
- [X] T011 [US1] [S4] Implement S4 in `install.sh`: leave `ensure_keepdir "specs"`/`"plans"` at root unchanged; leave `merge_gitignore` entries unchanged (research R3 — no `dark-factory/temp/`); update the "Next steps" heredoc (~`install.sh:215-223`) to reference `dark-factory/docs` and `dark-factory/telemetry` and the skills line to the corrected link. Make U5 + U17 + U18 green; ruff clean. (green)

**Checkpoint**: User Story 1 independently functional — a fresh install produces the full subdir layout, all required root/docs links resolve into `dark-factory/`, and `specs/`/`plans/` stay real at root.

## Phase 4: User Story 2 — Migrate a prior flat install into the subdirectory layout (Priority: P1)

**Goal**: Re-running on a prior flat install relocates (moves) the flat payloads into `dark-factory/`, repoints the root symlinks, names each relocated payload, and leaves NO dual layout — preserving the user's own content.
**Independent Test**: Seed a flat layout (real payloads + old root symlinks); run the installer; assert zero real payloads remain at root, all under `dark-factory/`, root symlinks repointed, each relocation named in output, and user `specs/`/`plans`/other files untouched (plan units U7–U10).

> Depends on US1 (S1–S4): migration reuses the subdir destination and link-wiring that US1 established.

- [X] T012 [US2] [S6] Write failing tests U7 + U8 + U9 + U10 in `tests/test_install.py`: U7 — seed flat layout, after run **zero real** framework payloads at root and all five under `dark-factory/`; U8 — root links repointed into `dark-factory/` and stdout **names each relocated payload** (FR-017); U9 — seed `specs/mine.txt`, after migration it is byte-identical and still at root; U10 — seed mixed (some payloads real-at-root, some already symlinked) and assert it converges to a single subdir layout with no real at root. Confirm red. (red)
- [X] T013 [US2] [S6] Implement the migration in `install.sh`: replace the existence-only prior-install note (~`install.sh:180-182`) with real-payload detection `for p in .agents .specify telemetry docs AGENTS.md` guarded by `[ -e "$TARGET/$p" ] && [ ! -L "$TARGET/$p" ]` (research R4 — detect REAL payload, not mere existence, so a migrated target is not re-migrated); for each, `mkdir -p "$TARGET/$SUBDIR"` then `mv "$TARGET/$p" "$TARGET/$SUBDIR/$p"` (real `mv`, R5) with `info "relocated: $p -> $SUBDIR/$p"` (FR-017). **Repoint stale root symlinks (migration path, FR-006):** because migrating relocated the payloads the old-style root symlinks pointed at, when a migration actually occurred (`migrated=1`) clear the stale managed root symlinks (`.claude/skills`, `CLAUDE.md`) — `[ -L ]` symlinks only, never a real file (no-clobber preserved), routed through `run` (dry-run safe) — so the unchanged `link_one` wiring recreates them fresh into `dark-factory/` on the DEFAULT (no-`--force`) path. Gated on `migrated=1` so an idempotent re-run of an already-migrated target (`migrated=0`) never touches existing correct links (E2/FR-010 preserved; that no-migration skip-without-force case is U13/T014). `link_one` itself is NOT modified. No real payload may remain at root (Constitution I). Make U7 + U8 + U9 + U10 green; ruff check + ruff format --check clean. (green)

**Checkpoint**: User Stories 1 and 2 both work — fresh install and flat-migration each converge on the single subdir layout with no dual layout.

## Phase 5: User Story 4 — Re-run safely: idempotent, no-clobber, `--force`, guards (Priority: P2)

**Goal**: A re-run is idempotent and non-clobbering; `--force` repoints links and refreshes copied payloads without error; the self-copy/nested guards are preserved and **extended** so `dark-factory/` cannot collide with SOURCE.
**Independent Test**: Run the installer twice on a clean target (second run copies/relocates nothing, layout identical); a no-`--force` run against a stale old-flat-location link leaves it skip-reported (E2); run with `--force` (copied files refreshed, links repointed, rc 0); pre-place a real file where a link belongs (left untouched + warn); SOURCE==TARGET / nested / subdir-collision each exit non-zero; and the installer offers no dual-mode/layout-toggle flag (FR-008) (plan units U13–U16, folding the E2 skip-report and FR-008 flag-absence checks into U13/U16).

> US4 is sequenced **before** US3 because US3's flat-seed dry-run (U11/U12) can only assert migration
> output once the migration code (US2/S6) and the guard/force code (US4/S6) exist. US4 here completes
> the remaining S6 behaviour (guards, idempotency, no-clobber, `--force`).

- [X] T014 [US4] [S6] Write tests U13 + U14 + U15 + U16 in `tests/test_install.py` as **regression / invariant PINS** (like U4/U5/U9/U17 — they pin that the subdir layout PRESERVES the installer's existing guarantees; they pass today via existing code and their biting negatives fail if a guarantee is removed, so they are NOT contrived to fail): U13 — a second no-`--force` run copies/relocates nothing new and leaves the layout/content identical to after the first run (snapshot compare on structure/content; mtime excluded because `merge_gitignore` always `touch`es `.gitignore` — a pre-existing benign wart, surfaced not fixed); **plus the E2 no-`--force` stale-link skip-report half (FR-012/E2), seeded in a NON-migration context (stale root symlink present, NO real payloads at root → `migrated=0` → the T013 stale-symlink clearing does NOT run):** the link is left untouched and counted in the summary's `skipped(existing)=` (`link_one`'s skip branch, ~`install.sh:134-140`, which does NOT print a per-link line — the test asserts the actual summary count), NOT repointed (the repoint-WITH-`--force` half is covered by U15 below and U8/T012). U14 — pre-place a **real** `CLAUDE.md`, run without `--force` → left untouched + warning on stderr; U15 — after a `--force` re-run, a stale managed link repointed into `dark-factory/`, copied files refreshed, exit 0; U16 — SOURCE==TARGET, nested either way, and a SOURCE checkout inside `<TARGET>/dark-factory/` each exit non-zero with an error (the dark-factory/-vs-SOURCE collision is refused by the existing SOURCE-inside-TARGET guard because `$TARGET/$SUBDIR` is always a subpath of `$TARGET` — subsumption, see T015); **plus the FR-008 no-dual-mode flag-absence assertion:** the installer exposes NO layout-toggle/dual-mode flag — `bash install.sh --flat <tmp>` (or any `--flat`/layout-toggle flag) is rejected as an unknown flag (`install.sh` already `die`s on unknown flags at ~`install.sh:54`), and `--help` output advertises no flat/subdir toggle (guards FR-008 against a future regression that re-introduces a dual mode). (green pins)
- [X] T015 [US4] [S6] **FR-013 collision guard is satisfied by SUBSUMPTION — no separate functional guard is added** (analysis: `$TARGET/$SUBDIR` = `dark-factory/` is always a lexical subpath of `$TARGET`, so every dark-factory/-vs-SOURCE collision shape is already refused by the existing SOURCE↔TARGET self-copy + nested guards at `install.sh:70-72`; a `"$TARGET/$SUBDIR/"*` guard would be unreachable dead code — team-lead-confirmed Option A). Production change in `install.sh` = a **clarifying CODE COMMENT** near those guards documenting the subsumption (so a future reader/reviewer does not think the "extended guard" was forgotten). VERIFY (do NOT weaken) that `copy_one` no-clobber-of-real, `link_one` warn-on-real, and `--force` repoint/refresh already cover U13/U14/U15 for the new links. Make U13 + U14 + U15 + U16 green; ruff clean. (green)

**Checkpoint**: Re-run safety and guards proven on top of the migration; the installer is non-destructive by default and refuses unsafe SOURCE/TARGET/subdir combinations.

## Phase 6: User Story 3 — Preview the planned layout with a dry run (Priority: P2)

**Goal**: `--dry-run` routes every new mutation (subdir copy, new links, migration moves) through the `run`/dry-run wrapper, prints the full plan (payloads, links+targets, relocations), and changes nothing on disk — on both a clean and a flat seed.
**Independent Test**: `--dry-run` against a clean target and a flat-layout target; assert a `find`+stat snapshot is byte-identical before/after, and the stdout describes the subdir payloads, each link+target, and (flat seed) the relocations (plan units U11–U12).

> Sequenced **last**: the flat-seed half of U11/U12 asserts migration dry-run output, which only exists
> once US2/US4 (S6) have landed. Split into the clean-seed half (could land after US1/S4) and the
> flat-seed half (after S6); both are completed here now that S6 exists.

- [X] T016 [US3] [S5] Write failing tests U11 + U12 in `tests/test_install.py`: U11 — a `find`+per-entry stat snapshot of the target is byte-for-byte identical before and after a `--dry-run` invocation, on **both** a clean seed **and** a flat seed (inode/mtime unchanged, not merely "looks unchanged"); U12 — dry-run stdout describes the `dark-factory/` payloads, each root symlink + its target text, and (flat seed) the migration relocations. Confirm red. (red)
- [X] T017 [US3] [S5] Implement S5 in `install.sh`: route the new link calls and the S6 migration `mv` (and `mkdir -p`) through the existing `run`/dry-run wrapper; add dry-run print lines naming the planned `dark-factory/` payloads, each link + target, and the relocations. Verify no new mutation (`mv`/`ln`/`cp`/`mkdir`) is left un-wrapped by `run`. Make U11 + U12 green (incl. the flat-seed cases); ruff clean. (green) — **VERIFY-ONLY OUTCOME (no functional change needed):** audit confirmed every mutation (`mkdir`/`rm`/`cp`/`ln`/`mv` at `install.sh:99,101,103,142,153,154,161,163,197,198,211`) already routes through the `run` dry-run wrapper, and the sole non-`run` `touch` in `merge_gitignore` sits behind that function's own `DRY_RUN` early-return — so `--dry-run` makes zero changes and its `[dry-run] …` command echoes already name the payloads, links+targets, and relocations. U11/U12 therefore pass on the existing installer as preserved-invariant pins; no `install.sh` edit was required (adding redundant echo lines would be gold-plating).

**Checkpoint**: All four user stories complete; `--dry-run` previews the full subdir layout and any migration with zero filesystem change.

## Phase N: Polish & cross-cutting

- [X] T018 [S6] Run the whole-feature quality gate green check: `uv run ruff check tests/ && uv run ruff format --check tests/` clean, and `uv run pytest -q` green for the full suite (existing 17 tests + all new U1–U19 in `tests/test_install.py`). This is the build's quality gate (ruff + pytest via `uv` — there is no pre-commit config; user-confirmed). Do not weaken, skip, or `--no-verify` any gate.
- [X] T019 [setup] [S5] Validate `quickstart.md` end-to-end: run each runnable scenario in `specs/002-subdir-install-layout/quickstart.md` against a temp target and confirm the documented outcomes match the installed layout (no doc drift versus the shipped `install.sh`).

## Dependencies & Execution Order

- **Setup (Phase 1)**: T001 (confirm committed conventions — satisfied precondition) and T002 (harness + first red). Start immediately. No `install.sh` edit until both done.
- **Foundational (Phase 2)**: T003 (the `SUBDIR` constant) depends on Setup and **blocks every user story** (all links/payloads/migration root at `$TARGET/$SUBDIR`).
- **User Stories**:
  - **US1 (Phase 3, S1–S4)**: depends on Foundational. MVP — must land first.
  - **US2 (Phase 4, S6 migration)**: depends on US1 (reuses subdir + link-wiring).
  - **US4 (Phase 5, S6 guards/idempotency/force)**: depends on US1; sequenced **before** US3 because US3's flat-seed dry-run asserts migration+guard output that US2/US4 must produce first.
  - **US3 (Phase 6, S5 dry-run)**: depends on US2 + US4 — the flat-seed dry-run (U11/U12) can only assert migration relocations once the migration/guard code exists. The clean-seed half is logically available after US1/S4; both halves are completed in Phase 6.
- **Within every story**: the failing-test task precedes its implementation task (red before green), mirroring the plan's red/green loop. The `SUBDIR` constant (T003) precedes the dest change (T005). The docs exclude-then-link-fresh (T009) precedes nothing else but must keep the copied-in stale link out so U19 passes on the default path.
- **Polish (Phase N)**: T018 (whole-suite gate) and T019 (quickstart validation) run after all stories.
- **Repo ordering gotcha (from plan §Sequencing, S3 correction)**: `cp -RPp` in `copy_payload "docs"` preserves SOURCE's three internal docs symlinks verbatim with old 4-level text, and `link_one` only repoints a pre-existing link under `--force`. T009 therefore **excludes** those three from `copy_payload` so the link paths do not pre-exist and `link_one` creates them fresh with the corrected 5-level targets on the **default (no-`--force`)** path — U19 (in T008) pins this. There is no bronze→silver→gold / DuckDB / dbt-asset ordering in this filesystem-only feature.

### Parallel opportunities

- **None.** Every implementation task edits the single file `install.sh` (serial writes), and every test task edits the single file `tests/test_install.py` (serial writes). Test→impl pairs additionally carry a hard TDD dependency (red must precede green). No two tasks in this feature are both file-disjoint and dependency-free, so **no task is marked `[P]`**. `implementor` runs every task sequentially in T### order.

## Notes

- **`[P]` rationale (single-file constraint).** `[P]` means "different files, no unmet dependency", and a wrong `[P]` causes parallel write conflicts in `implementor`. Here the production surface is one file (`install.sh`) and the test surface is one file (`tests/test_install.py`); the only cross-file pairing (install.sh vs. test_install.py) is exactly the red→green TDD pair, which is a dependency, not a parallel opportunity. Distinct test units could in principle be independent functions, but they share `tests/test_install.py`, so concurrent edits would still collide. Therefore `[P]` is correctly absent from every task.
- **[Sn]** links each task to its plan step (traceability): Setup→S0; Foundational→S1 (constant); US1→S1/S2/S3/S4; US2→S6; US4→S6; US3→S5; Polish→S5/S6. The docs-link default-path fix (U19) is its explicit own implementation task (T009) so it cannot be skipped.
- **TDD**: verify each test fails (red) for the intended reason before implementing. Commit after each task or logical red→green pair.
- **Gate**: `uv run ruff` + `uv run pytest` (no pre-commit config exists — user-confirmed). Never bypass with `--skip`/`--no-verify`.
- **Constitution**: I — migration replaces the flat layout (no dual mode); II — no faked/stubbed steps, gate intact; III — red before green every step; IV — migration names each relocated payload (U8).
- **Coverage folded in from speckit-analyze (no new tasks/renumbering):** FR-008 "no dual mode" is asserted not only on-disk (U7/U10 → T013/T015) but also via a **flag-absence** check in T014/U16 (`--flat`/layout-toggle rejected as unknown; `--help` advertises no toggle). E2's **no-`--force` stale-link skip-report** half is asserted in T014/U13 (the repoint-with-`--force` half stays in U15/T014 and U8/T012). Both are test-only additions to `tests/test_install.py` within existing tasks — no new task, no `[P]`.
