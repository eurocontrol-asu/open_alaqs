"""Rebuild `data/training_validation_reference.xlsx` from the pinned plugin outputs
and the CAEP14 reference implementation.

Sheets:
  README            what the workbook holds and how it was made
  Summary           grand totals, plugin beside reference, per method
  Movement          per movement, plugin beside reference, per method and pollutant
  NOx_correction    bymode with the ICCAIA ambient NOx correction, plugin beside reference
  Movement_Hourly   plugin movement emissions per period, per method
  AreaSources, ParkingSources, PointSources, RoadwaySources
                    plugin stationary-source emissions per period (bymode run)
  Helicopter        FOCA 2015 parameters of the fixture's AS50 and its two movements

Inputs: `data/plugin_output/*.csv` (made by `regenerate_plugin_csvs.py`) and the
fixture, on which the reference is run with the study meteo. No QGIS needed.

Usage, from the repository root:

    PYTHONPATH=. python3 openalaqs_standalone/validation/tools/regenerate_training_validation_xlsx.py
        [--fixture ...] [--plugin-dir ...] [--out ...]
"""

from __future__ import annotations

import argparse
import csv
import datetime
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

POLLUTANTS = [
    ("co", "CO"),
    ("co2", "CO2"),
    ("hc", "HC"),
    ("nox", "NOx"),
    ("sox", "SOx"),
    ("pm10", "PM10"),
]
PLUGIN_COLUMNS = [
    "co_kg",
    "co2_kg",
    "hc_kg",
    "nox_kg",
    "sox_kg",
    "pm10_kg",
    "p1_kg",
    "p2_kg",
    "pm10_organic_kg",
    "pm10_nonvol_kg",
    "pm10_sul_kg",
]
METHODS = [
    ("bymode", "bymode", "plugin bymode", "reference bymode"),
    (
        "bffm2_traj",
        "bffm2_traj",
        "plugin BFFM2 trajectory",
        "reference BFFM2 trajectory",
    ),
    (
        "bffm2_anchor",
        "bffm2_anchor",
        "plugin BFFM2 mode anchor",
        "reference BFFM2 mode anchor",
    ),
]
STATIONARY = ["AreaSources", "ParkingSources", "PointSources", "RoadwaySources"]


def _read_rows(path: Path) -> list:
    with open(path) as f:
        return list(csv.DictReader(f))


def _oid(name: str):
    m = re.match(r"id\s+(\d+):", name)
    return int(m.group(1)) if m else None


def _movement_totals(rows: list) -> dict:
    totals: dict = {}
    for r in rows:
        oid = _oid(r["source_name"])
        if oid is None:
            continue
        t = totals.setdefault(
            oid, {"name": r["source_name"], **{c: 0.0 for c in PLUGIN_COLUMNS}}
        )
        for c in PLUGIN_COLUMNS:
            t[c] += float(r[c])
    return totals


def _hourly(rows: list) -> dict:
    out: dict = defaultdict(lambda: {c: 0.0 for c in PLUGIN_COLUMNS})
    for r in rows:
        for c in PLUGIN_COLUMNS:
            out[r["timestamp"]][c] += float(r[c])
    return dict(sorted(out.items()))


def _reference(fixture: Path, method: str, nox_corr: bool = False) -> dict:
    import compute_caep14_reference as ref

    conn = ref._connect(str(fixture))
    ctx = {"runway": ref._get_runway(conn), "grid_bounds": ref._grid_bounds_3857(conn)}
    out = {}
    for (oid,) in conn.execute("SELECT oid FROM user_aircraft_movements ORDER BY oid"):
        r = ref.compute_for_movement(
            conn,
            oid,
            ctx,
            method=method,
            use_isa_meteo=False,
            apply_nox_corrections=nox_corr,
        )
        if r is not None:
            out[oid] = r
    conn.close()
    return out


