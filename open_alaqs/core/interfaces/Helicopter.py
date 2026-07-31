"""
Helicopter catalog interfaces.

Mirrors the Aircraft / AircraftDatabase / AircraftStore pattern but reads from
the dedicated helicopter tables (default_helicopter, default_helicopter_engines)
introduced for the FOCA 2015 emissions methodology.

Key differences from Aircraft:
  * helicopter_category is derived at runtime from (engine_type, engine_count,
    mtow) per FOCA section 2.4 — not stored in the table.
  * variant_label disambiguates multiple rows per ICAO (e.g. A109E_POWER vs
    A109II). The composite logical key is (icao, variant_label).
  * APU and gate emissions are skipped entirely for helicopters (see
    MovementEmissionCalculator dispatch in Phase 2b).
  * Engine catalog is minimal: engine_name, engine_full_name, engine_type,
    max_shp_per_engine, source. No precomputed FF/EI columns;
    emissions are computed live by foca_heli.compute_lto() under the FOCA
    formulas.
"""

import os
import sqlite3
from collections import OrderedDict

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# HelicopterEngine — engine catalog entry (no precomputed EI; emissions live)
# ---------------------------------------------------------------------------


class HelicopterEngine:
    """A single engine in the helicopter engines catalog.

    Carries only metadata + max_shp. Fuel flow and emission indices are
    computed at calculation time via foca_heli.compute_lto(max_shp,
    helicopter_category, n_engines).
    """

    def __init__(self, val=None):
        if val is None:
            val = {}
        self._engine_name = str(val.get("engine_name") or "")
        self._engine_full_name = str(val.get("engine_full_name") or self._engine_name)
        self._engine_type = str(val.get("engine_type") or "")  # PISTON / TURBOSHAFT
        self._max_shp_per_engine = float(val.get("max_shp_per_engine") or 0.0)
        self._source = str(val.get("source") or "")

    def getName(self) -> str:
        return self._engine_name

    def getFullName(self) -> str:
        return self._engine_full_name

    def getType(self) -> str:
        return self._engine_type

    def getMaxShpPerEngine(self) -> float:
        return self._max_shp_per_engine

    def getSource(self) -> str:
        return self._source

    def __str__(self) -> str:
        return (
            f"HelicopterEngine '{self._engine_name}': "
            f"{self._engine_type}, max_shp={self._max_shp_per_engine}"
        )


# ---------------------------------------------------------------------------
# Helicopter — catalog entry from default_helicopter
# ---------------------------------------------------------------------------


