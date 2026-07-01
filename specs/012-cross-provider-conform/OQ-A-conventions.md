# OQ-A — Two new conventions drafted (APPROVED governance)

The `create-rule` skill is not installed in this environment, so these rule texts were
drafted directly (duplicate-checked against `CLAUDE.md` — neither exists there yet). Per
tasks.md T004/T005 they are RECORDED here and NOT committed to `CLAUDE.md` in this task;
they LAND in `CLAUDE.md` *Non-obvious constraints* at T036 (S12). OQ-A is APPROVED (team-lead
sign-off): these ARE to be codified.

## Rule A — Provider four-file additions convention (T004, drafted)

> **A Python provider that mints canonical rows writes FOUR additions Parquet files, not one.**
> `data/silver/<provider>_canonical_{match,team,league,season}_additions.parquet` — one per
> canonical entity a minted match references. Minting a match MUST emit (or reuse) its whole
> `season → league → team` chain: a team-addition per un-resolved `home_team_id`/`away_team_id`,
> a season-addition for its `season_id`, a league-addition for that season's `league_id`, and the
> match-addition itself. Identity is **seed-first**: team ids resolve through the `team_aliases`
> seed (`coalesce(seed.team_id, md5(lower(name)))`), league ids through the `league_aliases` seed
> (`coalesce(seed.league_id, mint_provider_scoped(provider, provider_key))`), `season_id =
> md5(league_id || '|' || year)`, and `match_id` via the `canonical_match_id` macro's replica —
> never a raw provider id or a provider-private constant. Each of the four files is
> **bootstrap-written empty (with the correct columns) before any `dbt build`**, because the
> `int_*` models read them with `read_parquet`, which ERRORS on a missing file (it is NOT
> `try_read_parquet`). The Python conform module **never opens a DuckLake connection** (even
> read-only): it reads bronze Parquet + the `canonical_{team,match,league,season}` external-Parquet
> exports and writes the additions files; dbt owns the catalog and unions the files via `read_parquet`
> + `UNION ALL`, then keep-one on the id. ESPN is exempt — it conforms in SQL and is the union base.

## Rule B — `league_aliases` seed convention (T005, drafted)

> **`dbt/data_platform/seeds/league_aliases.csv` maps each provider's league key onto the
> ESPN-anchored canonical `league_id`.** Columns: `league_id, canonical_name, provider,
> provider_key`. The natural key is the composite **`(provider, provider_key)`** — it MUST be
> `unique` (one canonical mapping per provider key), enforced by a zero-dependency SINGULAR test
> under `dbt/data_platform/tests/` (`... group by provider, provider_key having count(*) > 1`
> returns zero rows — no `dbt_utils` dependency). `league_id` and `provider_key` are `not_null`;
> `provider` is `not_null` + `accepted_values(espn|matchbook|football_data)`. `league_id` is
> intentionally **NOT `unique`** — several providers deliberately map onto one ESPN-anchored
> `league_id` (mirroring how `team_aliases` allows many `alias` rows per `team_id`). The seed is
> **ESPN-anchor additive**: it RECORDS ESPN's own mapping (`provider=espn, provider_key=<league_slug>,
> league_id=md5(<league_slug>)`) and maps OTHER providers' keys onto that SAME id — it does NOT
> redefine ESPN identity, so ESPN's `int_league`/`int_match`/`int_espn_*_link` stay byte-for-byte
> unchanged. `provider_key` encoding: ESPN = `league_slug` (e.g. `eng.1`); Matchbook =
> `"<sport_id>|<category_id>"`; football_data = its `<family|division>` key. **Seed-only, no
> auto-learn** (no write-back of provider spellings). Registered in a new
> `dbt/data_platform/seeds/_seeds.yml` (the first `_seeds.yml` in the repo).
