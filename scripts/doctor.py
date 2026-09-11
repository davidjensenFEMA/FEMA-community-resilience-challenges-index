"""
CRIA install doctor — diagnose why the pipeline isn't behaving.

Walks the install in dependency order (env → config → data files → database →
optional API ping) and prints a paste-friendly status report. Designed for
copying the output into chat or attaching as a file when debugging across
machines.

Usage:
    poetry run python scripts/doctor.py                 # human-readable report
    poetry run python scripts/doctor.py --check-api     # also ping Census API
    poetry run python scripts/doctor.py --json          # machine-readable

Exit codes:
    0   all checks passed (WARN allowed)
    1   one or more checks failed
    2   doctor itself errored (very rare — bug in the doctor)
"""

import argparse
import importlib
import json
import logging
import os
import platform
import sys
import traceback

# Quiet the noisy loggers — the doctor's value is the report, not the SQL trace
# or the urllib retry chatter that imports/queries trigger underneath. Engine
# echo=True attaches its own handler, so we also disable propagation and swap in
# a NullHandler before src.db.session ever creates the engine.
for _name in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool",
              "urllib3", "cria"):
    _lg = logging.getLogger(_name)
    _lg.setLevel(logging.WARNING)
    for _h in list(_lg.handlers):
        _lg.removeHandler(_h)
    _lg.addHandler(logging.NullHandler())
    _lg.propagate = False
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, List, Optional

# Resolve project root from this file's location (scripts/doctor.py -> ..)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Make src importable when run outside `poetry run` (best-effort).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

OK, WARN, FAIL, ERROR = "OK", "WARN", "FAIL", "ERROR"


@dataclass
class CheckResult:
    name: str
    status: str  # OK / WARN / FAIL / ERROR
    detail: str = ""
    remediation: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Section:
    name: str
    results: List[CheckResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tier 1 — Environment
# ---------------------------------------------------------------------------

def check_python_version() -> CheckResult:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro} ({sys.executable})"
    if (v.major, v.minor) < (3, 11):
        return CheckResult(
            "Python version", FAIL, detail,
            remediation="pyproject.toml requires Python ^3.11. Recreate the venv with a newer Python.",
        )
    return CheckResult("Python version", OK, detail)


def check_required_packages() -> List[CheckResult]:
    """One result per package — pyarrow gets singled out because it caused the original incident."""
    required = [
        ("pyarrow", "Required to read data/geographies/*.parquet. Without it the pipeline silently falls back to a stripped Census-API geography reference, corrupting EAVS/CBP joins."),
        ("pandas", ""),
        ("sqlalchemy", ""),
        ("mapclassify", ""),
        ("openpyxl", ""),
        ("pydantic_settings", ""),
    ]
    results = []
    for pkg, why in required:
        try:
            mod = importlib.import_module(pkg)
            ver = getattr(mod, "__version__", "?")
            results.append(CheckResult(f"package: {pkg}", OK, f"v{ver}"))
        except ImportError as e:
            results.append(CheckResult(
                f"package: {pkg}", FAIL,
                detail=str(e),
                remediation="Run `poetry install` from the project root." + (f" Why this matters: {why}" if why else ""),
            ))
    return results


# ---------------------------------------------------------------------------
# Tier 2 — Configuration
# ---------------------------------------------------------------------------

def check_dotenv_present() -> CheckResult:
    p = PROJECT_ROOT / ".env"
    if p.exists():
        return CheckResult(".env file", OK, str(p))
    return CheckResult(
        ".env file", WARN,
        detail=f"Not found at {p}",
        remediation="Copy .env.example to .env and fill in CENSUS_API_KEY (and DATABASE_URL if not using the SQLite default).",
    )


def check_cwd_vs_project_root() -> CheckResult:
    """SQLite DATABASE_URL is relative to CWD; running scripts from different dirs creates split DBs."""
    cwd = Path.cwd().resolve()
    if cwd == PROJECT_ROOT:
        return CheckResult("Working directory", OK, str(cwd))
    return CheckResult(
        "Working directory", WARN,
        detail=f"CWD={cwd}, project root={PROJECT_ROOT}",
        remediation=(
            "Run scripts from the project root. SQLite DATABASE_URL=sqlite:///./cria.db "
            "is relative to CWD — running import_reference_data.py and run_full_pipeline.py "
            "from different directories silently creates two separate empty databases."
        ),
    )