class Helicopter:
    """A single helicopter type/variant from default_helicopter.

    helicopter_category is derived at runtime in getCategory() per FOCA 2015
    section 2.4: PISTON | SINGLE_TURBOSHAFT | TWIN_TURBOSHAFT_LIGHT |
    TWIN_TURBOSHAFT_HEAVY. The category drives mode power settings used by
    the FOCA emission formulas.
    """

    # Category boundary per FOCA section 2.4: twin engines, MTOM > 3400 kg
    # is HEAVY; otherwise LIGHT.
    TWIN_HEAVY_MTOM_THRESHOLD_KG = 3400.0

    def __init__(self, val=None):
        if val is None:
            val = {}
        self._icao = str(val.get("icao") or "unknown")
        self._variant_label = str(val.get("variant_label") or "")
        self._manufacturer = str(val.get("manufacturer") or "")
        self._name = str(val.get("name") or "")
        try:
            self._mtow = float(val.get("mtow_kg") or 0)
        except (TypeError, ValueError):
            self._mtow = 0.0
        try:
            self._engine_count = int(val.get("engine_count") or 0)
        except (TypeError, ValueError):
            self._engine_count = 0
        self._engine_id = str(val.get("engine") or "")  # FK to engines.engine_name
        self._engine_name = str(val.get("engine_name") or self._engine_id)
        try:
            self._max_shp_per_engine = float(val.get("max_shp_per_engine") or 0)
        except (TypeError, ValueError):
            self._max_shp_per_engine = 0.0
        # is_default may arrive as bool, int, or string depending on round-trip:
        # CSV "true"/"false" -> pandas bool -> SQLite TEXT stores '1'/'0'.
        # Accept all of: True, 1, "true", "1", "yes" (case-insensitive). Anything
        # else is False.
        raw_is_default = val.get("is_default")
        if isinstance(raw_is_default, bool):
            self._is_default = raw_is_default
        elif isinstance(raw_is_default, (int, float)):
            self._is_default = bool(raw_is_default)
        else:
            self._is_default = str(raw_is_default).strip().lower() in (
                "true",
                "1",
                "yes",
            )

        self._engine: HelicopterEngine | None = None

    # -- accessors -----------------------------------------------------------

    def getICAOIdentifier(self) -> str:
        return self._icao

    def getVariantLabel(self) -> str:
        return self._variant_label

    def getManufacturer(self) -> str:
        return self._manufacturer

    def getName(self) -> str:
        return self._name

    def getMTOW(self) -> float:
        return self._mtow

    def getEngineCount(self) -> int:
        return self._engine_count

    def getEngineIdentifier(self) -> str:
        """FK value pointing into default_helicopter_engines.engine_name."""
        return self._engine_id

    def getEngineName(self) -> str:
        return self._engine_name

    def getMaxShpPerEngine(self) -> float:
        return self._max_shp_per_engine

    def isDefault(self) -> bool:
        return self._is_default

    def getEngine(self) -> "HelicopterEngine | None":
        return self._engine

    def setEngine(self, engine: HelicopterEngine) -> None:
        self._engine = engine

    # -- derived ------------------------------------------------------------

    def getCategory(self) -> str:
        """FOCA 2015 section 2.4 category, derived at runtime.

        Returns one of PISTON, SINGLE_TURBOSHAFT, TWIN_TURBOSHAFT_LIGHT,
        TWIN_TURBOSHAFT_HEAVY. Returns 'UNKNOWN' if inputs are insufficient
        (e.g. engine not yet bound, missing MTOM for a twin).
        """
        if self._engine is None:
            return "UNKNOWN"
        engine_type = self._engine.getType()
        if engine_type == "PISTON":
            return "PISTON"
        if engine_type != "TURBOSHAFT":
            return "UNKNOWN"
        if self._engine_count == 1:
            return "SINGLE_TURBOSHAFT"
        if self._mtow <= 0:
            return "UNKNOWN"
        if self._mtow <= self.TWIN_HEAVY_MTOM_THRESHOLD_KG:
            return "TWIN_TURBOSHAFT_LIGHT"
        return "TWIN_TURBOSHAFT_HEAVY"

    # -- dispatch ----------------------------------------------------------

    def is_helicopter(self) -> bool:
        return True

    # -- groups for backward-compat with code that reads getGroup() --------

    def getGroup(self) -> str:
        """Legacy group string for code paths that still check getGroup().

        Returns 'HELICOPTER' (matching the existing convention used by some
        legacy code branches in MovementEmissionCalculator).
        """
        return "HELICOPTER"

    def getEmissionDynamicsByMode(self):
        """Helicopters do not participate in the smooth-and-shift plume model.

        The S&S plume model represents thermal buoyancy of jet/turboprop
        exhaust; helicopter rotor downwash is a different physics not
        modelled here. Returning an empty mapping causes
        ``GeoTransformation.create_polygon_3d`` to raise ``KeyError`` on
        the ``[lto_mode]`` subscript, which is caught by the existing
        ``except (KeyError, TypeError)`` block and falls through to
        zero-extension defaults (the same behaviour as an aircraft with
        no ``default_emission_dynamics`` entry). Emission masses are
        preserved.

        Without this method, ``[lto_mode]`` is attempted on the return
        value of a missing method and Python raises ``AttributeError``,
        which is NOT caught by the existing exception tuple, aborting
        the inventory build. See issue #340.
        """
        return {}

    def __str__(self) -> str:
        return (
            f"\n Helicopter '{self._icao}' / variant '{self._variant_label}':"
            f"\n\t Name: {self._name}"
            f"\n\t Manufacturer: {self._manufacturer}"
            f"\n\t Category: {self.getCategory()}"
            f"\n\t MTOW: {self._mtow} kg"
            f"\n\t Engine count: {self._engine_count}"
            f"\n\t Engine: {self._engine_name} ({self._max_shp_per_engine} SHP)"
            f"\n\t Default: {self._is_default}"
        )


# ---------------------------------------------------------------------------
# HelicopterDatabase — reads default_helicopter table
# ---------------------------------------------------------------------------


class HelicopterDatabase(SQLSerializable, metaclass=Singleton):
    """Grants access to the default_helicopter table."""

    TABLE_NAME = "default_helicopter"

    def __init__(
        self,
        db_path_string,
        table_columns_type_dict=None,
        primary_key="",
        deserialize=True,
    ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY"),
                    ("icao", "TEXT"),
                    ("variant_label", "TEXT"),
                    ("manufacturer", "TEXT"),
                    ("name", "TEXT"),
                    ("mtow_kg", "DECIMAL"),
                    ("engine_count", "INTEGER"),
                    ("engine", "TEXT"),  # FK to default_helicopter_engines.engine_name
                    ("engine_name", "TEXT"),  # display name
                    ("max_shp_per_engine", "DECIMAL"),
                    (
                        "is_default",
                        "INTEGER",
                    ),  # 1/0 for clean pandas/SQLite round-trip; Helicopter.__init__ tolerates bool/int/string
                ]
            )

        SQLSerializable.__init__(
            self,
            db_path_string,
            self.TABLE_NAME,
            table_columns_type_dict,
            primary_key,
        )

        if deserialize and self._db_path:
            try:
                self.deserialize()
            except sqlite3.OperationalError as e:
                # Legacy projects (pre-5.2.0) don't have default_helicopter.
                # Treat as empty catalog: hasIdentifier() returns False for
                # every identifier, fixed-wing dispatch always wins. Migrating
                # the project via scripts/migrate_alaqs.py creates the table.
                if "no such table" in str(e).lower():
                    logger.warning(
                        "default_helicopter table missing from %s; "
                        "helicopter catalog will be empty. Migrate the "
                        "project via scripts/migrate_alaqs.py to add it.",
                        self._db_path,
                    )
                else:
                    raise


