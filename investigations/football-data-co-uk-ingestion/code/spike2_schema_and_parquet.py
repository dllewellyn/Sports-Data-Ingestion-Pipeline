"""SPIKE (disposable) — schema-drift map + bronze Parquet proof.

Answers:
- Q2/H3: how badly do columns drift across seasons/divisions, and across the two
  dataset families (main `mmz4281/...` vs extra `new/<CODE>.csv`)?
- Target output: prove a *validated* bronze Parquet can be produced with Pydantic
  (mandatory core) + Pandera (frame contract), tolerating the optional-column sprawl.

Downloads a representative sample only (polite). Writes:
- evidence/samples/*.csv         (raw downloaded samples, as evidence)
- evidence/spike2_schema_matrix.csv  (column presence across files)
- evidence/spike2_bronze_sample.parquet  (validated, unioned bronze sample)
- evidence/spike2_report.json

Run: uv run python investigations/football-data-co-uk-ingestion/code/spike2_schema_and_parquet.py
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pandas as pd
import requests
from pandera.pandas import Column, DataFrameSchema
from pydantic import BaseModel, ConfigDict, field_validator

BASE = "https://www.football-data.co.uk/"
EV = Path(__file__).resolve().parent.parent / "evidence"
SAMPLES = EV / "samples"
HEADERS = {"User-Agent": "data-platform-investigation-spike/0.1 (+local research)"}

# Representative sample: main-family across eras/divisions + extra-family two countries.
MAIN = [
    "mmz4281/9394/E0.csv",  # earliest England top flight
    "mmz4281/0001/E0.csv",
    "mmz4281/1011/E0.csv",
    "mmz4281/2324/E0.csv",  # recent England top flight
    "mmz4281/2324/E1.csv",  # different division, recent
    "mmz4281/2324/I1.csv",  # Italy, recent
    "mmz4281/2324/SC0.csv",  # Scotland, recent
]
EXTRA = ["new/ARG.csv", "new/USA.csv"]


def get(path: str) -> bytes:
    r = requests.get(BASE + path, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.content


def read_csv(raw: bytes) -> pd.DataFrame:
    # Source is latin-1-ish; tolerate bad lines like the user's original script.
    return pd.read_csv(io.BytesIO(raw), encoding="latin-1", on_bad_lines="skip")


# --- Bronze contract -------------------------------------------------------------
# H3: a STRICT per-file model is impossible. Use a small mandatory CORE and let
# everything else ride along as optional columns. Two families need two cores.

CORE_MAIN = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
CORE_EXTRA = ["Country", "League", "Date", "Home", "Away", "HG", "AG", "Res"]


class MainMatch(BaseModel):
    """Edge contract for ONE main-family record (core fields only)."""

    model_config = ConfigDict(extra="ignore")
    Div: str
    Date: str
    HomeTeam: str
    AwayTeam: str
    FTHG: float | None = None
    FTAG: float | None = None
    FTR: str | None = None

    @field_validator("Div", "HomeTeam", "AwayTeam", mode="before")
    @classmethod
    def _nonempty(cls, v):
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
            raise ValueError("required core field empty")
        return str(v).strip()


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    report: dict = {"files": {}, "families": {}}
    col_presence: dict[str, set[str]] = {}
    frames_main: list[pd.DataFrame] = []

    def handle(path: str, family: str):
        raw = get(path)
        slug = path.replace("/", "__")
        (SAMPLES / slug).write_bytes(raw)
        df = read_csv(raw)
        df = df.dropna(axis=1, how="all")  # trailing empty unnamed cols are common
        cols = [c for c in df.columns if not str(c).startswith("Unnamed")]
        col_presence[path] = set(cols)
        report["files"][path] = {
            "family": family,
            "rows": int(len(df)),
            "n_cols": len(cols),
            "cols_head": cols[:12],
        }
        print(f"{path:<26} rows={len(df):<6} cols={len(cols)}")
        time.sleep(0.4)
        return df

    print("== MAIN family ==")
    for p in MAIN:
        df = handle(p, "main")
        # Pydantic edge validation on the mandatory core, then keep the FULL frame.
        present_core = [c for c in CORE_MAIN if c in df.columns]
        records = df[present_core].to_dict(orient="records")
        ok = 0
        for rec in records:
            try:
                MainMatch.model_validate(rec)
                ok += 1
            except Exception:  # noqa: BLE001 - spike: count failures
                pass
        report["files"][p]["core_valid_rows"] = ok
        df["__source_file"] = p
        df["__season"] = p.split("/")[1] if "mmz4281" in p else None
        frames_main.append(df)

    print("\n== EXTRA family ==")
    for p in EXTRA:
        handle(p, "extra")

    # --- schema drift matrix (main family) ---
    all_cols = sorted(set().union(*[col_presence[p] for p in MAIN]))
    matrix = pd.DataFrame(
        {p.split("/", 1)[1]: [c in col_presence[p] for c in all_cols] for p in MAIN},
        index=all_cols,
    )
    matrix["present_in_n"] = matrix.sum(axis=1)
    matrix = matrix.sort_values("present_in_n", ascending=False)
    matrix.to_csv(EV / "spike2_schema_matrix.csv")

    core_everywhere = [c for c in all_cols if all(c in col_presence[p] for p in MAIN)]
    report["families"]["main"] = {
        "files_sampled": len(MAIN),
        "union_cols": len(all_cols),
        "cols_in_every_file": sorted(core_everywhere),
        "min_cols": min(len(col_presence[p]) for p in MAIN),
        "max_cols": max(len(col_presence[p]) for p in MAIN),
    }
    report["families"]["extra"] = {
        "files_sampled": len(EXTRA),
        "union_cols": len(set().union(*[col_presence[p] for p in EXTRA])),
        "cols": sorted(set().union(*[col_presence[p] for p in EXTRA])),
    }

    # --- bronze Parquet proof (main family, sparse union) ---
    bronze = pd.concat(frames_main, ignore_index=True, sort=False)
    # Frame contract: only the mandatory core is enforced; the rest ride along.
    bronze_schema = DataFrameSchema(
        {
            "Div": Column(str, nullable=False),
            "Date": Column(str, nullable=False),
            "HomeTeam": Column(str, nullable=False),
            "AwayTeam": Column(str, nullable=False),
            "FTHG": Column(float, nullable=True, coerce=True),
            "FTAG": Column(float, nullable=True, coerce=True),
        },
        strict=False,  # tolerate the wide optional-column sprawl
        coerce=True,
    )
    # Drop rows missing mandatory core (e.g. blank trailing rows) before validating.
    before = len(bronze)
    bronze = bronze.dropna(subset=["Div", "HomeTeam", "AwayTeam"])
    validated = bronze_schema.validate(bronze)
    out = EV / "spike2_bronze_sample.parquet"
    validated.to_parquet(out, index=False)
    report["bronze_parquet"] = {
        "path": str(out),
        "rows_in": before,
        "rows_validated": int(len(validated)),
        "total_union_cols": int(validated.shape[1]),
    }
    print(f"\nbronze parquet: {len(validated)} rows, {validated.shape[1]} cols -> {out.name}")

    (EV / "spike2_report.json").write_text(json.dumps(report, indent=2, default=str))
    print("wrote evidence/spike2_report.json + spike2_schema_matrix.csv")


if __name__ == "__main__":
    main()
