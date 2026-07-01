# Tasks: Cross-Provider Conform — Symmetric Resolve-or-Mint for Every Provider

**Feature directory**: `specs/012-cross-provider-conform/`
**Date**: 2026-07-01
**Plan**: `plan.md`
**Status**: Draft

## Phase 1: Setup (shared infrastructure)

- [X] T001 [S0] Confirm the known-good baseline: run `PYTHONPATH=src uv run pytest tests/matchbook/test_conform.py` and `( cd dbt/data_platform && uv run --project ../.. dbt parse --profiles-dir . )`, recording both as green (`dbt parse` exit 0). Record honestly — no product code.
- [X] T002 [S0] Create the `tests/conform/` directory and add `tests/conform/test_smoke.py::test_placeholder_fails` asserting `False`; confirm it is collected and RED, then flip it green — proves the new test dir is collected. No product code smuggled in.
- [X] T003 [P] [S0] Ensure the git pre-commit hook is installed (`uv run pre-commit install`) so ruff `E,W,F,I,UP,B,C4,SIM` gates every later step.

## Phase 2: Foundational (blocking prerequisites)

> No user-story work begins until this phase completes. S1 is a hard convention gate; S2 is the shared identity authority every provider depends on.

- [X] T004 [S1] Draft the **provider four-file additions convention** rule text (naming `<provider>_canonical_{match,team,league,season}_additions.parquet`, seed-first resolution, bootstrap-empty discipline, Python-never-opens-DuckLake) targeting `CLAUDE.md` *Non-obvious constraints* via `create-rule`; duplicate-check against existing CLAUDE.md text; record verbatim under OQ-A. Do NOT auto-commit — OQ-A is APPROVED governance, so the CLAUDE.md write itself lands in S12 (T041). This task only establishes/records the drafted rule.
- [X] T005 [S1] Draft the **`league_aliases` seed convention** rule text (columns `league_id,canonical_name,provider,provider_key`; composite `(provider,provider_key)` unique; `league_id` not_null + intentionally NON-unique; `provider_key` not_null; ESPN-anchor additive; seed-only no-auto-learn) targeting `CLAUDE.md` *Non-obvious constraints* via `create-rule`; duplicate-check; record verbatim under OQ-A. Do NOT auto-commit — landed in S12 (T041). Establishes/records only. Depends on T004 (same `create-rule` invocation / same OQ-A record — serial, not `[P]`).
- [X] T006 [S2] Write failing pytest `tests/conform/test_resolve.py` (red — module absent): `resolve_team_id` seeded-name→seed team_id and unseen→`md5(lower(name))` (U1); `resolve_league_id` mapped key→`md5(league_slug)` and unmapped→deterministic provider-scoped id that is NOT `md5('matchbook_football')` (U2); `derive_season_id`==`md5(league_id||'|'||year)` matching `int_season` (U3); `compute_canonical_match_id` == the dbt macro's `concat_ws('|')`+`md5` shape (U4). Assert formulas byte-identical to `int_team.sql:27`, `int_season.sql:22`, `macros/canonical_match_id.sql`.
- [X] T007 [S2] Implement `src/data_platform/conform/resolve.py` (+ `conform/__init__.py`) as pure functions taking a seed DataFrame: `resolve_team_id`, `resolve_league_id`, `mint_provider_scoped`, `derive_season_id`, `compute_canonical_match_id` (moved from `matchbook/conform/engine.py:77-85`), `is_mintable_name`. No DuckLake, no I/O. Green: `PYTHONPATH=src uv run pytest tests/conform/test_resolve.py`; ruff clean. Depends on T006.

**Checkpoint**: shared resolver exists and matches the dbt formulas; conventions drafted and recorded in OQ-A.

## Phase 3: User Story 3 — Conform is a first-class cross-provider layer (Priority: P2 — relocation, foundational for US1/US2)

**Goal**: Relocate the Python resolve-or-mint engine to a neutral `src/data_platform/conform/` and remove the old `matchbook/conform/` package outright (constitution I), so every later provider change edits the neutral module.
**Independent Test**: `grep -rn "matchbook/conform\|matchbook\.conform" src tests` is empty; conform output byte-for-byte equivalent to pre-move for identical input; `dbt parse` + `dagster definitions validate` succeed.

