"""Emission compute for engine-test area sources.

Introduced in Phase 3 alongside its standalone twin
``openalaqs_standalone/compute_engine_test.py``. Both consume Phase 1b
schema (``is_test_site`` on ``shapes_area_sources`` + rows in
``engine_test_events``) and Phase 2 interfaces (``EngineTestEvent``,
``EngineTestEventsStore``, ``AreaSources.getEngineTestEvents``).

Design (per phase 0 memo):
  * D4: window-fraction hour-split. An event window ``[e_start, e_end]``
    contributing to period ``[p_start, p_end]`` yields
    ``fraction = overlap_s / (e_end - e_start).total_seconds()`` of the
    event's total mode times. Same fraction applies to every mode
    because run-up mode time is treated as uniform across the window.
  * D2: per-event ``thrust_mode`` override. ``'snap'`` uses the ICAO
    per-mode EI unchanged; ``'meem'`` runs the segment through
    ``getEmissionIndexByModeWithMEEM`` with LTO defaults (sea-level
    ambient, Mach 0), which is physically correct for a stationary
    engine at airport elevation.
  * D5: one aircraft/engine type per event. Mixed-type run-ups are
    represented as two rows sharing ``source_id`` and window; both are
    iterated as independent events here.
  * D10: interval-overlap semantics used by
    ``EngineTestEventsStore.getEventsInPeriod`` (strict ``<`` on both
    boundaries). This module does NOT re-check overlap; it trusts
    the store's filter.

Test sites are NOT processed by ``AreaSourceWithTimeProfileModule``
(which skips ``isTestSite()`` sources) so there is no double-count.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AreaSources import AreaSourcesStore
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.EngineTestEvents import EngineTestEventsStore
from open_alaqs.core.interfaces.Movement import defaultEmissions
from open_alaqs.core.interfaces.SourceModule import SourceModule

logger = get_logger(__name__)


# MEEM defaults for run-up events. Real run-ups happen at airport
# elevation (sea-level here is a proxy; airport-specific altitude could
# be surfaced in Phase 4) and zero forward speed. LTO branch of MEEM
# applies below 914 m so these defaults route correctly.
_MEEM_P_AMB_PA = 101325.0
_MEEM_MACH = 0.0


# Emission.add() writes into ``*_g`` keys (grams). Use the same
# defaultEmissions dict as MovementSourceModule so the keys are pre-
# initialised. AreaSourceModule's ``_ZERO_EMISSION_VALUES`` (with
# ``*_kg`` keys) is only compatible with ``Emission.addGeneric``.


class EngineTestSourceModule(SourceModule):
    """Emission compute for engine-test area sources.

    Stationary geometry: each area source is a fixed polygon so the
    emissions inherit the source's geometry unchanged. Marked for
    downstream loop-fusion by ``time_invariant_geometry``.
    """

    # Set to True so downstream code can loop-fuse identical geometries
    # across periods (same optimisation ``AreaSourceWithTimeProfileModule``
    # gets).
    time_invariant_geometry: bool = True

    @staticmethod
    def getModuleName():
        return "EngineTestSource"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        SourceModule.__init__(self, values_dict)

        # Primary store: area sources. This is what we iterate. Events
        # and engine/aircraft stores are auxiliaries loaded on demand.
        if self.getDatabasePath() is not None:
            self.setStore(AreaSourcesStore(self.getDatabasePath()))

        # Auxiliary stores. Lazy-initialised in beginJob so tests can
        # swap them in via setter methods without triggering DB access.
        self._events_store: Optional[EngineTestEventsStore] = None
        self._aircraft_store = None
        self._engine_store = None
        self._ambient_store = None  # AmbientConditionStore; only used for BFFM2

        # Diagnostic: set to True the first time an event asks for BFFM2
        # and the ambient store is empty. Prevents log flooding when a
        # study uses BFFM2 without a populated tbl_InvMeteo.
        self._bffm2_isa_fallback_logged: bool = False

        # Default thrust-mode override; per-event ``thrust_mode`` still
        # takes precedence. Kept for potential future study-level
        # override; not currently exposed.
        self._default_thrust_mode = values_dict.get("default_thrust_mode", "snap")

    # ── Store accessors ────────────────────────────────────────────────

    def getEventsStore(self) -> Optional[EngineTestEventsStore]:
        return self._events_store

    def setEventsStore(self, store) -> None:
        self._events_store = store

    def getAircraftStore(self):
        return self._aircraft_store

    def setAircraftStore(self, store) -> None:
        self._aircraft_store = store

    def getEngineStore(self):
        return self._engine_store

    def setEngineStore(self, store) -> None:
        self._engine_store = store

    def getAmbientStore(self):
        return self._ambient_store

    def setAmbientStore(self, store) -> None:
        self._ambient_store = store

    # ── Lifecycle ──────────────────────────────────────────────────────

    def loadSources(self):
        """Populate ``_sources`` from ``AreaSourcesStore``, keeping only
        area sources flagged as engine-test sites (``is_test_site='1'``).

        The store is shared with ``AreaSourceModule``; filtering here
        means the Results Analysis source-name dropdown for
        "EngineTestSource" excludes regular area sources. Each area
        source ends up in exactly one module's dropdown based on its
        ``is_test_site`` flag.
        """
        if self.getStore() is None:
            return
        for source_name, source in self.getStore().getObjects().items():
            if not source.isTestSite():
                continue
            self.setSource(source_name, source)

    def beginJob(self):
        SourceModule.beginJob(self)

        db_path = self.getDatabasePath()
        if db_path is None:
            return

        # Load the auxiliary stores if the caller hasn't already injected
        # them (setters take precedence, so tests can supply fakes).
        if self._events_store is None:
            self._events_store = EngineTestEventsStore(db_path)

        if self._aircraft_store is None:
            # Import lazily to avoid a circular import at module-load time
            # (AircraftStore pulls in EngineStore which pulls in a lot).
            from open_alaqs.core.interfaces.Aircraft import AircraftStore

            self._aircraft_store = AircraftStore(db_path)

        if self._engine_store is None:
            from open_alaqs.core.interfaces.EngineStore import EngineStore

            self._engine_store = EngineStore(db_path)

        if self._ambient_store is None:
            # AmbientConditionStore is a Singleton; if EmissionCalculation
            # has already loaded it for the same db_path, this call
            # returns the same instance rather than re-reading tbl_InvMeteo.
            from open_alaqs.core.interfaces.AmbientCondition import (
                AmbientConditionStore,
            )

            self._ambient_store = AmbientConditionStore(db_path)

    def endJob(self):
        # Nothing to release; stores are Singletons owned by the runtime.
        return None

    # ── Core compute ───────────────────────────────────────────────────

    def process(
        self,
        start_dt: datetime,
        end_dt: datetime,
        source_names: Optional[list] = None,
        **kwargs,
    ):
        """Emit ``(period_start, source, [emission])`` triples for every
        test-site area source active in ``[start_dt, end_dt]``.

        Iteration:
          1. For each area source that is flagged as a test site AND in
             study (``isInStudy() and isTestSite()``), fetch overlapping
             events via ``EventsStore.getEventsInPeriod``.
          2. Filter events to those actually attached to this source
             (``event.getSourceId() == source_id``) and in-study.
          3. For each event, compute its period-fraction and emit one
             ``Emission`` object per source-period pair (contributions
             from multiple events on the same source in the same period
             are summed).

        Non-fatal skip conditions (logged as warnings, no emission
        produced for that event, other events on the same source still
        computed):
          * Missing / unresolvable aircraft type.
          * Missing / unresolvable engine.
          * Zero engine count (no engine to run).
          * Non-positive event duration (missing datetimes, e.g. a
            partially-imported row).
          * Every-mode EI resolution failure (engine exists but has no
            EI table for any LTO mode).
        """
        if source_names is None:
            source_names = []

        if self._events_store is None:
            # beginJob was not called or the caller didn't supply the
            # events store. Emit nothing rather than raise; matches the
            # behaviour of every other source module when its store is
            # empty.
            return []

        # Fetch overlapping events once for the period, then re-filter
        # per source. Cheaper than N per-source calls when many sources
        # are test sites; equivalent when few.
        period_events = self._events_store.getEventsInPeriod(start_dt, end_dt)
        events_by_source: dict = {}
        for ev in period_events:
            events_by_source.setdefault(ev.getSourceId(), []).append(ev)

        result_ = []
        for source_id, source in self.getSources().items():
            if (
                source_names
                and ("all" not in source_names)
                and (source_id not in source_names)
            ):
                continue
            if not source.isInStudy():
                continue
            # ONLY test sites go through this module; ordinary area
            # sources are handled by AreaSourceWithTimeProfileModule.
            if not source.isTestSite():
                continue

            source_events = events_by_source.get(source_id, [])
            if not source_events:
                continue

            emission = Emission(initValues=None, defaultValues=defaultEmissions)
            any_contribution = False

            for event in source_events:
                if not event.isInStudy():
                    continue

                contributed = self._add_event_to_emission(
                    event=event,
                    emission=emission,
                    period_start=start_dt,
                    period_end=end_dt,
                )
                if contributed:
                    any_contribution = True

            if any_contribution:
                emission.setGeometryText(source.getGeometryText())
                result_.append((start_dt, source, [emission]))

        return result_

    # ── Per-event contribution ─────────────────────────────────────────

    def _add_event_to_emission(
        self,
        event,
        emission: Emission,
        period_start: datetime,
        period_end: datetime,
    ) -> bool:
        """Add one event's contribution to ``emission``. Returns True if
        any pollutant mass was added, False on any of the skip conditions
        listed on ``process``.

        Isolated as a method for two reasons: (a) tests can call it
        directly against a fake event without needing a full study
        setup, and (b) refactoring risk is contained if the per-event
        math changes.
        """
        event_id = event.getEventId()

        # Fraction of the event window that falls inside this period.
        fraction = _period_window_fraction(
            event.getStartDateTime(),
            event.getEndDateTime(),
            period_start,
            period_end,
        )
        if fraction <= 0.0:
            # Store already filtered on overlap so this should be
            # unreachable, but defensive against consistency drift.
            return False

        aircraft = event.getAircraft(self._aircraft_store)
        if aircraft is None:
            logger.warning(
                "EngineTest event %s: aircraft type %r not resolvable; "
                "skipping event contribution.",
                event_id,
                event.getAircraftType(),
            )
            return False

        engine = event.getEngine(self._engine_store, aircraft)
        if engine is None:
            logger.warning(
                "EngineTest event %s: engine %r not resolvable (aircraft "
                "%r has no default engine either); skipping.",
                event_id,
                event.getEngineUid(),
                event.getAircraftType(),
            )
            return False

        engine_count = event.resolveEngineCount(aircraft)
        if engine_count is None or engine_count <= 0:
            logger.warning(
                "EngineTest event %s: engine count unresolved / non-positive "
                "(%r); skipping.",
                event_id,
                engine_count,
            )
            return False

        mode_times = event.getModeTimes()  # {"TX": s, "AP": s, "CL": s, "TO": s}
        thrust_mode = event.getThrustMode() or self._default_thrust_mode

        # BFFM2 needs ambient conditions at the event midpoint. Lazy: only
        # look up when the thrust mode requires it, so snap/meem events
        # don't pay the cost.
        ambient_conditions = None
        if thrust_mode == "bffm2":
            ambient_conditions = self._resolve_event_ambient(event)
            # None means the ambient store is empty AND diagnostic already
            # emitted; fall back to snap-equivalent behaviour by returning
            # None here so _resolve_ei drops to base EI (which is what an
            # ISA-fallback would produce anyway when the store is empty —
            # AmbientCondition() empty getters yield None).
            # The BFFM2 wrapper (getEmissionIndexByModeWithBFFM2) already
            # handles the "empty AmbientCondition → fall back to base" path
            # via the existing bffm2.py ISA-defaults branch. So passing
            # ambient_conditions even when the store was empty is safe;
            # the diagnostic gets logged once and BFFM2 downcasts to ISA
            # internally.

        any_mode_computed = False
        for mode, t_mode_s in mode_times.items():
            if t_mode_s <= 0:
                continue

            ei = _resolve_ei(engine, mode, thrust_mode, ambient_conditions)
            if ei is None:
                logger.warning(
                    "EngineTest event %s: no EI for engine %r mode %r; "
                    "skipping this mode.",
                    event_id,
                    event.getEngineUid() or "<aircraft default>",
                    mode,
                )
                continue

            # t_effective seconds already multiplied by engine count and
            # the period-fraction; matches Emission.add's contract that
            # says "the time in a certain mode, multiplied by number of
            # engines".
            t_effective = t_mode_s * engine_count * fraction
            emission.add(ei, t_effective)
            any_mode_computed = True

        return any_mode_computed

    def _resolve_event_ambient(self, event):
        """Look up ambient conditions at the event's midpoint via the
        AmbientConditionStore.

        Returns:
          * The nearest ``AmbientCondition`` from ``tbl_InvMeteo``, OR
          * An empty ``AmbientCondition()`` (whose getTemperature /
            getPressure / getRelativeHumidity return None) if the store
            is empty. A diagnostic is emitted once per module lifetime
            in this case so the user learns their study is missing
            meteo but log volume stays sane.

        The empty case is handled downstream by ``bffm2.calculate_emission_index``
        (existing behaviour): it silently substitutes ISA defaults with
        its own logger.warning. So the ISA-fallback path is well-defined
        and the diagnostic here explains WHY BFFM2 got ISA defaults for
        callers who ask.
        """
        if self._ambient_store is None:
            # Ambient store never loaded (e.g. beginJob not called).
            # Return empty AmbientCondition; BFFM2 will fall back to ISA
            # inside bffm2.py.
            from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition

            return AmbientCondition()

        start_dt = event.getStartDateTime()
        end_dt = event.getEndDateTime()
        if start_dt is None or end_dt is None:
            # Degenerate event; the caller (process) already filtered
            # these but be safe.
            from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition

            return AmbientCondition()

        midpoint_dt = start_dt + (end_dt - start_dt) / 2
        midpoint_ts = midpoint_dt.timestamp()

        ambient = self._ambient_store.getNearestByTime(midpoint_ts)
        if ambient.getTemperature() is None and not self._bffm2_isa_fallback_logged:
            logger.warning(
                "EngineTestSource: tbl_InvMeteo has no ambient data; "
                "BFFM2 events will fall back to ISA defaults "
                "(T=288.15 K, P=101325 Pa, RH=0.6). Populate tbl_InvMeteo "
                "to get real ambient corrections. This message is shown "
                "once per run."
            )
            self._bffm2_isa_fallback_logged = True
        return ambient


# ── Free functions (unit-testable without instantiating the module) ────


def _period_window_fraction(
    event_start: Optional[datetime],
    event_end: Optional[datetime],
    period_start: datetime,
    period_end: datetime,
) -> float:
    """Fraction of the event window ``[event_start, event_end]`` that
    falls inside period ``[period_start, period_end]``.

    Returns 0.0 for degenerate events (missing datetimes, non-positive
    duration) or non-overlapping windows. Returns a value in (0, 1] on
    proper overlap.
    """
    if event_start is None or event_end is None:
        return 0.0
    total_s = (event_end - event_start).total_seconds()
    if total_s <= 0.0:
        return 0.0
    overlap_start = max(event_start, period_start)
    overlap_end = min(event_end, period_end)
    overlap_s = (overlap_end - overlap_start).total_seconds()
    if overlap_s <= 0.0:
        return 0.0
    return overlap_s / total_s


def _resolve_ei(engine, mode: str, thrust_mode: str, ambient_conditions=None):
    """Return the ``EmissionIndex`` for ``mode`` on ``engine`` under the
    requested ``thrust_mode``.

    ``'snap'`` → plain ICAO ``getEmissionIndexByMode``.
    ``'meem'`` → MEEM-corrected via ``getEmissionIndexByModeWithMEEM``
        at sea-level ambient, Mach 0 (correct for stationary run-ups at
        airport elevation).
    ``'bffm2'`` → BFFM2-corrected gas-phase EIs (NOx, CO, HC) via
        ``getEmissionIndexByModeWithBFFM2`` at the caller-supplied
        ``ambient_conditions``, Mach 0. PM10 (and PM sub-classes), SOx,
        and CO2 pass through unchanged from the base mode EI. Per
        Design A: BFFM2 gas + EEDB PM composed together.

    Note on MEEM for engine-test events: MEEM V1 only corrects nvPM EIs,
    and its LTO branch (which applies here — engine test runs are at
    ground level, Mach 0) is a log-log / linear interpolation across
    the four ICAO EEDB anchor points. Since engine-test modes always
    correspond to those anchor thrust settings (TX=0.07, AP=0.30,
    CL=0.85, TO=1.00 F00), MEEM V1 returns the anchor's own nvPM value
    unchanged. Gas-phase EIs (NOx, CO, HC, SOx) are untouched by MEEM V1
    in any case. So for engine-test events, ``'meem'`` and ``'snap'``
    produce numerically identical results. The MEEM path is kept for
    consistency with the wider ALAQS emission methodology and to leave
    room for future work (e.g. non-anchor thrust events with an
    explicit ``power_setting`` column).

    Note on BFFM2: unlike MEEM, BFFM2 IS numerically different from snap
    whenever the ambient is not ISA. Users choosing ``'bffm2'`` need a
    populated ``tbl_InvMeteo``; the module emits a diagnostic if the
    ambient store is empty and the underlying ``bffm2.py`` layer
    substitutes ISA defaults with its own warning.

    Falls back to ``'snap'`` if MEEM or BFFM2 is unavailable on the
    engine (older EEDB entries without enough data for the correction).
    Returns None if even the snap lookup fails.

    Implementation note: the mode/MEEM/BFFM2 methods live on the
    ``EngineEmissionIndex`` store returned by ``engine.getEmissionIndex()``,
    NOT on the ``Engine`` object itself. Calling them directly on the
    Engine raises ``AttributeError`` (which the try/except below would
    silently swallow, causing every mode to return None and every event
    to produce zero emissions — the bug this comment now guards against).
    """
    ei_store = engine.getEmissionIndex() if engine is not None else None
    if ei_store is None:
        return None

    try:
        if thrust_mode == "meem":
            try:
                ei = ei_store.getEmissionIndexByModeWithMEEM(
                    mode,
                    p_amb_Pa=_MEEM_P_AMB_PA,
                    mach=_MEEM_MACH,
                )
            except AttributeError:
                # Old engine EI store lacking the MEEM wrapper method.
                # Fall through to snap.
                ei = None
            if ei is not None:
                return ei
            # Fall through to snap on MEEM unavailability.
        elif thrust_mode == "bffm2":
            if ambient_conditions is None:
                # Caller forgot to supply ambient. Fall back to snap.
                return ei_store.getEmissionIndexByMode(mode)
            try:
                ei = ei_store.getEmissionIndexByModeWithBFFM2(
                    mode,
                    ambient_conditions=ambient_conditions,
                    mach=0.0,
                )
            except AttributeError:
                # Old engine EI store lacking the BFFM2 wrapper method.
                # Fall through to snap.
                ei = None
            if ei is not None:
                return ei
            # Fall through to snap on BFFM2 unavailability.
        return ei_store.getEmissionIndexByMode(mode)
    except Exception:  # pragma: no cover
        # Engine misconfigured (mode not in its table). Callers log
        # and skip.
        return None
