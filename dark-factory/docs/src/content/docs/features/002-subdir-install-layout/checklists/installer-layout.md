---
title: "Installer Layout & Migration Requirements Quality Checklist: Subdir Install Layout"
---

# Installer Layout & Migration Requirements Quality Checklist: Subdir Install Layout

**Purpose**: Domain-focused "unit tests for English" validating that the *requirements* for the subdir
install layout — filesystem placement, root-symlink wiring, migration/relocation safety, idempotency &
no-clobber, dry-run, and symlink relative-depth correctness — are unambiguous, testable, complete,
consistent, and bounded in scope. This validates the requirements writing, NOT the installer behaviour.
**Created**: 2026-06-30
**Feature**: [spec.md](../spec.md)
**Focus chosen (non-interactive)**: installer behaviour-change with filesystem-layout requirements —
migration, idempotency, dry-run, symlink/relative-depth correctness. Rationale recorded in Notes.

## Filesystem Layout Completeness & Boundedness

- [x] CHK017 Is the exact set of payloads that move into `dark-factory/` enumerated, with no "etc."? [Completeness, Spec §FR-001] — `.agents`, `.specify`, `telemetry`, `docs`, `AGENTS.md` listed explicitly and repeated in Scope constraint.
- [x] CHK018 Is the name of the destination subdirectory fixed unambiguously rather than left to choice? [Clarity, Spec §Assumptions] — literally `dark-factory/`, recorded as a settled assumption.
- [x] CHK019 Are `specs/`/`plans/` explicitly excluded from relocation and required to remain real root directories? [Boundedness, Spec §FR-004] — stated in FR-004, Scope constraint, and E7.
- [x] CHK020 Is the post-install root state defined as an absence assertion ("no real X at root"), making it objectively testable? [Measurability, Spec §FR-002, §SC-001] — SC-001 asserts no real payload at root + payload present under `dark-factory/`.
- [x] CHK021 Is the distinction between a *real* directory/file and a *symlink* at the root made explicit everywhere it matters? [Clarity, Spec §FR-002, §FR-011] — FR-002 "no real", FR-011 "real (non-symlink)", migration-detection assumption all distinguish them.

## Root Symlink Set & Resolution

- [⚠] CHK022 Is the *complete* set of root symlinks to wire enumerated, or is its derivation deferred? [Completeness, Spec §FR-003] — FR-003 names a MINIMUM set (`.claude/skills`, `CLAUDE.md`, `.agents`, `.specify`, docs-site links) and defers the exact/complete set to "derived from current install.sh" in planning. Bounded and explicitly deferred, not silently vague — acceptable for a spec, but the complete list is NOT yet a fixed requirement.
- [x] CHK023 Is each root symlink required to *resolve* to an existing path under `dark-factory/`, not merely to exist? [Measurability, Spec §SC-002, §FR-003] — SC-002 requires every required symlink resolve to an existing path; AS US1#2 echoes this.
- [x] CHK024 Are the helper/Claude-Code paths that MUST resolve from the root named concretely so coverage is checkable? [Clarity, Spec §SC-003, §Constraints] — `.specify/feature.json`, `.agents/skills/<any-skill>`, `specs/NNN-<slug>` named in SC-003 and the Hard constraint.
- [x] CHK025 Is the `docs/CLAUDE.md` link's conditional nature (wired only when present in SOURCE) stated as a requirement rather than assumed? [Clarity, Spec §FR-005] — FR-005 mandates it stay conditional "not made unconditional".

## Symlink Relative-Depth Correctness

- [x] CHK026 Are relative-depth requirements for relocated links specified as "resolve to the intended root target" rather than a hardcoded `../` count? [Clarity, Spec §FR-005] — FR-005 requires correct relative depth for the new location; outcome stated, not a brittle literal.
- [x] CHK027 Is the relative-depth-correctness class scoped to *all* affected links (docs-site links AND `.claude/skills`/`CLAUDE.md`), not only the docs links? [Coverage, Spec §Assumptions, §E6] — Assumptions explicitly extend the class to `.claude/skills` and `CLAUDE.md`.
- [x] CHK028 Is the one genuinely-open depth question (extra `../` after `docs/` moves deeper) recorded with a best-guess answer and a deterministic resolution path, not left as a blocking ambiguity? [Ambiguity, Spec §Open Questions] — Open Questions #1 gives best-guess (+1 `../`) and says verify by resolving the link; marked not-a-blocker.
- [x] CHK029 Is cross-platform (BSD/macOS + GNU) correctness of the relative-depth math stated as a requirement? [Coverage, Spec §Constraints] — Symlink portability constraint requires the depth math work on both.

## Migration / Relocation Safety

- [x] CHK030 Is migration *detection* defined by an objective signal (a real, non-symlink payload at root) rather than vaguely "a prior install"? [Clarity, Spec §Assumptions] — Detection-by-real-payload assumption; explicitly contrasts the current existence-only check that would misfire.
- [x] CHK031 Is the no-dual-layout outcome stated as a hard post-condition (zero real framework payloads remain at root after relocation)? [Measurability, Spec §FR-007, §SC-005] — FR-007 + SC-005 assert no real payload remains post-migration.
- [x] CHK032 Is "move (not copy-then-leave)" specified so a surviving flat copy is impossible by construction? [Clarity, Spec §Assumptions, §FR-007] — Assumption mandates a move; FR-007 forbids the dual layout.
- [x] CHK033 Is partial/interrupted prior migration (mixed flat + subdir) covered with a defined convergent outcome? [Coverage, Edge Case, Spec §E3] — E3 requires completing the relocation onto the single subdir layout.
- [x] CHK034 Is preservation of the user's own `specs/`/`plans`/other content during migration stated as a requirement, not just a hope? [Completeness, Spec §FR-014, §E7] — FR-014 + E7 require user content untouched.
- [x] CHK035 Is migration *reporting* (naming which payloads were relocated) required, satisfying the honesty-about-destructive-steps constraint? [Completeness, Spec §FR-017, §Constraints] — FR-017 mandates naming relocated payloads; Honesty constraint reinforces.

