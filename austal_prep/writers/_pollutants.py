"""
Pollutant-to-AUSTAL parameter-name mapping.

Source of truth: AUSTAL 3.3 program description (UBA / Janicke,
2024-03-22), Section 3.1 "Eingabedaten". The relevant passages:

  "Der Parametername besteht aus dem Stoffnamen, einem Minuszeichen
   und der Komponentenbezeichnung."

  [The parameter name consists of the substance name, a minus sign,
   and the component designation.]

  "Feinstaub (Durchmesser kleiner als 10 um) wird durch die beiden
   Komponenten 1 und 2 (zum Beispiel pm-1 und pm-2) repraesentiert.
   Zusaetzlich kann PM2.5 ... pm25 ... verwendet werden, hier steht
   natuerlich nur die Komponente 1 (also pm25-1) zur Verfuegung."

  [PM10 is represented by components 1 and 2 (for example pm-1
   and pm-2). Additionally, PM2.5 ... pm25 ... can be used, where
   only component 1 is available (i.e., pm25-1).]

So valid austal.txt parameter names for particulate matter are:
  pm-1, pm-2, pm-3, pm-4, pm-u   (size classes of substance pm)
  pm25-1                          (substance pm25, only component 1)

NOT pm or pm25 alone. Those are substance section headings in
austal.settings (the substance database file), not parameter names
in austal.txt (the emission input file). Earlier revisions of this
module that emitted "pm" and "pm25" without component suffix were
rejected by AUSTAL with "Unknown parameter name".

Gaseous substances (nox, co, hc, so2, nh3, etc.) have no component
suffix; they use the substance name directly as the parameter name.

Internal pollutant -> AUSTAL parameter name(s):

  pm10                   -> pm-1 (fine) + pm-2 (coarse) with split
                            via pm10_fine_fraction (default 0.9)
  pm25 / pm2.5 / pm-2.5  -> pm25-1
  hc / voc               -> hc
  (other)                -> lowercase same name

The two PM substances (pm and pm25) are independent in AUSTAL. They
share aerosol group 1 (same settling/deposition for fine particles)
but track and output separately:
  pm-y00a.dmna    = substance pm (= sum of pm-1 + pm-2)
  pm25-y00a.dmna  = substance pm25 (= pm25-1)
"""

from __future__ import annotations

from typing import List, Tuple

DEFAULT_PM10_FINE_FRACTION = 0.9


def austal_components(
    pollutant: str,
    pm10_fine_fraction: float = DEFAULT_PM10_FINE_FRACTION,
) -> List[Tuple[str, float]]:
    """Return AUSTAL emission-line components for one internal pollutant.

    Each component is (austal_parameter_name, fraction). For pm10
    two components are returned (the fine/coarse split). For pm25,
    hc, and everything else, a single component is returned.
    """
    p = pollutant.lower()
    if p == "pm10":
        fine = max(0.0, min(1.0, float(pm10_fine_fraction)))
        coarse = 1.0 - fine
        out: List[Tuple[str, float]] = []
        if fine > 0.0:
            out.append(("pm-1", fine))
        if coarse > 0.0:
            out.append(("pm-2", coarse))
        return out or [("pm-1", 1.0)]
    if p in ("pm25", "pm2.5", "pm-2.5"):
        return [("pm25-1", 1.0)]
    if p in ("hc", "voc"):
        return [("hc", 1.0)]
    return [(p, 1.0)]


def austal_substance_for_output(pollutant: str) -> str:
    """Plugin-read reverse map: AUSTAL output substance name for
    a given internal pollutant.

    AUSTAL aggregates pm-1 + pm-2 into substance "pm" in its output
    files (pm-y00a.dmna etc.). The pm25 substance outputs separately
    (pm25-y00a.dmna).
    """
    p = pollutant.lower()
    if p == "pm10":
        return "pm"
    if p in ("pm25", "pm2.5", "pm-2.5"):
        return "pm25"
    if p in ("hc", "voc"):
        return "hc"
    return p