def check_census_key() -> CheckResult:
    try:
        from src.config.settings import settings
        from src.api.census_client import _normalize_api_key, validate_census_api_key_format
    except Exception as e:
        return CheckResult(
            "CENSUS_API_KEY", ERROR,
            detail=f"Could not import settings/census_client: {e}",
            remediation="Fix the Tier-1 package failures first.",
        )
    raw = settings.census_api_key
    if not raw:
        return CheckResult(
            "CENSUS_API_KEY", FAIL,
            detail="empty",
            remediation="Set CENSUS_API_KEY in .env. Get a key at api.census.gov/data/key_signup.html (and click the activation link in the email).",
        )
    normalized, notes = _normalize_api_key(raw)
    masked = f"{normalized[:4]}…{normalized[-4:]} (len={len(normalized)})" if len(normalized) >= 8 else "(too short to mask safely)"
    reason = validate_census_api_key_format(normalized)
    if reason:
        return CheckResult(
            "CENSUS_API_KEY", WARN,
            detail=f"{masked} — {reason}",
            remediation="Census keys are 40 lowercase-hex characters. Re-paste from the activation email if this looks off.",
            extra={"normalize_notes": notes},
        )
    return CheckResult(
        "CENSUS_API_KEY", OK,
        detail=f"{masked} (format OK)",
        extra={"normalize_notes": notes},
    )


def check_database_url() -> CheckResult:
    try:
        from src.config.settings import settings
    except Exception as e:
        return CheckResult(
            "DATABASE_URL", ERROR,
            detail=f"Could not import settings: {e}",
        )
    url = settings.database_url
    detail = url
    if url.startswith("sqlite:///"):
        # Resolve the SQLite path so the user sees where the file actually lands.
        rel = url.removeprefix("sqlite:///")
        resolved = (Path(rel) if Path(rel).is_absolute() else Path.cwd() / rel).resolve()
        exists = resolved.exists()
        detail = f"{url}  →  {resolved}  ({'file exists' if exists else 'file NOT YET created'})"
        return CheckResult("DATABASE_URL", OK, detail)
    return CheckResult("DATABASE_URL", OK, detail)


# ---------------------------------------------------------------------------
# Tier 3 — Data files
# ---------------------------------------------------------------------------

def check_reference_excel() -> CheckResult:
    try:
        from src.config.paths import paths
    except Exception as e:
        return CheckResult("Reference Excel", ERROR, detail=f"Could not import paths: {e}")
    p = paths.reference_file
    if not p.exists():
        return CheckResult(
            "Reference Excel", FAIL,
            detail=f"Not found at {p}",
            remediation="Place cria_data_reference.xlsx under data/ — it's the source of truth for indicator definitions.",
        )
    return CheckResult("Reference Excel", OK, detail=str(p))


