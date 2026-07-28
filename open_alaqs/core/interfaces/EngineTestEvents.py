"""Schema definition for the ``engine_test_events`` table.

Phase 1b introduces only the schema. The Python interface layer
(``EngineTestEvent`` dataclass, ``EngineTestEventsStore``) is deferred
to Phase 2. This file exists so ``tools/template_build/generate_templates.py``
can register the table via the standard ``SQLSerializable`` mechanism, so
that fresh projects created from the template already contain the table.

Design context (per phase 0 decisions memo):

- D5: one aircraft/engine type per event. Mixed-type tests are represented
  as two rows sharing ``source_id``, ``start_datetime``, ``end_datetime``.
- D12: mode times stored as INTEGER seconds (``t_TX_s`` etc.). Sub-second
  precision is not meaningful for run-up events.
- D2 (thrust mode): per-event override of the study-wide default. The
  ``thrust_mode`` column carries either ``'snap'`` (nearest ICAO point) or
  ``'meem'`` (interpolation). Default ``'snap'``.
- Boolean convention (per Phase 1b decision): ``instudy`` uses TEXT
  ``'0'`` / ``'1'`` for parity with the rest of the codebase.

Foreign key is intentionally NOT declared. SQLite does not enforce FKs
by default in this codebase, and orphaned events must be tolerated
(a user might delete the parent area source in QGIS without
ON DELETE CASCADE). The engine-test source module (Phase 3) handles
orphans by skip-with-warning.

Index on ``(source_id, start_datetime)`` supports the period-window
query pattern of the compute module.
"""

from __future__ import annotations

from collections import OrderedDict

from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.tools.Singleton import Singleton


class EngineTestEventsDatabase(SQLSerializable, metaclass=Singleton):
    """Schema-only representation of the ``engine_test_events`` table.

    Instantiating this class against a database is enough for the
    template-generation pipeline to CREATE the table. Reading and
    writing rows is deferred to ``EngineTestEventsStore`` in Phase 2.
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

        # Deserialize is a no-op for Phase 1b since we do not yet own
        # a dataclass reader; the table just needs to exist.
        if deserialize:
            try:
                self.deserialize()
            except Exception:
                # Fresh project: table not present yet. Non-fatal —
                # recreate_table() will create it during template generation.
                pass