# ---------------------------------------------------------------------------
# HelicopterEnginesDatabase — reads default_helicopter_engines table
# ---------------------------------------------------------------------------


class HelicopterEnginesDatabase(SQLSerializable, metaclass=Singleton):
    """Grants access to the default_helicopter_engines table.

    The FOCA 2015 clean-schema helicopter engine catalog. Carries only
    engine metadata + max_shp; emissions are computed live via
    foca_heli.compute_lto() under FOCA formulas (no per-mode emission
    indices stored on disk).
    """

    TABLE_NAME = "default_helicopter_engines"

    def __init__(
        self,
        db_path_string,
        table_columns_type_dict=None,
        primary_key="",
        deserialize=True,
    ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY"),
                    ("engine_name", "TEXT"),
                    ("engine_full_name", "TEXT"),
                    ("engine_type", "TEXT"),  # PISTON / TURBOSHAFT
                    ("max_shp_per_engine", "DECIMAL"),
                    ("source", "TEXT"),
                ]
            )

        SQLSerializable.__init__(
            self,
            db_path_string,
            self.TABLE_NAME,
            table_columns_type_dict,
            primary_key,
        )

        if deserialize and self._db_path:
            try:
                self.deserialize()
            except sqlite3.OperationalError as e:
                # Legacy projects (pre-5.2.0) don't have default_helicopter_engines.
                # See HelicopterDatabase above for rationale.
                if "no such table" in str(e).lower():
                    logger.warning(
                        "default_helicopter_engines table missing from %s; "
                        "helicopter engine catalog will be empty. Migrate the "
                        "project via scripts/migrate_alaqs.py to add it.",
                        self._db_path,
                    )
                else:
                    raise


# ---------------------------------------------------------------------------
# HelicopterStore — Singleton view over both tables, used by Movement loader
# ---------------------------------------------------------------------------