def check_geography_parquets() -> List[CheckResult]:
    """Each parquet checked individually — exposes the original pyarrow incident clearly."""
    try:
        from src.config.paths import paths
        import pandas as pd
    except Exception as e:
        return [CheckResult("Geography parquets", ERROR, detail=f"Could not import: {e}")]
    geo_dir = paths.data / "geographies"
    levels = ["state", "county", "tract", "tribal"]
    results = []
    if not geo_dir.exists():
        return [CheckResult(
            "Geography parquets", FAIL,
            detail=f"Directory not found: {geo_dir}",
            remediation="Run `poetry run python scripts/sync_geographies.py --level <level>` for each level, or restore from version control.",
        )]
    for lvl in levels:
        pq = geo_dir / f"{lvl}.parquet"
        if not pq.exists():
            results.append(CheckResult(
                f"parquet: {lvl}", FAIL,
                detail=f"Missing: {pq}",
                remediation=f"`poetry run python scripts/sync_geographies.py --level {lvl}`",
            ))
            continue
        try:
            df = pd.read_parquet(pq)
        except ImportError as e:
            results.append(CheckResult(
                f"parquet: {lvl}", FAIL,
                detail=f"No parquet engine: {e}",
                remediation="Run `poetry install` to install pyarrow.",
            ))
            continue
        except Exception as e:
            results.append(CheckResult(
                f"parquet: {lvl}", FAIL,
                detail=f"Read failed: {e}",
                remediation=f"File may be corrupt. Re-run sync_geographies.py --level {lvl} or restore from git.",
            ))
            continue
        nan_idx = int(df.index.isna().sum()) if len(df) else 0
        idx_name = df.index.name
        if nan_idx > 0 or idx_name != "GEO_ID" or len(df) == 0:
            results.append(CheckResult(
                f"parquet: {lvl}", WARN,
                detail=f"shape={df.shape}, index_name={idx_name}, NaN_indices={nan_idx}",
                remediation="Expected GEO_ID-indexed DataFrame with no NaN indices. Re-sync this level.",
            ))
        else:
            results.append(CheckResult(
                f"parquet: {lvl}", OK,
                detail=f"shape={df.shape}, GEO_ID indexed",
            ))
    return results


# ---------------------------------------------------------------------------
# Tier 4 — Database
# ---------------------------------------------------------------------------

def check_database() -> List[CheckResult]:
    """Connect, then count critical tables. Each table is a separate result line."""
    results = []
    try:
        from sqlalchemy import select, func
        from src.db.session import get_db_session
        from src.db.models import ReferenceIndicator, DataYear, Geography
    except Exception as e:
        return [CheckResult("Database", ERROR, detail=f"Could not import db modules: {e}")]

    try:
        db = get_db_session()
    except Exception as e:
        return [CheckResult(
            "Database connection", FAIL,
            detail=str(e),
            remediation="Check DATABASE_URL. For PostgreSQL: is the docker container up? For SQLite: does the parent dir exist?",
        )]

    try:
        # Use a trivial query to confirm we can actually round-trip.
        try:
            ref_count = db.execute(select(func.count()).select_from(ReferenceIndicator)).scalar() or 0
        except Exception as e:
            results.append(CheckResult(
                "Database connection", FAIL,
                detail=f"Connected but query failed: {e}",
                remediation="Schema may not be migrated. Run `poetry run alembic upgrade head`.",
            ))
            return results

        results.append(CheckResult("Database connection", OK))

        if ref_count == 0:
            results.append(CheckResult(
                "reference_indicators table", FAIL,
                detail="0 rows — pipeline cannot persist indicators",
                remediation="`poetry run python scripts/import_reference_data.py`",
            ))
        else:
            results.append(CheckResult("reference_indicators table", OK, detail=f"{ref_count} rows"))

        year_count = db.execute(select(func.count()).select_from(DataYear)).scalar() or 0
        if year_count == 0:
            results.append(CheckResult(
                "data_years table", WARN,
                detail="0 rows",
                remediation="`poetry run python scripts/import_reference_data.py` (populates this too)",
            ))
        else:
            results.append(CheckResult("data_years table", OK, detail=f"{year_count} rows"))

        # Per-level geography counts (each line easy to scan in chat)
        for lvl in ["state", "county", "tract", "tribal"]:
            n = db.execute(
                select(func.count()).select_from(Geography).where(Geography.geography_level == lvl)
            ).scalar() or 0
            if n == 0:
                results.append(CheckResult(
                    f"geographies: {lvl}", WARN,
                    detail="0 rows",
                    remediation=f"`poetry run python scripts/sync_geographies.py --level {lvl}`",
                ))
            else:
                results.append(CheckResult(f"geographies: {lvl}", OK, detail=f"{n} rows"))
    finally:
        db.close()
    return results


# ---------------------------------------------------------------------------
# Tier 5 — Optional Census API ping
# ---------------------------------------------------------------------------

