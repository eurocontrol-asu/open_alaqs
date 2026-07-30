"""Schema and store for the ``engine_test_events`` table.

Phase 1b introduced the schema (``EngineTestEventsDatabase``). Phase 2
adds the loader (``EngineTestEventsStore``), which reads rows into
``EngineTestEvent`` instances and offers period-window and
source-window filters used by the Phase 3 compute module.

Design context (per phase 0 decisions memo):

- D5: one aircraft/engine type per event. Mixed-type tests are represented
  as two rows sharing ``source_id``, ``start_datetime``, ``end_datetime``.
- D10: interval-overlap semantics for period membership. An event with
  window ``[e_start, e_end]`` overlaps a period ``[p_start, p_end]`` iff
  ``e_start < p_end AND e_end > p_start``. Strict ``<`` (event touching
  the period boundary does not overlap it).
- D12: mode times stored as INTEGER seconds. Sub-second precision is not
  meaningful for run-up events.
- D2 (thrust mode): per-event override of the study-wide default. The
  ``thrust_mode`` column carries either ``'snap'`` (nearest ICAO point) or
  ``'meem'`` (interpolation). Default ``'snap'``.

Foreign key on ``source_id`` intentionally NOT declared. SQLite does not
enforce FKs by default in this codebase, and orphaned events must be
tolerated (a user might delete the parent area source without ON DELETE
CASCADE). The Phase 3 compute module handles orphans by skip-with-warning.

Index on ``(source_id, start_datetime)`` supports the period-window
query pattern of the compute module.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Optional

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.EngineTestEvent import EngineTestEvent
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


class EngineTestEventsDatabase(SQLSerializable, metaclass=Singleton):
    """Schema wrapper for the ``engine_test_events`` table.

    Instantiating this class against a database is enough for the
    template-generation pipeline to CREATE the table. Loading rows into
    ``EngineTestEvent`` objects is the responsibility of
    ``EngineTestEventsStore``.
    """

    TABLE_NAME = "engine_test_events"

    def __init__(
        self,
        db_path_string,
        table_columns_type_dict=None,
        primary_key="",
        geometry_columns=None,
        deserialize=True,
    ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("event_id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                    ("source_id", "TEXT NOT NULL"),
                    ("test_id", "TEXT"),
                    ("start_datetime", "TEXT NOT NULL"),
                    ("end_datetime", "TEXT NOT NULL"),
                    ("aircraft_type", "TEXT NOT NULL"),
                    ("engine_uid", "TEXT"),
                    ("engine_count", "INTEGER"),
                    ("t_TX_s", "INTEGER NOT NULL DEFAULT 0"),
                    ("t_AP_s", "INTEGER NOT NULL DEFAULT 0"),
                    ("t_CL_s", "INTEGER NOT NULL DEFAULT 0"),
                    ("t_TO_s", "INTEGER NOT NULL DEFAULT 0"),
                    ("thrust_mode", "TEXT NOT NULL DEFAULT 'snap'"),
                    ("instudy", "TEXT NOT NULL DEFAULT '1'"),
                ]
            )

        # No geometry columns: events reference an area source via
        # source_id; the geometry lives on shapes_area_sources.
        if geometry_columns is None:
            geometry_columns = []

        SQLSerializable.__init__(
            self,
            db_path_string,
            self.TABLE_NAME,
            table_columns_type_dict,
            primary_key,
            geometry_columns,
        )

        # deserialize is defensive: fresh projects lack the table; the
        # table also doesn't exist in pre-v1b projects opened by the new
        # plugin before migration has been run. Both cases are non-fatal
        # here (the Store instantiates with an empty entry set); the
        # migration script or template creation restore the table.
        if deserialize:
            try:
                self.deserialize()
            except Exception:
                pass


class EngineTestEventsStore(Store, metaclass=Singleton):
    """Loader for ``engine_test_events`` into ``EngineTestEvent`` objects.

    Consumed by the Phase 3 ``EngineTestSourceModule`` and by the
    ``AreaSources.getEngineTestEvents`` convenience accessor. Provides
    two filtered views:
      * ``getEventsBySourceId(source_id)`` — all events for one test site.
      * ``getEventsInPeriod(start, end)`` — all events overlapping a
        period window, across all test sites. Interval-overlap semantics
        (per D10 in the phase 0 memo): ``e_start < p_end AND e_end > p_start``.
    """

    def __init__(self, db_path: str = "", db: Optional[dict] = None):
        if db is None:
            db = {}
        Store.__init__(self, ordered=True)

        self._db_path = db_path

        self._events_db: Optional[EngineTestEventsDatabase] = None
        if "engine_test_events_db" in db:
            candidate = db["engine_test_events_db"]
            if isinstance(candidate, EngineTestEventsDatabase):
                self._events_db = candidate

        if self._events_db is None:
            self._events_db = EngineTestEventsDatabase(db_path)

        self.initEngineTestEvents()

    def initEngineTestEvents(self) -> None:
        """Load all rows from the database into ``EngineTestEvent``
        instances keyed by ``event_id`` in the Store's ordered map.

        Rows with a NULL / missing ``event_id`` are skipped with a
        warning; they cannot be reliably indexed. (This should never
        happen in practice because the schema declares
        ``INTEGER PRIMARY KEY AUTOINCREMENT``, but defensive.)
        """
        try:
            entries = self._events_db.getEntries()
        except Exception as e:
            # Table absent (pre-v1b project pre-migration, or a fresh
            # DB that has not run recreate_table). Non-fatal; store
            # stays empty and downstream sees no events.
            logger.debug("EngineTestEventsStore: no entries loaded (%s)", e)
            return

        for key, event_dict in list(entries.items()):
            event = EngineTestEvent(event_dict)
            event_id = event.getEventId()
            if event_id is None:
                logger.warning(
                    "EngineTestEventsStore: row with no event_id skipped: %r",
                    event_dict,
                )
                continue
            # Store keyed by event_id, an int. Store's ordered=True
            # preserves insertion (= DB row) order for stable iteration.
            self.setObject(event_id, event)

    def getEngineTestEventsDatabase(self) -> EngineTestEventsDatabase:
        return self._events_db

    def getEventsBySourceId(self, source_id: str) -> list:
        """Return all events whose ``source_id`` matches. Order is stable
        (row order in the database). Returns ``[]`` for unknown ids.
        """
        if not source_id:
            return []
        return [
            event
            for event in self._objects.values()
            if event.getSourceId() == source_id
        ]

    def getEventsInPeriod(self, period_start: datetime, period_end: datetime) -> list:
        """Return all events whose window overlaps ``[period_start, period_end]``.

        Interval-overlap semantics (D10 in the phase 0 memo):
        ``e_start < period_end AND e_end > period_start``. Strict ``<`` /
        ``>``; an event ending exactly at ``period_start`` or starting
        exactly at ``period_end`` does not overlap.

        Events with missing or unparseable start / end datetimes are
        skipped (they surface as consistency warnings elsewhere).
        """
        if period_start is None or period_end is None:
            return []
        out = []
        for event in self._objects.values():
            e_start = event.getStartDateTime()
            e_end = event.getEndDateTime()
            if e_start is None or e_end is None:
                continue
            if e_start < period_end and e_end > period_start:
                out.append(event)
        return out