> Sequenced before US1/US2 because those stories rewrite the mint path inside the relocated `conform/matchbook.py`. S3 and S5 touch several shared files together and MUST run serially (no `[P]` between them).

- [X] T008 [US3] [S3] Write failing `tests/conform/test_relocation.py` (red): assert `import data_platform.matchbook.conform` raises `ModuleNotFoundError` and `from data_platform.conform.matchbook import run_conform` succeeds (U16). Also move `tests/matchbook/test_conform.py` → `tests/conform/test_conform.py` and add an output-equivalence assertion against a captured pre-move fixture (resolved/exceptions/additions byte-for-byte for identical input, U16). Fails before the move.
- [X] T009 [US3] [S3] Relocate `matchbook/conform/{engine,event_name,overrides,scoring}.py` into `src/data_platform/conform/` (grouped as `conform/matchbook*`), rewire to use `conform/resolve.py`, and DELETE `src/data_platform/matchbook/conform/` (no shim, no re-export). Update `src/data_platform/assets/intermediate/matchbook_conform.py` import to `...conform.matchbook`; keep AssetKey `["matchbook_conform"]` UNCHANGED (do not touch `assets/dbt.py:35` source-map key). Green: `grep -rn "matchbook/conform\|matchbook\.conform" src tests` empty; `PYTHONPATH=src uv run pytest tests/conform`; `dbt parse` + `dagster definitions validate` succeed; ruff clean; no `from __future__ import annotations` re-added. Self-review via `code-architecture-review`. Depends on T007, T008.

**Checkpoint**: neutral conform layer in place; old path gone; Matchbook conform output unchanged.

## Phase 4: User Story 2 — Minted teams AND leagues de-duplicate through their alias seeds (Priority: P1)

**Goal**: Route every provider's team/league minting through the `team_aliases`/`league_aliases` seeds so a minted club/competition lands on the existing ESPN-anchored canonical id; kill the bogus `md5('matchbook_football')` constant.
**Independent Test**: mint a Matchbook team named "Wolves" (seeded alias) → `team_id` equals the seed's Wolverhampton Wanderers id; map the Matchbook `(sport_id,category_id)` for the Premier League onto `md5('eng.1')` → minted `league_id`/`season_id`/`match_id` equal the ESPN-anchored values.

> The `league_aliases` seed and the additions-file rename are the identity foundation US1 (full-chain minting) builds on.

- [X] T010 [US2] [S4] Write the red state for the `league_aliases` seed: add `dbt/data_platform/seeds/_seeds.yml` with FR-015 tests, then run `dbt build --select league_aliases` and confirm it FAILS (CSV absent). Separately add a deliberate duplicate `(provider,provider_key)` row and confirm the composite-unique singular test in `dbt/data_platform/tests/` goes RED, then remove the dup (U7). Provider `provider_key` = `"<sport_id>|<category_id>"` for Matchbook.
- [X] T011 [US2] [S4] Create `dbt/data_platform/seeds/league_aliases.csv` (columns `league_id,canonical_name,provider,provider_key`) with an ESPN `eng.1`→`md5('eng.1')` row and a Matchbook `15|<category>`→same `md5('eng.1')` row; complete `dbt/data_platform/seeds/_seeds.yml` — `league_id` not_null (NOT unique), `provider_key` not_null, `provider` not_null + accepted_values(`espn|matchbook|football_data`) — plus the zero-dependency singular composite-unique test in `dbt/data_platform/tests/` (no `dbt_utils` assumed, D6). Green: `dbt build --select league_aliases` with all tests; ESPN `int_league`/`int_match` byte-for-byte unchanged (`md5('eng.1')` recorded, not redefined). Depends on T010.
- [X] T012 [US2] [S5] Write failing `tests/conform/test_additions_naming.py` (red): assert the engine writes `matchbook_canonical_match_additions.parquet` and that no code references the old `matchbook_canonical_additions` name (U16). Fails before rename.
- [X] T013 [US2] [S5] Rename `matchbook_canonical_additions` → `matchbook_canonical_match_additions` across ALL consumers together (clean replace, no dual-read): engine write path in `conform/matchbook*`, the `config.py` property (check for property-name collision with existing `matchbook_*` props at 99-129), `int_match.sql:83-85` `read_parquet`, `_sources.yml:77-80` source name+location, and `matchbook_conform.py:44-47` bootstrap. Green: `grep -rn "matchbook_canonical_additions\b" src dbt` finds only the new `_match_additions` name; `dbt parse` succeeds; conform + `dbt build --select int_match` green. Depends on T009, T011. Serial with T009 (both edit shared files incl. `matchbook_conform.py` / `int_match.sql`) — NOT `[P]`.

