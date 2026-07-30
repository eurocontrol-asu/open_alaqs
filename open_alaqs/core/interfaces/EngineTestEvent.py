"""Dataclass wrapping one row of ``engine_test_events``.

Introduced in Phase 2 alongside ``EngineTestEventsStore``. Consumed by
the Phase 3 compute module (``EngineTestSourceModule``) and by the
convenience accessor ``AreaSources.getEngineTestEvents``.

Structurally mirrors ``Movement`` in ``Movement.py``: field parsing in
``__init__`` from a dict, accessor methods per field, resolvers against
the aircraft/engine stores.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from open_alaqs.core.alaqslogging import get_logger

logger = get_logger(__name__)


# Tolerance for the "running seconds exceed the window duration" consistency
# check. Kept generous (60 s) because logbook remarks in the wild commonly
# round to the nearest minute; a stricter tolerance would fire on innocuous
# rounding and drown out the real anomalies.
_RUNNING_EXCEEDS_WINDOW_TOLERANCE_S = 60

_MODE_KEYS = ("TX", "AP", "CL", "TO")
_MODE_COLUMN = {
    "TX": "t_TX_s",
    "AP": "t_AP_s",
    "CL": "t_CL_s",
    "TO": "t_TO_s",
}


def _parse_iso_datetime(s: Any) -> Optional[datetime]:
    """Best-effort ISO 8601 parser for ``start_datetime`` / ``end_datetime``.

    Returns ``None`` for empty inputs. Raises ``ValueError`` for
    unparseable non-empty inputs, matching the datetime module's own
    behaviour so bad data is loud, not silent.
    """
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    # datetime.fromisoformat accepts YYYY-MM-DDTHH:MM:SS and variants.
    # Normalise a trailing "Z" (UTC) into "+00:00" for py<3.11 compat.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _to_int(v: Any, default: int = 0) -> int:
    """Coerce to int with a default. Used for engine_count and mode-time
    columns to tolerate NULL / empty-string values coming from SQLite.
    """
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class EngineTestEvent:
    """One engine-test event, wrapping one row of ``engine_test_events``.

    Constructed either from a ``val`` dict (as returned by
    ``EngineTestEventsDatabase.getEntries().values()``) or field-by-field
    via the setters. Missing / empty fields fall back to safe defaults so
    partial rows do not crash construction; ``getConsistencyWarnings``
    surfaces anything unusual.
    """

    def __init__(self, val: Optional[dict] = None):
        if val is None:
            val = {}

        self._event_id: Optional[int] = (
            _to_int(val.get("event_id"), default=None)
            if val.get("event_id") is not None
            else None
        )
        self._source_id: str = str(val.get("source_id", "")).strip()
        self._test_id: str = str(val.get("test_id", "") or "").strip()

        # Datetimes: parsed lazily so a bad string doesn't abort construction,
        # but the raw string is preserved on the instance so callers can see
        # the offending input in error messages.
        self._start_datetime_raw = val.get("start_datetime")
        self._end_datetime_raw = val.get("end_datetime")
        try:
            self._start_datetime = _parse_iso_datetime(self._start_datetime_raw)
        except ValueError:
            logger.warning(
                "EngineTestEvent %s: unparseable start_datetime %r",
                self._event_id,
                self._start_datetime_raw,
            )
            self._start_datetime = None
        try:
            self._end_datetime = _parse_iso_datetime(self._end_datetime_raw)
        except ValueError:
            logger.warning(
                "EngineTestEvent %s: unparseable end_datetime %r",
                self._event_id,
                self._end_datetime_raw,
            )
            self._end_datetime = None

        self._aircraft_type: str = str(val.get("aircraft_type", "")).strip()

        # engine_uid may be NULL in the schema; empty string treated same as NULL.
        raw_uid = val.get("engine_uid")
        self._engine_uid: Optional[str] = (
            str(raw_uid).strip() if raw_uid not in (None, "") else None
        )

        # engine_count may be NULL; None means "use aircraft default at
        # resolve time".
        raw_count = val.get("engine_count")
        self._engine_count: Optional[int] = (
            _to_int(raw_count) if raw_count not in (None, "") else None
        )

        self._t_TX_s: int = _to_int(val.get("t_TX_s"))
        self._t_AP_s: int = _to_int(val.get("t_AP_s"))
        self._t_CL_s: int = _to_int(val.get("t_CL_s"))
        self._t_TO_s: int = _to_int(val.get("t_TO_s"))

        self._thrust_mode: str = str(val.get("thrust_mode", "snap") or "snap").strip()

        # instudy: TEXT '1' / '0'; treat NULL/empty as in-study (default '1'
        # in schema). Matches how AreaSources handles instudy.
        self._instudy: bool = str(val.get("instudy", "1") or "1").strip() == "1"

    # ── Identity ────────────────────────────────────────────────────────

    def getEventId(self) -> Optional[int]:
        return self._event_id

    def getSourceId(self) -> str:
        return self._source_id

    def getTestId(self) -> str:
        return self._test_id

    # ── Datetime / duration ─────────────────────────────────────────────

    def getStartDateTime(self) -> Optional[datetime]:
        return self._start_datetime

    def getEndDateTime(self) -> Optional[datetime]:
        return self._end_datetime

    def getDurationSeconds(self) -> Optional[float]:
        """Total seconds between start and end. Returns None if either
        datetime failed to parse."""
        if self._start_datetime is None or self._end_datetime is None:
            return None
        return (self._end_datetime - self._start_datetime).total_seconds()

    # ── Mode times ──────────────────────────────────────────────────────

    def getModeTimes(self) -> dict:
        """Return per-mode seconds as a dict keyed by ICAO mode code."""
        return {
            "TX": self._t_TX_s,
            "AP": self._t_AP_s,
            "CL": self._t_CL_s,
            "TO": self._t_TO_s,
        }

    def getRunningSeconds(self) -> int:
        """Sum of the four per-mode seconds. Total time the engine is
        producing emissions during the event."""
        return self._t_TX_s + self._t_AP_s + self._t_CL_s + self._t_TO_s

    # ── Aircraft / engine identity ──────────────────────────────────────

    def getAircraftType(self) -> str:
        return self._aircraft_type

    def getEngineUid(self) -> Optional[str]:
        return self._engine_uid

    def getEngineCount(self) -> Optional[int]:
        """Raw engine_count as stored on the row. None means "not set;
        resolve against aircraft default at compute time". Use
        ``resolveEngineCount`` when you want the effective count.
        """
        return self._engine_count

    def getThrustMode(self) -> str:
        return self._thrust_mode

    def isInStudy(self) -> bool:
        return self._instudy

    # ── Resolvers against upstream stores ───────────────────────────────

    def getAircraft(self, aircraft_store) -> Optional[Any]:
        """Resolve ``aircraft_type`` against an ``AircraftStore``.

        Returns the ``Aircraft`` instance if found, else ``None``. Does
        not raise; the caller decides whether an unresolved type is
        fatal or just a warning.
        """
        if not self._aircraft_type or aircraft_store is None:
            return None
        try:
            return aircraft_store.getObject(self._aircraft_type)
        except Exception:  # pragma: no cover
            return None

    def getEngine(self, engine_store, aircraft=None) -> Optional[Any]:
        """Resolve the engine for this event.

        Precedence:
          1. If ``engine_uid`` is set on the row, look it up in the
             ``EngineStore``.
          2. Otherwise fall back to ``aircraft.getDefaultEngine()`` if
             ``aircraft`` is provided.
          3. Otherwise ``None``.

        Does not raise; unresolved returns ``None``.
        """
        if self._engine_uid and engine_store is not None:
            try:
                eng = engine_store.getObject(self._engine_uid)
                if eng is not None:
                    return eng
            except Exception:  # pragma: no cover
                pass

        if aircraft is not None:
            try:
                return aircraft.getDefaultEngine()
            except Exception:  # pragma: no cover
                return None

        return None

    def resolveEngineCount(self, aircraft=None) -> Optional[int]:
        """Return the effective engine count for this event.

        Uses the row's ``engine_count`` if set, else the aircraft's
        default engine count if ``aircraft`` is provided, else ``None``.
        """
        if self._engine_count is not None:
            return self._engine_count
        if aircraft is not None:
            for attr in ("engine_count", "getEngineCount"):
                candidate = getattr(aircraft, attr, None)
                if callable(candidate):
                    try:
                        return int(candidate())
                    except Exception:  # pragma: no cover
                        pass
                elif candidate is not None:
                    try:
                        return int(candidate)
                    except Exception:  # pragma: no cover
                        pass
        return None

    # ── Diagnostics ─────────────────────────────────────────────────────

    def getConsistencyWarnings(self) -> list:
        """Return a list of non-fatal issues detected on this event.

        Codes returned:
          * ``"missing_start_datetime"`` / ``"missing_end_datetime"``:
            datetime failed to parse.
          * ``"end_before_start"``: end is chronologically before start.
          * ``"negative_running"``: at least one t_* is negative.
          * ``"running_exceeds_window"``: sum of t_* exceeds
            ``duration + tolerance`` (tolerance = 60 s, generous because
            logbook remarks commonly round to the minute).
          * ``"zero_running"``: sum of t_* is zero; the event will
            emit nothing.
          * ``"missing_aircraft_type"``: aircraft_type is empty.
        """
        warnings = []

        if self._start_datetime is None:
            warnings.append("missing_start_datetime")
        if self._end_datetime is None:
            warnings.append("missing_end_datetime")

        if (
            self._start_datetime is not None
            and self._end_datetime is not None
            and self._end_datetime < self._start_datetime
        ):
            warnings.append("end_before_start")

        if any(t < 0 for t in (self._t_TX_s, self._t_AP_s, self._t_CL_s, self._t_TO_s)):
            warnings.append("negative_running")

        running = self.getRunningSeconds()
        duration = self.getDurationSeconds()
        if (
            duration is not None
            and running > duration + _RUNNING_EXCEEDS_WINDOW_TOLERANCE_S
        ):
            warnings.append("running_exceeds_window")

        if running == 0:
            warnings.append("zero_running")

        if not self._aircraft_type:
            warnings.append("missing_aircraft_type")

        return warnings

    # ── Debug / logging ─────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"EngineTestEvent(event_id={self._event_id!r}, "
            f"source_id={self._source_id!r}, test_id={self._test_id!r}, "
            f"aircraft_type={self._aircraft_type!r}, "
            f"engine_uid={self._engine_uid!r}, "
            f"start={self._start_datetime!r}, end={self._end_datetime!r}, "
            f"running={self.getRunningSeconds()}s, "
            f"thrust_mode={self._thrust_mode!r}, instudy={self._instudy})"
        )
