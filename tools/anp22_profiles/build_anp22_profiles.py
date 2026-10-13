#!/usr/bin/env python3
"""
Amend ``default_aircraft_profiles.csv`` and the default profile columns of
``default_aircraft.csv`` so that every ANP v2.2 aircraft has its own profiles,
with a ``power`` column the plugin can use, and every aircraft type defaults to
a type-specific ANP v2.2 profile where a proxy can be determined.

The amendment is a deterministic correction of the 5.3.5 tables (git revision
``c8a55cd``), not a recomputation: the x, z and TAS of every existing ANP v2.2
profile are kept (they already follow ANP v2.2 at ISA, sea level; see
``documents/AIRCRAFT_PROFILES_PROVENANCE.md``).

Inputs
------
* the 5.3.5 tables (read from git revision ``c8a55cd`` by default, or from
  ``--base-profiles`` / ``--base-aircraft``); their md5 is checked;
* the ANP v2.2 tables (``--anp-dir``): ``Aircraft.csv``, ``Default_weights.csv``,
  ``Default_fixed_point_profiles.csv`` and the substitution workbook
  ``ANP v2.2 Aircraft substitutions - jets & heavy props (22022018).xlsx``.
  No other ANP release is read.

Outputs
-------
* ``open_alaqs/database/data/default_aircraft_profiles.csv``
* ``open_alaqs/database/data/default_aircraft.csv``
* ``tools/anp22_profiles/output/profile_build_log.csv`` (one row per profile:
  origin, power treatment, capped points, weight source)
* ``tools/anp22_profiles/output/default_aircraft_mapping.csv`` (one row per
  aircraft type: old and new defaults, rule, source)

Usage (from the repository root)::

    python3 tools/anp22_profiles/build_anp22_profiles.py --anp-dir /path/to/anp_v2_2

Re-runnable; byte-identical output for the same inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "open_alaqs" / "database" / "data"
OUT_DIR = Path(__file__).resolve().parent / "output"

BASE_REV = "c8a55cd"
BASE_MD5 = {
    "default_aircraft_profiles.csv": "c15a3e26b21e29fcf1edd2b0472921f8",
    "default_aircraft.csv": "ad1c2604f7b5f44d8b338c760ee49451",
}
WORKBOOK = "ANP v2.2 Aircraft substitutions - jets & heavy props (22022018).xlsx"

# Unit conversions used by every ANP row of the 5.3.5 table (checked on the
# 7,900+ rows of the pre-2024 table that still carried both unit systems).
FT_TO_M = 0.3048
KT_TO_MS = 0.514444
LB_TO_KG = 0.453592

# Rows that are not ANP v2.2 type profiles and are left untouched (none in
# the 5.3.5 table; kept for safety).
UNTOUCHED_PREFIXES = ("HELIPROF-",)
# ANP 2.1 profiles (COMJET, DHC-2FLT, GASEPF; 13 profiles, 137 rows) are
# removed: no aircraft type defaults to them, no fixture uses them, they have
# no weight and no power, and the catalogue is ANP v2.2 only.
DROPPED_PREFIXES = ("COMJET-", "DHC-2FLT-", "GASEPF-")
GROUP_RE = re.compile(r"^(JET-[A-Z]+|PISTON|TURBOPROP)-[AD]-\d+$")
TYPE_RE = re.compile(r"^(?P<ac>.+)-(?P<ad>[AD])-(?P<stage>\d+)$")

# Source of every group profile. Commit ab42da5 (2024-09-26) created the
# groups by renaming these type profiles; the table before that commit holds
# each of them with identical rows (imperial and metric columns, power,
# weight). Where two type profiles were identical (DC930/DC93LW,
# DC950/DC95HW) the one that disappeared in ab42da5 is listed.
GROUP_SOURCE = {
    "JET-BUSINESS-A-1": "GIIB-A-1",
    "JET-BUSINESS-D-1": "CNA510-D-1",
    "JET-BUSINESS-D-2": "CNA500-D-1",
    "JET-BUSINESS-D-3": "LEAR35-D-1",
    "JET-BUSINESS-D-4": "CNA680-D-1",
    "JET-BUSINESS-D-5": "EMB145-D-1",
    "JET-BUSINESS-D-6": "GIIB-D-1",
    "JET-LARGE-A-1": "A330-343-A-1",
    "JET-LARGE-D-1": "A310-304-D-1",
    "JET-LARGE-D-2": "A310-304-D-2",
    "JET-LARGE-D-3": "767CF6-D-3",
    "JET-LARGE-D-4": "A330-301-D-4",
    "JET-LARGE-D-5": "7478-D-1",
    "JET-LARGE-D-6": "7478-D-2",
    "JET-LARGE-D-7": "A300B4-203-D-2",
    "JET-MEDIUM-A-1": "A330-301-A-1",
    "JET-MEDIUM-D-1": "CNA750-D-1",
    "JET-MEDIUM-D-2": "DC930-D-1",
    "JET-MEDIUM-D-3": "A320-211-D-2",
    "JET-MEDIUM-D-4": "A321-232-D-2",
    "JET-MEDIUM-D-5": "767400-D-2",
    "JET-MEDIUM-D-6": "A330-301-D-2",
    "JET-MEDIUM-D-7": "A330-301-D-3",
    "JET-REGIONAL-A-1": "BAE300-A-1",
    "JET-REGIONAL-D-1": "CL601-D-1",
    "JET-REGIONAL-D-2": "CRJ9-ER-D-1",
    "JET-REGIONAL-D-3": "DC950-D-1",
    "JET-REGIONAL-D-4": "MD9028-D-1",
    "JET-REGIONAL-D-5": "BAE300-D-1",
    # JET-SMALL-A-1 is a copy of A320-232-A-1, which is still in the table.
    "JET-SMALL-A-1": "A320-232-A-1",
    "JET-SMALL-D-1": "LEAR25-D-1",
    "JET-SMALL-D-2": "A319-131-D-1",
    "JET-SMALL-D-3": "A320-211-D-1",
    "JET-SMALL-D-4": "A321-232-D-1",
    "JET-SMALL-D-5": "757PW-D-1",
    "JET-SMALL-D-6": "757300-D-1",
    "PISTON-A-1": "PA30-A-1",
    "PISTON-D-1": "ECLIPSE500-D-1",
    "PISTON-D-2": "CNA208-D-1",
    "PISTON-D-3": "PA30-D-1",
    "PISTON-D-4": "BEC58P-D-1",
    "TURBOPROP-A-1": "HS748A-A-1",
    "TURBOPROP-D-1": "CNA441-D-1",
    "TURBOPROP-D-2": "DO228-D-1",
    "TURBOPROP-D-3": "SD330-D-1",
    "TURBOPROP-D-4": "IA1125-D-1",
    "TURBOPROP-D-5": "DHC7-D-1",
    "TURBOPROP-D-6": "HS748A-D-1",
}

# Groups whose source is of another propulsion class get a same-class source.
GROUP_REPLACEMENT = {
    "PISTON-D-1": "CNA172-D-1",  # was ECLIPSE500 (a jet)
    "PISTON-D-2": "PA31-D-1",  # was CNA208 (a turboprop)
    "TURBOPROP-D-4": "EMB120-D-1",  # was IA1125 (a jet)
}

# Profiles rebuilt from the ANP v2.2 fixed-point table.
#  * 757300-A-1: only its last 4 points survived commit e9b087b, which renamed
#    the first 27 rows; the v2.2 fixed points restore all 31.
#  * CNA206-D-1: in ANP v2.2 the CNA206 'DEFAULT' departure (labelled stage 1)
#    is point for point the '3600LB' departure (stage 3, = CNA206-D-3), while
#    the stage-1 weight is 3,000 lb. CNA206-D-1 is rebuilt from '3000LB', as
#    CNA20T-D-1 already is. The mode sequence of the existing row set is kept.
FIXED_POINT_REBUILD = {
    "757300-A-1": ("757300", "A", "DEFAULT", "1"),
    "CNA206-D-1": ("CNA206", "D", "3000LB", "1"),
}

POWER_CAP = 1.0

# Substitution workbook codes with engine or model variants: the variant used
# for each type of default_aircraft.csv, the default engine the choice relies
# on (checked at build time), and the basis. Where the default engine does not
# identify a variant, the first row of the workbook is used (handoff D8).
VARIANT_CHOICE = {
    # code: (expected engine, expected engine_name, chosen proxy, basis)
    "A20N": (
        "01P20CM128",
        "LEAP-1A26/26E1",
        "A320-211",
        "engine LEAP-1A26 (CFM) -> 'A320neo CFM engines'",
    ),
    "A320": (
        "1CM008",
        "1CM008",
        "A320-211",
        "engine UID manufacturer code CM (CFM) -> 'CFM engines'",
    ),
    "A332": (
        "2GE051",
        "2GE051",
        "A330-301",
        "engine UID manufacturer code GE -> 'GE or PW engines'",
    ),
    "A333": (
        "2GE051",
        "2GE051",
        "A330-301",
        "engine UID manufacturer code GE -> 'GE or PW engines'",
    ),
    "A388": (
        "01P18RR103",
        "TRENT 970-84",
        "A380-841",
        "engine Trent 970 (RR) -> 'RR engines'",
    ),
    "B733": (
        "1CM004",
        "CFM56-3-B1",
        "737300",
        "engine CFM56-3B1 -> 'CFM56-3B1 engines'",
    ),
    "B742": (
        "3GE077",
        "CF6-50E2",
        "74720B",
        "engine CF6-50E2 (not JT9D-7Q) -> 'All other engines'",
    ),
    "B752": (
        "5RR038",
        "RB211-535E4",
        "757RR",
        "engine RB211-535E4 (RR) -> 'RR engines'",
    ),
    "B762": (
        "2GE042",
        "2GE042",
        "767CF6",
        "engine UID manufacturer code GE -> 'GE engines'",
    ),
    "C550": (
        "1PW036",
        "1PW036",
        "CNA560U",
        "engine model not identifiable from the table -> first row",
    ),
    "C560": ("1PW037", "JT15D-5-5A-5B", "CNA560U", "engine JT15D-5 -> 'JT15D engines'"),
    "DC10": (
        "1GE002",
        "1GE002",
        "DC1010",
        "variants by model, not engine -> first row",
    ),
    "E145": (
        "01P06AL028",
        "01P06AL028",
        "EMB145",
        "variants by range, not engine -> first row",
    ),
    "F100": (
        "1RR020",
        "1RR020",
        "F10062",
        "Tay variant not identifiable from the table -> first row",
    ),
    "F27": (
        "FOI-91",
        "FOI-91",
        "DHC830",
        "engine manufacturer not identifiable from the table -> first row",
    ),
    "F28": (
        "4RR035",
        "SPEY 555",
        "F28MK2",
        "variants by mark, not engine -> first row",
    ),
    "F2TH": (
        "B602",
        "B602",
        "CL600",
        "engine manufacturer not identifiable from the table -> first row",
    ),
    "GLF2": (
        "8RR043",
        "SPEY MK511",
        "GII",
        "variants by model, not engine -> first row",
    ),
    "L101": (
        "1RR002",
        "1RR002",
        "L1011",
        "RB211 variant not identifiable from the table -> first row",
    ),
    "MD11": (
        "2GE049",
        "CF6-80C2D1F",
        "MD11GE",
        "engine CF6-80C2D1F (GE) -> 'GE engines'",
    ),
    "MD90": ("1IA002", "V2525-D5", "MD9025", "engine V2525-D5 -> 'V2525 engines'"),
}

ANP_ENGINE_TYPE = {"J": "Jet", "T": "Turboprop", "P": "Piston"}
FIXED_WING_FIRST_LETTER = {"L", "A", "S"}  # landplane, amphibian, seaplane


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def read_base(name: str, path: str | None, allow_other: bool) -> str:
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = subprocess.run(
            ["git", "show", f"{BASE_REV}:open_alaqs/database/data/{name}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8")
    if md5(text) != BASE_MD5[name] and not allow_other:
        sys.exit(
            f"{name}: md5 {md5(text)} differs from the 5.3.5 table {BASE_MD5[name]}"
        )
    return text


def read_anp_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        rows = []
        for r in csv.DictReader(f, dialect=dialect):
            rows.append({(k or "").strip(): (v or "").strip() for k, v in r.items()})
    return rows


def fmt(value: float, ndigits: int = 9) -> str:
    """Format like the existing table: repr of the rounded float."""
    v = round(value, ndigits)
    if v == 0:
        v = 0.0
    return repr(v)


def fmt_sig(value: float, sig: int = 6) -> str:
    return repr(float(f"{value:.{sig}g}"))


def to_float(s: str) -> float | None:
    return float(s) if s not in ("", None) else None


# --------------------------------------------------------------------------
# ANP v2.2
# --------------------------------------------------------------------------
class Anp:
    def __init__(self, anp_dir: Path):
        self.dir = anp_dir
        self.aircraft = {
            r["ACFT_ID"]: r for r in read_anp_csv(anp_dir / "Aircraft.csv")
        }
        self.weights = {
            (r["ACFT_ID"], r["Stage Length"]): float(r["Weight (lb)"])
            for r in read_anp_csv(anp_dir / "Default_weights.csv")
        }
        self.fixed_points = read_anp_csv(anp_dir / "Default_fixed_point_profiles.csv")

    def static_thrust(self, ac: str) -> float:
        return float(self.aircraft[ac]["Max Sea Level Static Thrust (lb)"])

    def power_parameter(self, ac: str) -> str:
        return self.aircraft[ac]["Power Parameter"]

    def fixed_point_rows(self, ac, op, prof, stage):
        pts = [
            r
            for r in self.fixed_points
            if r["ACFT_ID"] == ac
            and r["Op Type"] == op
            and r["Profile_ID"] == prof
            and r["Stage Length"] == stage
        ]
        return sorted(pts, key=lambda r: int(r["Point Number"]))

    def substitutions(self) -> list[dict]:
        import openpyxl  # only needed for the type defaults

        wb = openpyxl.load_workbook(self.dir / WORKBOOK, read_only=True, data_only=True)
        ws = wb["by ICAO code"]
        rows = list(ws.iter_rows(values_only=True))
        head = [str(h).strip() for h in rows[0]]
        out = []
        for r in rows[1:]:
            if r is None or all(c is None for c in r):
                continue
            d = dict(zip(head, r))
            d = {k: (str(v).strip() if v is not None else "") for k, v in d.items()}
            out.append(d)
        return out


# --------------------------------------------------------------------------
# profiles
# --------------------------------------------------------------------------
def _fix_weight(pid, rs, col, anp, ac, ad, stage) -> dict:
    """Check or fill weight_kgs of one profile; return the log fields."""
    # weight: departures the stage weight ('M' for stage 0), arrivals the
    # stage-1 weight (the convention of all 134 arrivals that had one).
    wstage = "M" if (ad == "D" and stage == "0") else (stage if ad == "D" else "1")
    wlb = anp.weights[(ac, wstage)]
    wkg = wlb * LB_TO_KG
    cur = rs[0][col["weight_kgs"]]
    if cur == "":
        wtxt = fmt(wkg, 6)
        for r in rs:
            r[col["weight_kgs"]] = wtxt
        return {"weight": f"filled: v2.2 stage {wstage} weight {wlb:g} lb"}
    else:
        if any(r[col["weight_kgs"]] != cur for r in rs):
            sys.exit(f"{pid}: several weights")
        if abs(float(cur) - wkg) > 0.5:
            sys.exit(
                f"{pid}: weight {cur} kg differs from v2.2 stage {wstage} ({wkg:.1f} kg)"
            )
        return {"weight": "kept (equals v2.2)"}


def _fix_power(rs, col, anp, ac) -> dict:
    """Apply the power rules of the provenance document to one profile."""
    pp = anp.power_parameter(ac)
    f0 = anp.static_thrust(ac)
    capped = 0
    neg = 0
    for r in rs:
        p = to_float(r[col["power"]])
        if p is None:
            continue
        if pp.startswith("Other"):
            r[col["power"]] = ""
            continue
        new = p
        if pp.startswith("CNT (%"):
            # stored value = (percent of static thrust) / static thrust
            new = p * f0 / 100.0
        if new > POWER_CAP:
            new = POWER_CAP
            capped += 1
        if new < 0:
            new = 0.0
            neg += 1
        if new != p:
            r[col["power"]] = (
                fmt_sig(new)
                if pp.startswith("CNT (%") and new < POWER_CAP
                else fmt(new)
            )
    if pp.startswith("Other"):
        ptxt = "emptied (RPM aircraft)"
    elif pp.startswith("CNT (%"):
        ptxt = "x static thrust / 100 (percentage stored divided by static thrust)"
    else:
        ptxt = "kept (CNT / static thrust)"
    return {
        "power_parameter": pp,
        "power": ptxt,
        "capped_points": capped,
        "negative_points": neg,
    }


def build_profiles(base_text: str, anp: Anp):
    rows = list(csv.reader(io.StringIO(base_text)))
    header, body = rows[0], rows[1:]
    col = {c: i for i, c in enumerate(header)}

    # ordered profiles
    order: list[str] = []
    prof_rows: dict[str, list[list[str]]] = {}
    for r in body:
        pid = r[col["profile_id"]]
        if pid not in prof_rows:
            order.append(pid)
            prof_rows[pid] = []
        prof_rows[pid].append(r)
    for pid, rs in prof_rows.items():
        oids = [int(r[col["oid"]]) for r in rs]
        if oids != list(range(oids[0], oids[0] + len(oids))):
            sys.exit(f"{pid}: rows not contiguous in the base table")

    log: dict[str, dict] = {}

    def note(pid, **kw):
        log.setdefault(pid, {"profile_id": pid}).update(kw)

    # 1. restore the type profiles taken by the groups (copies of the group
    #    rows, renamed), placed immediately before their group.
    restored: dict[str, list[list[str]]] = {}
    for grp, src in GROUP_SOURCE.items():
        if grp not in prof_rows:
            sys.exit(f"group {grp} missing from the base table")
        if src in prof_rows:
            continue  # source still present (JET-SMALL-A-1)
        restored[src] = []
        for r in prof_rows[grp]:
            r2 = list(r)
            r2[col["profile_id"]] = src
            restored[src].append(r2)
        note(src, origin=f"restored: rows of {grp} (renamed from {src} in ab42da5)")

    # 2. rebuild the fixed-point profiles listed in FIXED_POINT_REBUILD
    rebuilt: dict[str, list[list[str]]] = {}
    for pid, (ac, op, prof, stage) in FIXED_POINT_REBUILD.items():
        pts = anp.fixed_point_rows(ac, op, prof, stage)
        if not pts:
            sys.exit(f"{pid}: no ANP v2.2 fixed points {ac} {op} {prof} {stage}")
        old = prof_rows[pid]
        template = old[0]
        if op == "D":
            if len(old) != len(pts):
                sys.exit(
                    f"{pid}: {len(old)} rows in the table, {len(pts)} fixed points"
                )
            modes = [r[col["mode"]] for r in old]
        else:
            modes = ["AP"] * len(pts)
        new = []
        for k, p in enumerate(pts):
            r2 = list(template)
            r2[col["point"]] = str(k + 1)
            r2[col["x_m"]] = fmt(float(p["Distance (ft)"]) * FT_TO_M)
            r2[col["y_m"]] = "0"
            r2[col["z_m"]] = fmt(float(p["Altitude AFE (ft)"]) * FT_TO_M)
            r2[col["tas_metres"]] = fmt(float(p["TAS (kt)"]) * KT_TO_MS)
            # raw power, as stored for every other fixed-point row
            r2[col["power"]] = fmt(float(p["Power Setting"]) / anp.static_thrust(ac))
            r2[col["mode"]] = modes[k]
            new.append(r2)
        rebuilt[pid] = new
        note(
            pid,
            origin=f"rebuilt from ANP v2.2 fixed points {ac} {op} '{prof}' stage {stage}",
        )

    # 3. assemble in order
    final: list[tuple[str, list[list[str]]]] = []
    dropped = []
    for pid in order:
        if pid.startswith(DROPPED_PREFIXES):
            course = {r[col["course"]] for r in prof_rows[pid]}
            if course != {"ANP2.1"}:
                sys.exit(f"{pid}: expected course ANP2.1, found {course}")
            dropped.append(
                {
                    "profile_id": pid,
                    "origin": "removed (ANP 2.1)",
                    "rows": 0,
                }
            )
            continue
        if pid in GROUP_SOURCE and GROUP_SOURCE[pid] in restored:
            src = GROUP_SOURCE[pid]
            final.append((src, restored[src]))
        final.append((pid, rebuilt.get(pid, prof_rows[pid])))
    final_ids = [p for p, _ in final]
    if len(final_ids) != len(set(final_ids)):
        sys.exit("duplicate profile ids after restoration")
    by_id = dict(final)

    # 4. class replacement of groups: copy of the same-class source
    for grp, src in GROUP_REPLACEMENT.items():
        new = []
        for r in by_id[src]:
            r2 = list(r)
            r2[col["profile_id"]] = grp
            new.append(r2)
        by_id[grp] = new
        note(grp, origin=f"copy of {src} (class replacement of {GROUP_SOURCE[grp]})")
    for grp, src in GROUP_SOURCE.items():
        if grp not in GROUP_REPLACEMENT:
            note(grp, origin=f"copy of {src}")

    # 5. weights, power
    for pid in final_ids:
        rs = by_id[pid]
        if pid.startswith(UNTOUCHED_PREFIXES):
            note(
                pid,
                origin="unchanged (not ANP v2.2)",
                power="unchanged",
                weight="unchanged",
            )
            continue
        ref = GROUP_REPLACEMENT.get(pid, GROUP_SOURCE.get(pid, pid))
        m = TYPE_RE.match(ref)
        ac, ad, stage = m["ac"], m["ad"], m["stage"]
        if ac not in anp.aircraft:
            sys.exit(f"{pid}: {ac} is not an ANP v2.2 aircraft")
        note(pid, aircraft=ac)
        log[pid].setdefault("origin", "kept")

        note(pid, **_fix_weight(pid, rs, col, anp, ac, ad, stage))
        note(pid, **_fix_power(rs, col, anp, ac))

    # 6. write
    out_rows = [header]
    oid = 0
    for pid in final_ids:
        for k, r in enumerate(by_id[pid]):
            oid += 1
            r2 = list(r)
            r2[col["oid"]] = str(oid)
            r2[col["point"]] = str(k + 1)
            out_rows.append(r2)
        log[pid]["rows"] = len(by_id[pid])
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(out_rows)
    return buf.getvalue(), [log[p] for p in final_ids] + dropped, set(final_ids)


# --------------------------------------------------------------------------
# type defaults (default_aircraft.csv)
# --------------------------------------------------------------------------
def build_defaults(base_text: str, anp: Anp, profile_ids: set[str]):
    rows = list(csv.reader(io.StringIO(base_text)))
    header, body = rows[0], rows[1:]
    col = {c: i for i, c in enumerate(header)}

    subs = anp.substitutions()
    by_code: dict[str, list[dict]] = {}
    for s in subs:
        by_code.setdefault(s["ICAO_CODE"], []).append(s)

    # rule (b) candidates
    cands = []
    for ac, r in anp.aircraft.items():
        if f"{ac}-D-1" in profile_ids and f"{ac}-A-1" in profile_ids:
            cands.append(
                (
                    ac,
                    r["Engine Type"],
                    int(r["Number Of Engines"]),
                    float(r["Max Gross Takeoff Weight (lb)"]) * 0.45359237,
                )
            )

    mapping = []
    for r in body:
        icao = r[col["icao"]]
        old_d, old_a = r[col["departure_profile"]], r[col["arrival_profile"]]
        cls = r[col["class"]]
        mtow = to_float(r[col["mtow"]])
        ec = r[col["engine_count"]]
        proxy, rule, basis = None, "c", ""
        if icao in by_code:
            variants = by_code[icao]
            if len(variants) == 1:
                proxy = variants[0]["ANP_PROXY"]
                basis = "substitution workbook, single entry"
            else:
                exp_e, exp_n, choice, why = VARIANT_CHOICE[icao]
                if (r[col["engine"]], r[col["engine_name"]]) != (exp_e, exp_n):
                    sys.exit(f"{icao}: default engine changed; review VARIANT_CHOICE")
                if choice not in [v["ANP_PROXY"] for v in variants]:
                    sys.exit(f"{icao}: {choice} not among the workbook variants")
                proxy = choice
                basis = f"substitution workbook, variant: {why}"
            rule = "a"
        else:
            letter = cls[2] if len(cls) >= 3 else ""
            n = (
                int(ec)
                if ec.isdigit()
                else (int(cls[1]) if len(cls) >= 2 and cls[1].isdigit() else None)
            )
            if (
                mtow
                and cls
                and cls[0] in FIXED_WING_FIRST_LETTER
                and letter in ANP_ENGINE_TYPE
                and n is not None
            ):
                same = [
                    c for c in cands if c[1] == ANP_ENGINE_TYPE[letter] and c[2] == n
                ]
                if same:
                    best = min(same, key=lambda c: (abs(c[3] - mtow), c[0]))
                    proxy = best[0]
                    rule = "b"
                    basis = (
                        f"{ANP_ENGINE_TYPE[letter]}, {n} engine(s), nearest MTOW: "
                        f"{best[3]:.0f} kg vs {mtow:.0f} kg"
                    )
                else:
                    basis = f"no ANP v2.2 aircraft with {ANP_ENGINE_TYPE[letter]} and {n} engine(s)"
            else:
                why = []
                if not mtow:
                    why.append("no MTOW")
                if not cls:
                    why.append("no class")
                elif cls[0] not in FIXED_WING_FIRST_LETTER:
                    why.append(f"class {cls}: not fixed-wing")
                elif letter not in ANP_ENGINE_TYPE:
                    why.append(f"class {cls}: propulsion {letter!r} not in ANP")
                if n is None:
                    why.append("engine count unknown")
                basis = "; ".join(why)
        if proxy:
            new_d, new_a = f"{proxy}-D-1", f"{proxy}-A-1"
            for p in (new_d, new_a):
                if p not in profile_ids:
                    sys.exit(f"{icao}: {p} not in the profile table")
            r[col["departure_profile"]] = new_d
            r[col["arrival_profile"]] = new_a
        else:
            new_d, new_a = old_d, old_a
        mapping.append(
            {
                "icao": icao,
                "name": r[col["name"]],
                "class": cls,
                "mtow": r[col["mtow"]],
                "engine_count": ec,
                "rule": rule,
                "anp_proxy": proxy or "",
                "old_departure_profile": old_d,
                "old_arrival_profile": old_a,
                "departure_profile": new_d,
                "arrival_profile": new_a,
                "basis": basis,
            }
        )
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows([header] + body)
    return buf.getvalue(), mapping


def write_dicts(path: Path, rows: list[dict]):
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--anp-dir", required=True, type=Path, help="folder with the ANP v2.2 tables"
    )
    ap.add_argument(
        "--base-profiles",
        help="5.3.5 default_aircraft_profiles.csv (default: git c8a55cd)",
    )
    ap.add_argument(
        "--base-aircraft", help="5.3.5 default_aircraft.csv (default: git c8a55cd)"
    )
    ap.add_argument(
        "--allow-other-base",
        action="store_true",
        help="skip the md5 check of the base tables",
    )
    ap.add_argument("--out-data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--out-log-dir", type=Path, default=OUT_DIR)
    a = ap.parse_args()

    anp = Anp(a.anp_dir)
    if len(anp.aircraft) != 154:
        sys.exit(f"{len(anp.aircraft)} aircraft in Aircraft.csv; ANP v2.2 has 154")
    base_p = read_base(
        "default_aircraft_profiles.csv", a.base_profiles, a.allow_other_base
    )
    base_a = read_base("default_aircraft.csv", a.base_aircraft, a.allow_other_base)

    prof_text, log, ids = build_profiles(base_p, anp)
    acft_text, mapping = build_defaults(base_a, anp, ids)

    a.out_data_dir.mkdir(parents=True, exist_ok=True)
    a.out_log_dir.mkdir(parents=True, exist_ok=True)
    (a.out_data_dir / "default_aircraft_profiles.csv").write_text(
        prof_text, encoding="utf-8", newline=""
    )
    (a.out_data_dir / "default_aircraft.csv").write_text(
        acft_text, encoding="utf-8", newline=""
    )
    write_dicts(a.out_log_dir / "profile_build_log.csv", log)
    write_dicts(a.out_log_dir / "default_aircraft_mapping.csv", mapping)

    n_rows = prof_text.count("\n") - 1
    rules = {}
    for m in mapping:
        rules[m["rule"]] = rules.get(m["rule"], 0) + 1
    print(f"profiles: {len(ids)} ids, {n_rows} rows; md5 {md5(prof_text)}")
    print(
        f"aircraft: {len(mapping)} types, rules {dict(sorted(rules.items()))}; md5 {md5(acft_text)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
