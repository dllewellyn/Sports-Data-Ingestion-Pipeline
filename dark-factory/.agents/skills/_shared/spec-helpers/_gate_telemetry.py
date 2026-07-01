"""Best-effort gate telemetry for the spec validators.

When a feature run is active (temp/telemetry/current.json exists), each validator
emits a PASS/FAIL `gate` event tied to the run, so the feature dashboard can show
that a required artifact was validated BEFORE the next phase consumed it. When no
run is active or no collector is reachable this is a silent no-op — the validators'
own logic and exit codes are never affected. The phase label can be overridden with
FEATURE_GATE_PHASE (e.g. trace-check.py runs in several phases)."""

import os
import pathlib
import subprocess
import sys


def emit_gate(artifact, rc, phase):
    try:
        emit = pathlib.Path(__file__).resolve().parents[1] / "telemetry" / "emit.py"
        if not emit.exists():
            return
        subprocess.run(
            [
                sys.executable,
                str(emit),
                "gate",
                "--artifact",
                str(artifact or ""),
                "--verdict",
                "PASS" if rc == 0 else "FAIL",
                "--phase",
                os.environ.get("FEATURE_GATE_PHASE", phase),
            ],
            timeout=5,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001 — telemetry must never affect validation
        pass