class HelicopterStore(Store, metaclass=Singleton):
    """Singleton store of all Helicopter objects, joined to their engines.

    Resolves Helicopter objects by (icao, variant_label) AND by icao alone
    (returning is_default=true row when only ICAO is given).
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._helicopter_db = None
        if "helicopter_db" in db:
            if isinstance(db["helicopter_db"], HelicopterDatabase):
                self._helicopter_db = db["helicopter_db"]
            elif isinstance(db["helicopter_db"], str) and os.path.isfile(
                db["helicopter_db"]
            ):
                self._helicopter_db = HelicopterDatabase(db["helicopter_db"])
        if self._helicopter_db is None:
            self._helicopter_db = HelicopterDatabase(db_path)

        self._engines_db = None
        if "helicopter_engines_db" in db:
            if isinstance(db["helicopter_engines_db"], HelicopterEnginesDatabase):
                self._engines_db = db["helicopter_engines_db"]
            elif isinstance(db["helicopter_engines_db"], str) and os.path.isfile(
                db["helicopter_engines_db"]
            ):
                self._engines_db = HelicopterEnginesDatabase(
                    db["helicopter_engines_db"]
                )
        if self._engines_db is None:
            self._engines_db = HelicopterEnginesDatabase(db_path)

        # Composite-key map: (icao, variant_label) -> Helicopter
        self._by_composite_key: dict[tuple[str, str], Helicopter] = {}
        # Default-variant map: icao -> Helicopter (is_default=true row)
        self._defaults_by_icao: dict[str, Helicopter] = {}
        # Variant-label map: variant_label -> Helicopter (globally unique)
        # Lets user_aircraft_movements.aircraft hold EITHER an ICAO or a
        # variant_label in one column; getByIdentifier resolves both.
        self._by_variant_label: dict[str, Helicopter] = {}
        # Engines by engine_name
        self._engines_by_name: dict[str, HelicopterEngine] = {}

        self._init_engines()
        self._init_helicopters()

    # -- init helpers -----------------------------------------------------

    def _init_engines(self) -> None:
        for _key, eng_dict in self._engines_db.getEntries().items():
            engine = HelicopterEngine(eng_dict)
            name = engine.getName()
            if not name:
                logger.warning(
                    "helicopter engine row missing engine_name: %r", eng_dict
                )
                continue
            if name in self._engines_by_name:
                logger.warning(
                    "duplicate helicopter engine '%s'; later row overwrites earlier",
                    name,
                )
            self._engines_by_name[name] = engine

    def _init_helicopters(self) -> None:
        for _key, heli_dict in self._helicopter_db.getEntries().items():
            heli = Helicopter(heli_dict)
            icao = heli.getICAOIdentifier()
            vlabel = heli.getVariantLabel()
            if not icao:
                logger.warning("helicopter row missing icao: %r", heli_dict)
                continue

            # Resolve engine FK
            eng_id = heli.getEngineIdentifier()
            engine = self._engines_by_name.get(eng_id)
            if engine is None:
                logger.warning(
                    "helicopter %s/%s references unknown engine '%s'",
                    icao,
                    vlabel,
                    eng_id,
                )
            heli.setEngine(engine)  # may be None; getCategory handles it

            self._by_composite_key[(icao, vlabel)] = heli
            if vlabel:
                # Index by variant_label too. Globally unique by data convention;
                # log if a duplicate appears (data error). Skip when variant_label
                # equals icao to avoid shadowing the icao -> default-row mapping
                # in confusing ways (the default mapping below handles that case).
                if vlabel != icao:
                    if vlabel in self._by_variant_label:
                        logger.warning(
                            "duplicate variant_label '%s' (already mapped to %s/%s); "
                            "later row %s/%s overwrites earlier",
                            vlabel,
                            self._by_variant_label[vlabel].getICAOIdentifier(),
                            self._by_variant_label[vlabel].getVariantLabel(),
                            icao,
                            vlabel,
                        )
                    self._by_variant_label[vlabel] = heli
            if heli.isDefault():
                if icao in self._defaults_by_icao:
                    logger.warning(
                        "multiple is_default=true rows for icao '%s'; "
                        "later row overwrites earlier",
                        icao,
                    )
                self._defaults_by_icao[icao] = heli

        # Also push them into the Store dict for getObject()-style lookups.
        for (icao, vlabel), heli in self._by_composite_key.items():
            self.setObject(f"{icao}/{vlabel}", heli)

    # -- public lookups ---------------------------------------------------

    def getByIdentifier(self, identifier: str) -> "Helicopter | None":
        """Resolve an identifier that may be either an ICAO or a variant_label.

        Single-column dispatch for user_aircraft_movements.aircraft:
            "A109"           -> ICAO match, returns is_default=true row (A109E_POWER)
            "A109K2"         -> variant_label match, returns that specific row
            "AS350B3_ASTAR"  -> variant_label match
            "B212"           -> matches both ICAO and own variant_label (same row)
            "AS50"           -> ICAO match, returns AS350B2 (default)

        ICAO takes precedence over variant_label when both match (preserves
        backward-compatible behavior of ICAO-only references in existing data).
        Returns None for unknown identifiers (caller falls through to
        AircraftStore for fixed-wing).
        """
        if not identifier:
            return None
        # ICAO match wins (backward-compatible default behavior)
        heli = self._defaults_by_icao.get(identifier)
        if heli is not None:
            return heli
        # Fall back to variant_label lookup
        return self._by_variant_label.get(identifier)

    def hasIdentifier(self, identifier: str) -> bool:
        """True if identifier is either a helicopter ICAO or a variant_label."""
        if not identifier:
            return False
        return (
            identifier in self._defaults_by_icao or identifier in self._by_variant_label
        )

    def getByIcaoVariant(
        self, icao: str, variant_label: str = ""
    ) -> "Helicopter | None":
        """Explicit composite lookup. Use getByIdentifier() for the
        single-column user-facing path.

        Look up by (icao, variant_label). If variant_label is empty or does
        not match, returns the is_default=true row for that icao.
        """
        if icao and variant_label:
            heli = self._by_composite_key.get((icao, variant_label))
            if heli is not None:
                return heli
            logger.debug(
                "no helicopter variant '%s/%s'; falling back to is_default row",
                icao,
                variant_label,
            )
        return self._defaults_by_icao.get(icao)

    def hasIcao(self, icao: str) -> bool:
        return icao in self._defaults_by_icao

    def getEngine(self, engine_name: str) -> "HelicopterEngine | None":
        return self._engines_by_name.get(engine_name)

    def getDatabasePath(self) -> str:
        return self._db_path

    def getHelicopterDatabase(self) -> HelicopterDatabase:
        return self._helicopter_db

    def getHelicopterEnginesDatabase(self) -> HelicopterEnginesDatabase:
        return self._engines_db
