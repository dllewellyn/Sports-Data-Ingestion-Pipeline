---
title: "Requirements Quality Checklist: Subdir Install Layout"
---

# Requirements Quality Checklist: Subdir Install Layout

**Purpose**: Validate the quality and completeness of `spec.md` before planning.
**Created**: 2026-06-30
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] CHK001 No implementation detail beyond what defines the outcome (the layout vocabulary — `dark-factory/` subdir, root symlinks, payloads — is the requirement; no internal shell-function design prescribed beyond naming existing guarantees)
- [x] CHK002 Focused on user value (a developer installing/migrating the framework without polluting their repo root, while Claude Code and helpers keep working)
- [x] CHK003 All mandatory sections present (User Scenarios, Requirements, Success Criteria, Constraints, Assumptions, Open Questions)
- [x] CHK004 Template guidance comments removed from the spec

## Requirement Completeness

- [x] CHK005 No stray `[NEEDS CLARIFICATION]` markers (0 used; the one docs-link depth tension is recorded in Open Questions with a best-guess answer)
- [x] CHK006 Each functional requirement is objectively testable (FR-001..FR-016)
- [x] CHK007 Success criteria are measurable and technology-agnostic (SC-001..SC-006 assert filesystem state, not implementation)
- [x] CHK008 Acceptance scenarios are defined for every user story (BDD Given/When/Then across US1..US4)
- [x] CHK009 Edge cases identified with expected behaviour (E1..E8)
- [x] CHK010 Scope is bounded (framework payloads only move; `specs/`/`plans/` stay real at root; no dual mode)
- [x] CHK011 Dependencies and assumptions identified (symlink set derived from current install.sh, existing guards, `.gitignore` merge, migration detection signal)

## Feature Readiness

- [x] CHK012 Stories are prioritised (P1, P1, P2, P2) and each is independently testable
- [x] CHK013 Happy path (fresh install), migration, dry-run preview, and idempotency/no-clobber all covered by scenarios
- [x] CHK014 No constitution principle contradicted; the no-accretion / no-dual-layout requirement (Constitution I) is made explicit (FR-007, FR-008) rather than papered over
- [x] CHK015 `.specify/feature.json` points at `specs/002-subdir-install-layout`
- [x] CHK016 `validate-spec.py` passes on `spec.md`

## Notes

- The single material open item (docs-site symlink relative depth after `docs/` moves into
  `dark-factory/docs/`) is recorded under Open Questions with a best-guess answer (add one `../`). It is
  not a build blocker — resolvable deterministically in the plan/implement phase by resolving the link.
- The user locked three decisions as settled requirements: (1) scope = framework payloads only,
  `specs/`/`plans/` stay real at root; (2) root must expose Claude-Code/helper paths via symlinks — a
  hard constraint, not a choice; (3) migration is a one-time relocation that replaces the flat layout
  (no dual mode). These are encoded as FR-001..FR-008/FR-014 and the Constraints section, not as open
  questions.
- The exact, complete root-symlink set is to be confirmed against the live `install.sh` during planning
  (FR-003 requires deriving it from the current script); the Assumptions record the expected set.