## Idempotency, No-Clobber & Force

- [x] CHK036 Is a no-`--force` re-run defined as producing an identical layout with nothing newly copied/relocated? [Measurability, Spec §FR-010, §SC-006] — FR-010 + SC-006 define idempotent re-run with skip reporting.
- [x] CHK037 Is no-clobber of a pre-existing *real* file where a symlink belongs specified, with "warn, don't clobber"? [Clarity, Spec §FR-011, §E1] — FR-011 + E1 require leaving the real file and warning.
- [x] CHK038 Is `--force` behaviour bounded to exactly (overwrite copied payloads + repoint root symlinks) without erroring on pre-existing entries? [Clarity, Spec §FR-012, §SC-006] — FR-012 defines the precise force semantics.
- [x] CHK039 Is the stale-symlink case (a root link pointing at the old flat location) given distinct force vs non-force behaviour? [Coverage, Edge Case, Spec §E2] — E2 specifies repoint under `--force`, skip-and-report without.
- [x] CHK040 Is no-clobber of a differing pre-existing file *under* `dark-factory/` specified separately from the root-symlink case? [Coverage, Edge Case, Spec §E4] — E4 covers subdir file conflicts with the same force gate.

## Dry-Run Guarantee

- [x] CHK041 Is `--dry-run` required to make *zero* filesystem changes, stated as an objectively checkable invariant? [Measurability, Spec §FR-009, §SC-004] — FR-009 "zero changes"; SC-004/E8 assert filesystem unchanged (byte-for-byte per Independent Test).
- [x] CHK042 Is the dry-run *output content* specified (payloads bound for subdir, symlinks + their targets, migration relocations) so the preview's completeness is testable? [Completeness, Spec §FR-009, §US3] — FR-009 enumerates the planned-output content; US3 acceptance scenarios cover clean + flat targets.

## Existing-Guard Preservation & Anti-Accretion

- [x] CHK043 Is preservation of the self-copy and nested SOURCE/TARGET guards stated, *and extended* so `dark-factory/` cannot collide with the source? [Completeness, Spec §FR-013, §E5] — FR-013 + E5 require both the existing guards and the new collision guard.
- [x] CHK044 Is the prohibition on a dual flat+subdir mode stated as an explicit requirement (not only implied by the migration)? [Consistency, Spec §FR-008, §Constraints] — FR-008 forbids a dual mode outright; aligns with Constitution I (no accretion).
- [x] CHK045 Is removal of the old flat-install code path required (replace, not preserve alongside)? [Consistency, Spec §Constraints] — "No backward compatibility" constraint requires the flat path removed, not kept.
- [x] CHK046 Is the `.gitignore` merge requirement adjusted for the new layout without duplicating/rewriting user rules, and is its one open question (whether `dark-factory/temp/` is needed) recorded with a resolution path? [Consistency, Spec §FR-015, §Open Questions] — FR-015 covers the merge; Open Questions #2 records the `temp/` coverage question with a deterministic check and marks it not-a-blocker.

## Consistency, Traceability & Conflict

- [x] CHK047 Do the Success Criteria (SC-001..SC-006) each trace back to one or more functional requirements without contradiction? [Consistency, Traceability] — SC-001↔FR-001/002, SC-002↔FR-003/004, SC-003↔Constraints, SC-004↔FR-009, SC-005↔FR-006/007, SC-006↔FR-010/012; no conflicts found.
- [x] CHK048 Are the Constitution-I tensions (migration could accrete) surfaced in-spec rather than papered over? [Conflict, Spec §FR-007/008, §US2] — US2 "Why this priority" and Constraints name Constitution I explicitly and resolve it via FR-007/008.
- [x] CHK049 Are all three Open/Assumption "best-guess" defaults non-blocking and deterministically resolvable in planning, with none hiding an unresolved scope contradiction? [Ambiguity] — both Open Questions and every Assumption default carry a rationale + resolution path; none alter feature scope.

## Notes

- **Focus rationale**: Non-interactive run. The pre-existing `requirements.md` is a coarse, generic
  spec-quality pass (content quality / mandatory sections / testability) and is already all-ticked. The
  highest-value requirements-quality scrutiny remaining for THIS feature is its domain risk surface —
  filesystem layout, migration relocation safety, idempotency/no-clobber semantics, dry-run zero-change,
  and symlink relative-depth correctness. This checklist tests whether *those* requirements are written
  well (unambiguous, testable, bounded), complementing rather than duplicating `requirements.md`.
- IDs continue from `requirements.md` (last CHK016) → this file starts at CHK017, per the skill's
  append-and-continue numbering rule (separate file, shared ID sequence).
- **Validation verdict legend**: `[x]` = the requirement is written to the quality bar (clear/testable/
  bounded). `[⚠]` = acceptable but with a noted caveat (see CHK022 — complete symlink set deferred to
  planning by design, not yet a fixed requirement). No `[ ]` (failing) items.
- **One caveat, not a blocker (CHK022)**: FR-003 fixes a MINIMUM symlink set and explicitly defers the
  *complete* set to derivation from the live `install.sh` in planning. This is a bounded, intentional
  deferral recorded in Assumptions — it does not leave scope unbounded — but the plan phase must
  confirm the exact list/strings so no entry point is dropped (FR-003 already mandates this).
