"""
Dataclasses for AUSTAL prep configuration and reporting.

These are pure data containers. No I/O, no validation that requires
external resources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional


@dataclass
class GridSpec:
    """Calculation grid definition.

    AUSTAL expects square horizontal cells. dd is the cell width (m).
    sk is the list of vertical level top heights in m (length k+1 where
    k is the number of vertical layers).

    x0 and y0 are the south-west corner of the calculation grid in
    metres relative to the user's reference point. nx and ny are the
    number of horizontal cells.

    QGIS plugin compatibility:
    The QGIS Open-ALAQS plugin's AUSTAL writer
    (AUSTALOutputModule.py) and concentration reader
    (ConcentrationsQGISVectorLayerOutputModule.py) assume the
    austal.txt calc-grid SW corner is offset from the reference
    point by an additional DEFAULT_CONCENTRATION_GRID_FACTOR = 2
    cells beyond the centered SW corner. For a 75x75 grid at 250 m
    that means x0 = y0 = -((nx/2 + 2) * dd) = -9875. If the AUSTAL
    output of this run is to be visualized by the legacy QGIS plugin
    without a one-row spatial offset in the GPKG, pass x0/y0 with
    that halo applied, or build the GridSpec with
    centered_on_reference() below.
    """

    dd: float  # mesh width (m), e.g. 250
    nx: int  # x-cells, e.g. 75
    ny: int  # y-cells, e.g. 75
    x0: float  # south-west x corner relative to ref point (m)
    y0: float  # south-west y corner relative to ref point (m)
    sk: List[float]  # vertical layer top heights (m)
    reference_x: float = 0.0  # absolute UTM x of (x0, y0) reference point
    reference_y: float = 0.0  # absolute UTM y of (x0, y0) reference point
    utm_epsg: Optional[int] = None  # UTM EPSG of reference_x/y, e.g. 32631

    @property
    def n_layers(self) -> int:
        """Number of vertical cells (one less than the number of level
        boundaries in sk)."""
        return len(self.sk) - 1

    @property
    def x_max(self) -> float:
        return self.x0 + self.dd * self.nx

    @property
    def y_max(self) -> float:
        return self.y0 + self.dd * self.ny

    @classmethod
    def centered_on_reference(
        cls,
        dd: float,
        nx: int,
        ny: int,
        sk: List[float],
        halo_cells: int = 2,
        reference_x: float = 0.0,
        reference_y: float = 0.0,
        utm_epsg: Optional[int] = None,
    ) -> "GridSpec":
        """Construct a GridSpec whose calc grid is centered on the
        reference point with an additional halo_cells offset on x0/y0.
        Matches the QGIS Open-ALAQS writer convention
        (DEFAULT_CONCENTRATION_GRID_FACTOR = 2). With halo_cells=2,
        nx=75, dd=250 the result is x0 = y0 = -9875 m. Pass
        halo_cells=0 to keep the previous unshifted (centered)
        behavior.
        """
        x0 = -((nx / 2.0) + halo_cells) * dd
        y0 = -((ny / 2.0) + halo_cells) * dd
        return cls(
            dd=dd,
            nx=nx,
            ny=ny,
            x0=x0,
            y0=y0,
            sk=sk,
            reference_x=reference_x,
            reference_y=reference_y,
            utm_epsg=utm_epsg,
        )


@dataclass
class AustalStudyConfig:
    """Top-level study configuration. Maps directly to the austal.txt
    fields plus a few internal toggles."""

    title: str
    grid: GridSpec
    qs: int = 3  # quality level (0..4)
    z0: float = 0.3  # roughness length (m)
    d0: float = 1.2  # displacement height (m)
    ha: float = 11.2  # anemometer height (m)
    os_options: str = "NOSTANDARD;SCINOTAT;Kmax=1"
    # AUSTAL represents PM10 as two size-class components: pm-1
    # (< 2.5 um, "fine") and pm-2 (2.5-10 um, "coarse"). This field
    # sets the mass fraction assigned to pm-1; the rest goes to pm-2.
    # Default 0.9 mirrors the plugin's ui_run_austal default. PM2.5
    # is emitted as the separate substance "pm25-1" and is unaffected.
    pm10_fine_fraction: float = 0.9
    mixing_height_included: bool = True  # write hm column in series.dmna
    # "hybrid" (default): per-hour spatial dmnas for aircraft sub-sources
    # (true temporal-spatial variation, one per pollutant) plus a single
    # time-invariant dmna per stationary source. Matches the plugin's
    # per-period source approach for aircraft while keeping stationary
    # output compact. Works with source_aggregation = "by_type_per_pollutant"
    # (no extra expansion needed; sub-sources already exist) or "by_type"
    # (expanded in runner.py).
    # "time_indexed": all sources get a single time-invariant dmna. Faster
    # to write but smears aircraft over the study window.
    # "legacy": all sources get one dmna per hour.
    grid_writer_mode: Literal["legacy", "time_indexed", "hybrid"] = "hybrid"
    # Source height to write in the hq line. The reference always
    # reports 0 for this; the actual release height is implicit in the
    # spatial distribution (which spans the full source vertical
    # extent). Override only if your AUSTAL configuration needs it.
    source_height: float = 0.0
    # AUSTAL rejects sources whose declared (xq, yq) is coincident with
    # (x0, y0) ("Source N outside of the computational area!"). The
    # reference layout offsets sources by 2 cells (= 2*dd metres). Set
    # to 0 only if you know AUSTAL will accept it.
    source_offset_cells: int = 2
    # AUSTAL has an internal cap on the number of receptor points. The
    # exact value isn't documented but is empirically around a few
    # hundred. Receptors beyond this cap are dropped, keeping those
    # closest to the geometric centre of all source emissions. Set to
    # None to disable capping.
    max_receptors: Optional[int] = 20
    # Aggregation strategy applied before writing AUSTAL inputs.
    #
    # Default is "by_type_per_pollutant" because:
    #   1. AUSTAL's source model has time-invariant spatial geometry
    #      per source. One source = one fixed spatial pattern.
    #   2. Within a single source type (e.g. all road segments,
    #      all parking lots), constituents typically share a
    #      temporal profile to a high degree (median correlation
    #      0.99+ in real data). Combining them is a small, stable
    #      approximation.
    #   3. ACROSS source types (road vs parking vs stationary),
    #      profiles diverge significantly (correlation 0.6 in real
    #      data). Keeping types separate preserves the temporal
    #      distinction that matters most.
    #   4. Per-type aggregation is study-independent: the source-type
    #      vocabulary is fixed by the data model, not by a particular
    #      study's geometry.
    #   5. Per-pollutant splitting (the "by_type_per_pollutant" half)
    #      preserves the correct spatial pattern for EACH pollutant
    #      separately. Without it, a constituent that emits zero of
    #      pollutant X but non-zero of pollutant Y still contributes
    #      its location to X's spatial pattern (because the combined
    #      spatial weight is based on total emission across all
    #      pollutants). In the test campaign this caused ~14 % of stationary
    #      NOx mass to be placed at the position of a stack that
    #      emits only HC, producing a spurious near-ground NOx peak
    #      ~700 m from the actual NOx emitters.
    #
    # Available strategies:
    #   "none"    — pass through, one AUSTAL source per input source.
    #               Use when you want maximum fidelity and accept the
    #               larger files. Set source_aggregation=none when the
    #               within-type profile heterogeneity is high enough
    #               that emission-weighted averaging would distort
    #               results.
    #   "by_type" — group by the prefix before ':' in source_id. For
    #               OpenALAQS this means one AUSTAL source for
    #               'road:*', one for 'parking:*', etc. Legacy
    #               behaviour with the per-pollutant bias described
    #               above; kept for backward compatibility.
    #   "by_type_per_pollutant" — group by type, then split each
    #               group into one sub-source per pollutant. Each
    #               sub-source's spatial pattern is computed from
    #               only the constituents that emit that pollutant.
    #               Correct, default.
    #
    # NOTE: aggregation only applies to source types with stationary
    # geometry (geometry fixed across the study period). Source types
    # with non-stationary geometry (e.g. aircraft LTO movements where
    # each flight has a different trajectory) require a different
    # encoding mechanism — typically per-hour grid files. That path
    # is not yet implemented; when it lands, those source types will
    # bypass this aggregation step entirely.
    source_aggregation: Literal["none", "by_type", "by_type_per_pollutant"] = (
        "by_type_per_pollutant"
    )


@dataclass
class AustalPrepReport:
    """Returned by run_austal_prep. Lets callers verify rather than
    guess what was produced."""

    n_sources: int
    n_hours: int
    n_pollutants: int
    n_grid_files_written: int
    output_dir: Path
    missing_meteo_hours: List[datetime] = field(default_factory=list)
    sources_skipped_no_geometry: List[str] = field(default_factory=list)
    sources_skipped_no_emissions: List[str] = field(default_factory=list)
    pollutants_used: List[str] = field(default_factory=list)
    n_receptors_total: int = 0  # how many were in the input CSV
    n_receptors_kept: int = 0  # how many made it into austal.txt
    n_sources_before_aggregation: int = 0  # input source count
    aggregation_strategy: str = "none"  # what was applied
