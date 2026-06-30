# Tasks template

The **exact output format** for `<feature_dir>/tasks.md`. Keep the phase structure and the task-line
format. Remove `<!-- guidance -->` comments from the final file.

Task line format: `- [ ] T### [P?] [USn?] [Sn] <description with exact file path>`
- **T###** sequential execution-order id · **[P]** file-disjoint, no unmet dependency · **[USn]** the
  user story · **[Sn]** the plan step this task implements (required on test/impl tasks).

The linter is `_shared/spec-helpers/validate-tasks.py`; `trace-check.py` proves every plan step has a task.

---

```markdown
# Tasks: [FEATURE NAME]

**Feature directory**: `specs/NNN-<slug>/`
**Date**: YYYY-MM-DD
**Plan**: `plan.md`
**Status**: Draft   <!-- Draft | In-progress | Done -->

## Phase 1: Setup (shared infrastructure)

- [ ] T001 [S0] Establish pytest harness + pre-commit in <paths> (from plan step S0)
- [ ] T002 [P] [S0] Configure ruff lint/format per pyproject.toml

## Phase 2: Foundational (blocking prerequisites)

> No user-story work begins until this phase completes.

- [ ] T003 [Sn] Create base <entity/contract> in <path>

## Phase 3: User Story 1 — [title] (Priority: P1) 🎯 MVP

**Goal**: [what this story delivers]
**Independent Test**: [how to verify it alone]

- [ ] T004 [P] [US1] [S1] Write failing test for <behaviour> in tests/<path> (red — must fail first)
- [ ] T005 [US1] [S1] Implement <behaviour> in src/<path> (green)

**Checkpoint**: User Story 1 independently functional and testable.

## Phase 4: User Story 2 — [title] (Priority: P2)

**Goal**: …
**Independent Test**: …

- [ ] T006 [P] [US2] [S2] Write failing test in tests/<path>
- [ ] T007 [US2] [S2] Implement in src/<path>

**Checkpoint**: User Stories 1 and 2 both work independently.

<!-- add a phase per prioritised user story -->

## Phase N: Polish & cross-cutting

- [ ] T0XX [P] [setup] Documentation updates in docs/
- [ ] T0XX [setup] Run quickstart.md validation

## Dependencies & Execution Order

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — blocks all user stories.
- **User Stories (Phase 3+)**: depend on Foundational; then parallel or in priority order P1 → P2 → …
- **Within a story**: failing test before implementation; models → services → wiring.
- **Repo ordering gotchas** (from plan): bronze→silver→gold; single-writer DuckDB; prefixed dbt asset keys.

### Parallel opportunities

- [P] tasks in the same phase touch disjoint files and can run concurrently.
- Different user stories can proceed in parallel once Foundational completes.

## Notes

- [P] = different files, no unmet dependency. A wrong [P] causes parallel write conflicts.
- [Sn] links each task to its plan step (traceability). [USn] maps it to a user story.
- Verify tests fail before implementing. Commit after each task or logical group.
```