def check_census_api_reachable() -> CheckResult:
    """Tiny request that exercises auth + connectivity. Off by default — adds latency."""
    try:
        from src.api.census_client import CensusAPIClient
    except Exception as e:
        return CheckResult("Census API ping", ERROR, detail=f"import failed: {e}")
    try:
        client = CensusAPIClient()
        # Single state, single column — cheapest meaningful call.
        df = client.fetch_acs_data(["B01001_001E"], geography="state")
        return CheckResult("Census API ping", OK, detail=f"got {len(df)} rows for state geography")
    except Exception as e:
        return CheckResult(
            "Census API ping", FAIL,
            detail=f"{type(e).__name__}: {e}",
            remediation=(
                "If body says 'Invalid Key': the key may not be activated yet — check email for "
                "'Your Census Bureau API Key Request'. If unknown variable: ACS_YEAR may be wrong "
                "(ACS 5-year ships in Dec of year+1)."
            ),
        )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_check(label: str, fn: Callable) -> List[CheckResult]:
    """Wrap a check function so a bug in the doctor itself doesn't crash the doctor."""
    try:
        out = fn()
        return out if isinstance(out, list) else [out]
    except Exception:
        tb = traceback.format_exc(limit=3)
        return [CheckResult(label, ERROR, detail=f"doctor itself failed:\n{tb}")]


def collect(check_api: bool) -> List[Section]:
    sections = [
        Section("Environment", [
            *run_check("python", check_python_version),
            *run_check("packages", check_required_packages),
        ]),
        Section("Configuration", [
            *run_check(".env", check_dotenv_present),
            *run_check("cwd", check_cwd_vs_project_root),
            *run_check("CENSUS_API_KEY", check_census_key),
            *run_check("DATABASE_URL", check_database_url),
        ]),
        Section("Data files", [
            *run_check("reference_excel", check_reference_excel),
            *run_check("geography_parquets", check_geography_parquets),
        ]),
        Section("Database", run_check("database", check_database)),
    ]
    if check_api:
        sections.append(Section("External APIs", run_check("census_api", check_census_api_reachable)))
    return sections


def render_text(sections: List[Section]) -> str:
    """Plain text output — fixed-width, paste-friendly for chat."""
    lines = []
    lines.append("=" * 70)
    lines.append("FEMA CRIA — install doctor")
    lines.append(f"Project root : {PROJECT_ROOT}")
    lines.append(f"Working dir  : {Path.cwd()}")
    lines.append(f"Python       : {sys.version.split()[0]} ({sys.executable})")
    lines.append(f"Platform     : {platform.platform()}")
    lines.append("=" * 70)
    remediations = []
    for sec in sections:
        lines.append(f"\n[{sec.name}]")
        for r in sec.results:
            tag = f"[{r.status:<5}]"
            line = f"  {tag} {r.name}"
            if r.detail:
                line += f"  —  {r.detail}"
            lines.append(line)
            if r.status in (FAIL, WARN, ERROR) and r.remediation:
                remediations.append((r.name, r.status, r.remediation))
    lines.append("\n" + "=" * 70)
    if remediations:
        lines.append("ACTION ITEMS")
        lines.append("=" * 70)
        for name, status, rem in remediations:
            lines.append(f"\n  [{status}] {name}")
            for sub in rem.split(". "):
                if sub:
                    lines.append(f"      → {sub.rstrip('.')}.")
    else:
        lines.append("All checks passed.")
    lines.append("=" * 70)
    return "\n".join(lines)


def render_json(sections: List[Section]) -> str:
    payload = {
        "project_root": str(PROJECT_ROOT),
        "cwd": str(Path.cwd()),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "sections": [
            {"name": s.name, "results": [asdict(r) for r in s.results]}
            for s in sections
        ],
    }
    return json.dumps(payload, indent=2)


def overall_exit_code(sections: List[Section]) -> int:
    for sec in sections:
        for r in sec.results:
            if r.status in (FAIL, ERROR):
                return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Diagnose CRIA install state.")
    parser.add_argument("--check-api", action="store_true",
                        help="Also ping Census API (adds a network call, off by default).")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON instead of text.")
    args = parser.parse_args()

    try:
        sections = collect(check_api=args.check_api)
    except Exception:
        traceback.print_exc()
        sys.exit(2)

    if args.json:
        print(render_json(sections))
    else:
        print(render_text(sections))

    sys.exit(overall_exit_code(sections))


if __name__ == "__main__":
    main()