def _autosize(ws, width=16, first=28):
    from openpyxl.utils import get_column_letter

    for i in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(i)].width = first if i == 2 else width


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", default=str(DATA / "training_v3.alaqs"))
    ap.add_argument("--plugin-dir", default=str(DATA / "plugin_output"))
    ap.add_argument("--out", default=str(DATA / "training_validation_reference.xlsx"))
    args = ap.parse_args(argv)
    from openpyxl import Workbook
    from openpyxl.styles import Font

    fixture, pdir = Path(args.fixture), Path(args.plugin_dir)
    bold = Font(bold=True)
    plugin = {m: _read_rows(pdir / f"training_movements_{m}.csv") for m, *_ in METHODS}
    plugin["bymode_nox_corr"] = _read_rows(
        pdir / "training_movements_bymode_nox_corr.csv"
    )
    sources = _read_rows(pdir / "training_sources_bymode.csv")
    reference = {m: _reference(fixture, m) for m, *_ in METHODS}
    reference["bymode_nox_corr"] = _reference(fixture, "bymode", nox_corr=True)
    totals = {k: _movement_totals(v) for k, v in plugin.items()}
    oids = sorted(totals["bymode"])

    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    today = datetime.date.today().isoformat()
    heli_oids = [
        oid
        for oid in oids
        if str(reference["bymode"][oid]["profile_id"]).startswith("FOCA")
    ]
    with sqlite3.connect(fixture) as _c:
        custom_oids = [
            oid
            for oid in oids
            if _c.execute(
                "SELECT 1 FROM user_aircraft_movements m JOIN default_aircraft_profiles p "
                "ON p.profile_id = m.profile_id WHERE m.oid = ? AND p.course = 'CUSTOM' LIMIT 1",
                (oid,),
            ).fetchone()
        ]
    heli_line = (
        f"Helicopters (movements {', '.join(str(o) for o in heli_oids)}): FOCA 2015 half-LTO, the active mode cut "
        "at the mixing height and the grid; same for every method."
        if heli_oids
        else "No helicopter movements in this study."
    )

    def _worst(sel):
        gaps = [
            abs(totals[m][o][f"{k}_kg"] - reference[m][o]["total_em_kg"][k])
            / reference[m][o]["total_em_kg"][k]
            for m, *_ in METHODS
            for o in sel
            for k, _ in POLLUTANTS
            if reference[m][o]["total_em_kg"][k]
        ]
        return max(gaps) if gaps else 0.0

    others = [o for o in oids if o not in custom_oids]
    custom_line = (
        f"Worst relative gap plugin vs reference: {_worst(others):.1e} on the "
        f"{'ANP and helicopter' if heli_oids else 'ANP'} movements, "
        f"{_worst(custom_oids):.1e} on movement {', '.join(str(o) for o in custom_oids)} (CUSTOM profile, supplied track)."
        if custom_oids
        else f"Worst relative gap plugin vs reference: {_worst(oids):.1e}."
    )
    for line in [
        "Open-ALAQS validation reference: plugin beside the CAEP14 reference implementation",
        "",
        f"Made on {today} by openalaqs_standalone/validation/tools/regenerate_training_validation_xlsx.py",
        "from the plugin outputs (regenerate_plugin_csvs.py: the plugin's",
        f"EmissionCalculatorService run headlessly on {fixture.name}, {len(oids)} movements, all source types,",
        "hourly periods, the study's grid, reference altitude = airport elevation, mixing height from the",
        "study meteo) and from compute_caep14_reference.py run on the same study with the study meteo (tbl_InvMeteo).",
        "",
        "Movement and Summary: for each method the plugin total per movement beside the reference total.",
        custom_line,
        "bymode: fuel and emission indices at the ICAO mode anchors; no ambient correction.",
        "BFFM2 trajectory: fuel from the ICAO curve at the profile's thrust share (ADS-B: supplied fuel flow),",
        "  BFFM2 indices at the segment's ambient conditions and Mach.",
        "BFFM2 mode anchor: anchor fuel flow, BFFM2 indices at ambient conditions.",
        "NOx_correction: bymode with the ICCAIA ambient NOx correction on take-off and climb-out segments.",
        heli_line,
        "Movement_Hourly and the four stationary-source sheets: the plugin's per-period emissions, for an",
        "  installation check of a QGIS run of the training study (documents/VALIDATION_GUIDE.md).",
        "",
        "Values in kg per movement (Movement, Summary) or per hourly period (the other sheets).",
        "Procedure and tolerances: openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md.",
    ]:
        ws.append([line])
    ws["A1"].font = bold
    ws.column_dimensions["A"].width = 110

    # Summary
    ws = wb.create_sheet("Summary")
    ws.append(
        [f"Grand totals over the {len(oids)} movements (kg): plugin beside reference"]
    )
    ws["A1"].font = bold
    header = ["Pollutant"]
    for _, _, pl, rl in METHODS:
        header += [pl, rl]
    header += ["plugin bymode + NOx correction", "reference bymode + NOx correction"]
    ws.append(header)
    for c in ws[2]:
        c.font = bold
    for key, label in POLLUTANTS:
        row = [label]
        for m, *_ in METHODS + [("bymode_nox_corr",)]:
            row.append(sum(t[f"{key}_kg"] for t in totals[m].values()))
            row.append(sum(r["total_em_kg"][key] for r in reference[m].values()))
        ws.append(row)
    _autosize(ws, 30, 30)

    # Movement
    ws = wb.create_sheet("Movement")
    ws.append(["Per movement (kg): plugin beside reference, per method"])
    ws["A1"].font = bold
    h1, h2 = ["Mov ID", "Source name"], ["", ""]
    for key, label in POLLUTANTS:
        for _, _, pl, rl in METHODS:
            h1 += [f"{label} (kg)", f"{label} (kg)"]
            h2 += [pl, rl]
    ws.append(h1)
    ws.append(h2)
    for c in ws[2]:
        c.font = bold
    for oid in oids:
        row = [oid, totals["bymode"][oid]["name"]]
        for key, _ in POLLUTANTS:
            for m, *_ in METHODS:
                row.append(totals[m][oid][f"{key}_kg"])
                row.append(reference[m][oid]["total_em_kg"][key])
        ws.append(row)
    tot = ["TOTAL", ""]
    for key, _ in POLLUTANTS:
        for m, *_ in METHODS:
            tot.append(sum(t[f"{key}_kg"] for t in totals[m].values()))
            tot.append(sum(r["total_em_kg"][key] for r in reference[m].values()))
    ws.append(tot)
    ws[ws.max_row][0].font = bold
    _autosize(ws, 18, 44)

    # NOx correction
    ws = wb.create_sheet("NOx_correction")
    ws.append(
        [
            "bymode with the ICCAIA ambient NOx correction (kg): plugin beside reference; other pollutants unchanged"
        ]
    )
    ws["A1"].font = bold
    ws.append(
        [
            "Mov ID",
            "Source name",
            "NOx plugin",
            "NOx reference",
            "NOx plugin, no correction",
            "factor plugin",
        ]
    )
    for c in ws[2]:
        c.font = bold
    for oid in oids:
        base = totals["bymode"][oid]["nox_kg"]
        corr = totals["bymode_nox_corr"][oid]["nox_kg"]
        ws.append(
            [
                oid,
                totals["bymode"][oid]["name"],
                corr,
                reference["bymode_nox_corr"][oid]["total_em_kg"]["nox"],
                base,
                corr / base if base else None,
            ]
        )
    _autosize(ws, 22, 44)

    # Hourly movements
    ws = wb.create_sheet("Movement_Hourly")
    ws.append(["Plugin movement emissions per hourly period (kg), three methods"])
    ws["A1"].font = bold
    h1, h2 = ["Timestamp"], [""]
    for key, label in POLLUTANTS:
        for _, _, pl, _ in METHODS:
            h1.append(f"{label} (kg)")
            h2.append(pl)
    ws.append(h1)
    ws.append(h2)
    for c in ws[2]:
        c.font = bold
    hourly = {m: _hourly(plugin[m]) for m, *_ in METHODS}
    for ts in sorted(set().union(*[set(h) for h in hourly.values()])):
        row = [ts]
        for key, _ in POLLUTANTS:
            for m, *_ in METHODS:
                row.append(hourly[m].get(ts, {}).get(f"{key}_kg", 0.0))
        ws.append(row)
    _autosize(ws, 18, 22)

    # Stationary sources
    for stype in STATIONARY:
        ws = wb.create_sheet(stype)
        ws.append(
            [
                f"{stype}: plugin emissions per hourly period (kg), bymode run, all sources of the type summed"
            ]
        )
        ws["A1"].font = bold
        ws.append(
            ["Timestamp"]
            + [f"{label} (kg)" for _, label in POLLUTANTS]
            + [
                "P1 (kg)",
                "P2 (kg)",
                "PM10 organic (kg)",
                "PM10 non-vol (kg)",
                "PM10 sulphate (kg)",
            ]
        )
        for c in ws[2]:
            c.font = bold
        rows = [r for r in sources if r["source_type"] == stype]
        for ts, kg in _hourly(rows).items():
            ws.append([ts] + [kg[c] for c in PLUGIN_COLUMNS])
        _autosize(ws, 18, 18)

    # Helicopter
    ws = wb.create_sheet("Helicopter")

    conn = sqlite3.connect(fixture)
    heli = conn.execute(
        "SELECT h.icao, h.mtow_kg, h.engine_count, h.engine_name, h.max_shp_per_engine, e.engine_type "
        "FROM default_helicopter h JOIN default_helicopter_engines e ON e.engine_name = h.engine_name "
        "WHERE h.icao IN (SELECT DISTINCT aircraft FROM user_aircraft_movements WHERE profile_id IS NULL OR profile_id = '')"
    ).fetchall()
    conn.close()
    from open_alaqs.core.tools.foca_heli import PROFILES, derive_category

    ws.append(
        [
            "FOCA 2015 helicopter half-LTO (Appendix A): fixture helicopters and their movements"
        ]
    )
    ws["A1"].font = bold
    for icao, mtow, n_eng, engine, shp, etype in heli:
        cat = derive_category(etype, int(n_eng), float(mtow))
        prof = PROFILES[cat]
        ws.append([])
        ws.append(["ICAO type", icao, "engine", engine, "engine type", etype])
        ws.append(["MTOW (kg)", mtow, "engines", n_eng, "max SHP per engine", shp])
        ws.append(["FOCA category", cat.value if hasattr(cat, "value") else str(cat)])
        ws.append(["Mode", "power fraction", "time (min)"])
        ws.append(["GI", prof.gi_power, prof.gi_time_min])
        ws.append(["TO", prof.to_power, prof.to_time_min])
        ws.append(["AP", prof.ap_power, prof.ap_time_min])
    ws.append([])
    ws.append(
        [
            "Mov ID",
            "Source name",
            "GI fuel (kg)",
            "active mode",
            "active fuel kept (kg)",
            "NOx plugin (kg)",
            "NOx reference (kg)",
            "CO2 plugin (kg)",
            "CO2 reference (kg)",
        ]
    )
    for c in ws[ws.max_row]:
        c.font = bold
    for oid in oids:
        r = reference["bymode"][oid]
        if not str(r["profile_id"]).startswith("FOCA"):
            continue
        fm = r["traj_fuel_by_mode_kg"]
        active = [k for k in fm if k != "GI"][0]
        ws.append(
            [
                oid,
                totals["bymode"][oid]["name"],
                fm["GI"],
                active,
                fm[active],
                totals["bymode"][oid]["nox_kg"],
                r["total_em_kg"]["nox"],
                totals["bymode"][oid]["co2_kg"],
                r["total_em_kg"]["co2"],
            ]
        )
    ws.append(
        [
            "The active mode (TO or AP) keeps the share of its time below the period's mixing height and inside the grid "
            "on the FOCA flight path; ground idle is not cut."
        ]
    )
    _autosize(ws, 20, 44)

    wb.save(args.out)
    print(f"{args.out}: {len(oids)} movements, sheets {wb.sheetnames}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