**Checkpoint**: seed resolution wired; match-additions file renamed cleanly; ESPN identity untouched.

## Phase 5: User Story 1 — A minted match always has its full season→league→team chain (Priority: P1) 🎯 MVP

**Goal**: Minting a match emits (or reuses) its complete season→league→team chain into four provider additions files; the canonical `int_*` models union those additions; the four FK relationships tests pass green with minted rows present.
**Independent Test**: seed a Matchbook `new_canonical` event with an unseen team + uncovered league; run conform then `dbt build --select int_team int_league int_season int_match int_matchbook_event_link` → all minted ids appear canonically and all four relationships tests pass (red today).

> S7 (canonical league/season exports) MUST land before S6's resolution read path. S6 mints the chain (pytest-red→green on frames); S8 adds the UNIONs that turn the dbt relationships tests from red→green — the deliberate red→green for SC-001.

- [X] T014 [US1] [S7] Write failing `tests/conform/test_exports.py` (red): expect `data/silver/canonical/league.parquet` and `season.parquet` with the correct columns after `dbt build --select canonical_league_export canonical_season_export` (U15). Fails before the export models exist.
- [X] T015 [US1] [S7] Add `dbt/data_platform/models/marts/exports/canonical_league_export.sql` and `canonical_season_export.sql` mirroring `canonical_team_export.sql` (`materialized='external'`, two-file convention). Green: `dbt build --select canonical_league_export canonical_season_export` writes both Parquet files with correct columns. Depends on T014.
- [X] T016 [US1] [S7] Add `AssetKey(["marts","canonical_league_export"])` and `["marts","canonical_season_export"]` to the `matchbook_conform` asset `deps` and to the `matchbook_conform_assets` selection so lineage/order is correct; verify via a real **queued run** `dagster job execute -j matchbook_conform_job` (daemon path, not just `definitions validate`) that the new deps form edges and Python reads the FILE not the catalog. Depends on T015. Serial with T009/T013 (edits `matchbook_conform.py` shared state) — NOT `[P]`.
- [X] T017 [US1] [S6] Write failing `tests/conform/test_mint_chain.py` (red — new mint logic absent): minting a match with an unseen team + unmapped league emits a team-addition (`md5(lower(name))`), a season-addition, a provider-scoped league-addition, and a match-addition (U6); a seeded team reuses the seed id (E1); a mapped league yields `md5(league_slug)` (U2/E9); a blank home/away name routes to exceptions with NO addition row (U5/E5). Pandera rejects a malformed addition frame. Fails before the rewrite.
- [X] T018 [US1] [S6] Rewrite the mint path in `src/data_platform/conform/matchbook*` (replacing `_mint_canonical_addition`, old `engine.py:211-244`) using `conform/resolve.py`: resolve league via `league_aliases` (killing `md5('matchbook_football')`), derive `season_id` correctly, resolve teams via `team_aliases`, emit team/season/league additions ONLY for un-resolved chain members, read `data/silver/canonical/{league,season}.parquet` (from T015) to detect already-resolved members. Extend `_write_conform_outputs` to write all four additions frames with Pandera schemas. Green: `PYTHONPATH=src uv run pytest tests/conform/test_mint_chain.py`; ruff clean; `grep duckdb.connect` in `conform/` = none; run twice → identical additions (idempotent). Depends on T007, T011, T015, T017.
- [X] T019 [US1] [S6] Extend the `matchbook_conform` asset bootstrap (`matchbook_conform.py:44-51`) to bootstrap-write ALL FOUR additions files empty (with correct columns) before dbt runs — `read_parquet` errors on a missing file (it is NOT `try_read_parquet`), so every file must exist even when nothing is minted (FR-016/E4). Green: `dbt build` green with zero minting. Depends on T018. Serial with T016/T013/T009 (same `matchbook_conform.py`) — NOT `[P]`.
- [X] T020 [US1] [S8] Confirm the red-today state: with a minted Matchbook chain present (T018) but the UNIONs NOT yet added, `dbt build --select int_match int_season` FAILS the relationships tests (orphaned team/season/league) — this IS SC-001's red (U11). Record RED before adding the unions. Depends on T018, T019.
- [X] T021 [US1] [S8] Add to `int_team.sql` a `read_parquet('$DATA_DIR/silver/matchbook_canonical_team_additions.parquet')` (and football_data's, bootstrap-empty) UNION-ALL CTE, then `distinct`/`qualify row_number() ... = 1` keep-one on `team_id` (U8/E3). Green: `dbt build --select int_team` — `unique(team_id)`/`not_null` hold with minted rows. Depends on T020. `[P]` with T022, T023 (disjoint model files).
- [X] T022 [P] [US1] [S8] Add to `int_league.sql` the `read_parquet` UNION-ALL of `matchbook_canonical_league_additions.parquet` (and football_data's) + keep-one on `league_id` (U9). Green: `dbt build --select int_league` — `unique(league_id)`/`not_null` hold. Depends on T020. `[P]` with T021, T023.
- [X] T023 [P] [US1] [S8] Add to `int_season.sql` the `read_parquet` UNION-ALL of `matchbook_canonical_season_additions.parquet` (and football_data's) + keep-one on `season_id` (U10). **Acceptance detail:** the `int_season` season-addition rows MUST carry the resolved `league_id` on every row (never null) or the `int_season → int_league` relationships test fails. Green: `dbt build --select int_season` — season→league relationships passes with minted rows. Depends on T020. `[P]` with T021, T022.
- [X] T024 [US1] [S8] Verify the full chain resolves: `dbt build --select int_team int_league int_season int_match` green — all four `int_match`/`int_season` relationships tests pass with the minted chain present (fixed data path, no test weakened). **Note:** the existing `int_match` keep-one `qualify row_number() over (partition by match_id order by status_completed desc, kickoff_time desc)` intentionally makes a MINTED Matchbook row (status_completed=false) LOSE to an ESPN completed row for a shared match_id — this is the DESIRED outcome (ESPN authoritative fixture wins; both link tables still resolve to the shared match_id). Do NOT "fix" this ordering. Depends on T021, T022, T023.

**Checkpoint**: MVP — every minted match has its full chain; all four relationships tests green; no duplicate club/competition.

## Phase 6: User Story 4 — Matchbook link tables carry the missing FK tests (Priority: P2)

**Goal**: Add the two missing Matchbook link-table FK relationships tests (Spec 010 OQ3), safely green once US1/US2 guarantee every referenced team/league exists.
**Independent Test**: add the two `relationships` tests to `_intermediate.yml`; with US1/US2 in place they pass; an absent `team_id` makes the team-link test go red.

- [ ] T025 [US4] [S9] Write the red mutation check: add the `relationships` block for `int_matchbook_team_link.team_id` → `int_team.team_id` to `_intermediate.yml`, introduce a Matchbook team-link row whose `team_id` is absent from `int_team`, run `dbt build --select int_matchbook_team_link` and confirm the test goes RED (proves it bites, U13), then remove the bad row.
- [ ] T026 [US4] [S9] Add both `relationships` blocks to `_intermediate.yml` — `int_matchbook_team_link.team_id` → `int_team.team_id` and `int_matchbook_league_link.league_id` → `int_league.league_id` (matching the espn-link pattern at `:217-219`, `:238-241`) (U13, U14). Green: `dbt build --select int_matchbook_team_link int_matchbook_league_link` with US1/US2 in place. Depends on T024, T025.

**Checkpoint**: both Matchbook FK tests present and genuinely biting.

## Phase 7: User Story 5 — football-data conform is scaffolded to the shared contract (Priority: P3)

**Goal**: Wire football-data into the same shared resolve-or-mint contract via an interface module and four bootstrap-empty additions files, without implementing its matching body.
**Independent Test**: the football-data module declares the shared interface; `dbt build --select int_match int_team` stays green with football-data additions bootstrap-empty (contributing zero rows, not erroring).

- [ ] T027 [US5] [S10] Write failing `tests/conform/test_football_data_scaffold.py` (red): assert `src/data_platform/conform/football_data.py` declares the shared interface (the four additions filenames, the `conform/resolve.py` imports) and that `dbt build --select int_match int_team` stays green with football_data additions bootstrap-empty (U18). Fails before module + empty-file bootstrap exist.
- [ ] T028 [US5] [S10] Add `src/data_platform/conform/football_data.py` declaring the shared resolve-or-mint interface with a documented `NotImplementedError` matching body (honestly labelled per spec Assumption 1); add a small shared bootstrap helper in `conform/__init__.py` (reused by both providers, KISS per plan OQ) that writes the four football_data additions files empty. Ensure T021/T022/T023's UNIONs already reference the football_data additions files (bootstrap-empty). Green: `dbt build --select int_match int_team` green with zero football_data rows; interface test green. Depends on T021, T022, T023, T027.

**Checkpoint**: football-data slots into the shared contract; zero rows; no error.

## Phase 8: Polish & cross-cutting

- [ ] T029 [S11] Write failing `tests/conform/test_parity.py` (red): for a fixture whose league is mapped in `league_aliases`, the Python-computed `match_id` == the dbt macro output recomputed from the canonical tables — fails if resolver and macro drift (U12, E2). Depends on T024.
- [ ] T030 [S11] Cross-provider de-dup + full-run parity verification: run `dagster job execute -j matchbook_conform_job` (queued/daemon path — no `DagsterCodeLocationNotFoundError`) to completion; `dbt build` over intermediate+marts green; `int_match` has exactly ONE row for the shared fixture (keep-one); parity test green (U12, U17). No new product code. Depends on T028, T029.
- [ ] T031 [S12] Write the docs red state: after planning the edits, run `grep -rn "try_read_parquet\|conform lives in matchbook\|canonical.*ESPN-only\|models/silver/canonical" CLAUDE.md ARCHITECTURE.md ERD.md "data flows.md" dbt/data_platform/models/intermediate/int_match.sql` and record every stale hit that must be removed (U19). Fails (stale text present) before edits.
- [ ] T032 [P] [US1] [S12] Ripple `ARCHITECTURE.md`: describe conform as a symmetric cross-provider layer in `src/data_platform/conform/`, the four additions files, and correct any `models/silver/canonical/` → `models/intermediate/` staleness. `[P]` with T033, T034 (disjoint doc files). Depends on T030.
- [ ] T033 [P] [S12] Ripple `ERD.md`: document the `league_aliases` seed + the four `<provider>_canonical_*_additions.parquet`, and correct `models/silver/canonical/` staleness. `[P]` with T032, T034. Depends on T030.
- [ ] T034 [P] [S12] Ripple `data flows.md`: describe the symmetric conform flow (sources → bronze → silver canonical union of all providers → four additions files). `[P]` with T032, T033. Depends on T030.
- [ ] T035 [S12] Fix stale `try_read_parquet` comments in `dbt/data_platform/models/intermediate/int_match.sql` (it is `read_parquet`, errors on missing file — FR-014). Depends on T030. Serial with US1's `int_match` work — NOT `[P]` with T024.
- [ ] T036 [S12] Ripple `CLAUDE.md`: describe symmetric cross-provider conform (remove "canonical from ESPN"/"conform lives in matchbook"/stale UNION-ALL notes) AND land the two OQ-A-approved conventions drafted in T004/T005 into *Non-obvious constraints* (the four-file additions convention + the `league_aliases`/`_seeds.yml` convention). Green: the T031 grep finds no stale text; `uv run pre-commit run --all-files` clean on changed files (pre-existing SIM105 in the MCP server is not ours). Depends on T032, T033, T034, T035. Serial with the other doc tasks that also gate on the same grep — NOT `[P]`.
- [ ] T037 [S11] Validate `quickstart.md`: walk its 8 runnable validation scenarios end-to-end and confirm each passes against the built pipeline. Depends on T030, T036.

## Dependencies & Execution Order

- **Setup (Phase 1, S0)**: no dependencies — start immediately. T003 `[P]` (pre-commit install is disjoint from the baseline runs).
- **Foundational (Phase 2)**: S1 (T004→T005, serial: same `create-rule`/OQ-A record) is a hard convention gate; S2 (T006→T007) is the shared resolver. Both block all user stories. S1 authoring is independent of S2 code but neither user story starts until the resolver exists.
- **US3 (Phase 3, S3)**: depends on S2 (T007). Relocation before US1/US2 rewrite the mint path in the relocated module. S3 + S5 touch shared files together → serial.
- **US2 (Phase 4, S4/S5)**: seed (S4: T010→T011) depends on S2; rename (S5: T012→T013) depends on US3's relocation (T009) + the seed (T011). T013 serial with T009 (shared files).
- **US1 (Phase 5, S6/S7/S8)**: S7 exports (T014→T016) before S6's read path (T018). S6 (T017→T019) depends on the resolver, seed, and exports. S8 (T020→T024) is the deliberate red→green: T020 records the red relationships tests, T021/T022/T023 add the unions (parallel — disjoint model files), T024 confirms green.
- **US4 (Phase 6, S9)**: T025→T026 depend on US1/US2 (T024) so the FK tests are safely green.
- **US5 (Phase 7, S10)**: T027→T028 depend on US1's unions (T021/T022/T023) already referencing football_data files.
- **Polish (Phase 8, S11/S12)**: parity (T029→T030) after US1; docs (T031→T037) after the full run.

### Within-story ordering (TDD)

- Every failing-test task precedes its implementation task: T006→T007, T008→T009, T010→T011, T012→T013, T014→T015, T017→T018, T020→T021/T022/T023, T025→T026, T027→T028, T029→T030, T031→T036.
- Models → wiring: `int_*` model unions (T021/T022/T023) before the asset/lineage verification and FK tests.

### Repo ordering gotchas (from plan / CLAUDE.md)

- **Bootstrap-empty before any `dbt build`** touching the canonical models — `read_parquet` errors on a missing file (all four additions files per provider written empty first: T019, T028).
- **S7 exports before S6's resolution read** — Python conform reads `silver/canonical/{league,season}.parquet` which only exist after T015.
- **Single-writer `warehouse.duckdb` / Python-never-opens-DuckLake** — conform reads only bronze + silver/canonical Parquet exports (no `duckdb.connect` in `conform/`).
- **dbt AssetKey = schema-folder prefix only**; the relocation keeps AssetKey `["matchbook_conform"]` UNCHANGED (T009) so `assets/dbt.py:35` source-map and `deps` need no key rename — verify lineage via a real queued run (T016, T030), not just `definitions validate`.

### Parallel opportunities

- Setup: T003 `[P]`.
- US1 canonical-model unions: T021, T022, T023 `[P]` (disjoint `int_team.sql`/`int_league.sql`/`int_season.sql`).
- Docs ripple: T032, T033, T034 `[P]` (disjoint `ARCHITECTURE.md`/`ERD.md`/`data flows.md`). T035/T036 are serial (T035 edits shared `int_match.sql`; T036's `pre-commit --all-files` gate depends on the other doc edits landing).

### Shared-state serialisation (do NOT `[P]` these together)

- `definitions.py` / `AssetSelection`, `config.py`, `_intermediate.yml`, `_sources.yml`, `dbt_project.yml`, `int_match.sql`, and the shared dbt manifest are shared state. Tasks touching the same shared file run serially: T009/T013/T016/T019 all edit `matchbook_conform.py` and/or `int_match.sql`/`_sources.yml`/`config.py` — serial. T024/T035 both concern `int_match.sql` — serial. The S3/S5 relocation+rename touches several shared files together — serial.

## Notes

- [P] = different files, no unmet dependency. A wrong [P] causes parallel write conflicts.
- [Sn] links each task to its plan step (traceability). [USn] maps it to a user story.
- Verify tests fail before implementing. Commit after each task or logical group.
- **OQ-A is APPROVED** (user sign-off recorded by team-lead): the two new conventions ARE to be codified into `CLAUDE.md` — established/recorded in S1 (T004/T005), finalised in S12 (T036) with the FR-014 doc ripple. This is agreed governance, not a deferred decision.
- No backward-compatibility tasks (constitution I); no gate-bypass tasks (constitution II); no test weakened to admit minted rows — the data path is fixed instead.
