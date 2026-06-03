from collections import OrderedDict

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Engine import (
    EngineEmissionIndex,
)
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


class EngineEmissionFactorsStartDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to emission factors that are related to an engine start
    """

    TABLE_NAME = "default_aircraft_start_ef"

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
                    ("aircraft_group", "VARCHAR(23) NOT NULL"),
                    ("aircraft_code", "VARCHAR(13)"),
                    ("emission_unit", "VARCHAR(16)"),
                    ("co", "DOUBLE PRECISION NULL"),
                    ("hc", "DOUBLE PRECISION NULL"),
                    ("nox", "DOUBLE PRECISION NULL"),
                    ("sox", "DOUBLE PRECISION NULL"),
                    ("pm10", "DOUBLE PRECISION NULL"),
                    ("p1", "DOUBLE PRECISION NULL"),
                    ("p2", "DOUBLE PRECISION NULL"),
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
            self.deserialize()


class EngineModeDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to aircraft-engine-emission indices
    """

    TABLE_NAME = "default_aircraft_engine_mode"

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
                    ("mode", "VARCHAR(2)"),
                    ("thrust", "DECIMAL NULL"),
                    ("description", "TEXT"),
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
            self.deserialize()


class EngineEmissionIndicesDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to aircraft-engine-emission indices
    """

    TABLE_NAME = "default_aircraft_engine_ei"

    def __init__(
        self,
        db_path_string,
        table_columns_type_dict=None,
        primary_key="",
        deserialize=True,
    ):

        if table_columns_type_dict is None:
            # Columns marked `# DEPRECATED (schema v2)` are dead at
            # emissions-calculation runtime — they were populated by the
            # one-shot update-scripts that used to live under
            # database/scripts/ (since removed) but never read during any
            # calculation. They are retained for now so that existing
            # .alaqs files and CSV exports remain round-trippable; they
            # will be dropped as part of a future schema-v2 migration.
            # See open_alaqs/database/DEPRECATIONS.md for the full list
            # and rationale.
            #
            # Column order MUST match the schema baked into
            # core/templates/project.alaqs (32 columns); template
            # generation via tools/template_build/generate_templates.py
            # uses this dict to recreate the table from scratch, and
            # downstream CSV imports rely on column order matching the
            # CSV header in open_alaqs/database/data/.
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY"),
                    ("engine_type", "VARCHAR(1)"),
                    ("engine_full_name", "TEXT"),
                    ("engine_name", "TEXT"),
                    ("thrust", "DECIMAL"),
                    ("mode", "VARCHAR(2)"),
                    ("fuel_kg_sec", "DECIMAL"),
                    ("co_ei", "DECIMAL"),
                    ("hc_ei", "DECIMAL"),
                    ("nox_ei", "DECIMAL"),
                    ("sox_ei", "DECIMAL"),
                    ("pm10_ei", "DECIMAL"),
                    ("p1_ei", "DECIMAL"),
                    ("p2_ei", "INTEGER"),
                    ("smoke_number", "DECIMAL"),  # DEPRECATED (schema v2)
                    ("smoke_number_maximum", "DECIMAL"),  # DEPRECATED (schema v2)
                    (
                        "fuel_type",
                        "TEXT",
                    ),  # DEPRECATED (schema v2) — runtime overridden
                    (
                        "manufacturer",
                        "TEXT",
                    ),  # DEPRECATED (schema v2) — pass-through only in Engine table
                    ("source", "TEXT"),
                    ("remark", "TEXT"),  # DEPRECATED (schema v2) — free-text notes
                    ("status", "TEXT"),  # DEPRECATED (schema v2)
                    (
                        "engine_name_type",
                        "TEXT",
                    ),  # DEPRECATED (schema v2) — migration-only
                    (
                        "coolant",
                        "VARCHAR(5)",
                    ),  # DEPRECATED (schema v2) — engine coolant type
                    (
                        "combustion_technology",
                        "TEXT",
                    ),  # DEPRECATED (schema v2) — engine combustion class
                    (
                        "technology_age",
                        "TEXT",
                    ),  # DEPRECATED (schema v2) — engine generation marker
                    ("pm10_nonvol", "DECIMAL"),
                    ("pm10_sul", "DECIMAL"),
                    ("pm10_organic", "DECIMAL"),
                    (
                        "eng_type",
                        "TEXT",
                    ),  # DEPRECATED (schema v2) — duplicates engine_type
                    ("bpr", "DECIMAL"),  # DEPRECATED (schema v2) — bypass ratio
                    (
                        "nvpm_ei",
                        "DECIMAL",
                    ),  # DEPRECATED (schema v2) — superseded by pm10_nonvol
                    ("nvpm_number_ei", "DECIMAL"),
                    # MEEM V1 / nvPM-from-rated-thrust columns. Populated by
                    # post-import data scripts (ICAO EEDB extract); read by
                    # _load_meem_metadata() into EmissionIndex._press_ratio
                    # and _meem_*/_nvpm_*_max_* attributes for the MEEM v2
                    # emission method. Without these columns the calculator
                    # silently falls back to bymode. Declared here so fresh
                    # templates carry them (NULL for unseeded engines) and
                    # migrations recognise them as matching columns rather
                    # than reporting them as 'extras' in the source.
                    ("press_ratio", "DECIMAL"),
                    ("meem_nvpm_m_i_f00_avg", "DECIMAL"),
                    ("meem_nvpm_n_i_f00_avg", "DECIMAL"),
                    ("nvpm_m_max_mgkg", "DECIMAL"),
                    ("nvpm_n_max_nkg", "DECIMAL"),
                ]
            )

        SQLSerializable.__init__(
            self,
            db_path_string,
            self.TABLE_NAME,
            table_columns_type_dict,
            primary_key,
        )

        self._emission_indices = OrderedDict()

        if deserialize and self._db_path:
            self.deserialize()
            self.initEmissionIndices()

    def initEmissionIndices(self) -> None:
        for ei_key, ei_val in self.getEntries().items():
            id_name = (
                ei_val["engine_name"]
                if ei_val["engine_name"]
                else ei_val["engine_full_name"]
            )
            self.addEngineEmissionIndex(id_name, ei_val)
        self._load_meem_metadata()

    def _load_meem_metadata(self) -> None:
        """
        Read MEEM V1 columns from default_aircraft_engine_ei via a separate
        query so the main SQLSerializable SELECT is not broken when these
        columns are absent in older databases.  Silently skipped on any error
        or when the schema predates the MEEM columns.
        """
        import sqlite3

        MEEM_COLS = (
            "press_ratio",
            "meem_nvpm_m_i_f00_avg",
            "nvpm_m_max_mgkg",
            "meem_nvpm_n_i_f00_avg",
            "nvpm_n_max_nkg",
        )
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            # Verify the MEEM columns actually exist before building the SELECT.
            # Without this guard, SQLite's legacy double-quote fallback would
            # reinterpret a missing column name as a string literal and return
            # the string name as the value — a confusing silent degradation.
            existing = {
                r[1]
                for r in conn.execute(
                    "PRAGMA table_info(default_aircraft_engine_ei)"
                ).fetchall()
            }
            present_meem = [c for c in MEEM_COLS if c in existing]
            if not present_meem:
                conn.close()
                return  # Older DB without MEEM schema — run plain bymode.
            cols_sql = ", ".join(f'"{c}"' for c in ("engine_name", *present_meem))
            rows = conn.execute(
                f"SELECT DISTINCT {cols_sql} FROM default_aircraft_engine_ei"
            ).fetchall()
            conn.close()
        except Exception:
            return
        for row in rows:
            uid = row["engine_name"]
            if uid not in self._emission_indices:
                continue
            ei_obj = self._emission_indices[uid]

            def _f(k):
                if k not in present_meem:
                    return None
                v = row[k]
                return float(v) if v is not None else None

            ei_obj._press_ratio = _f("press_ratio")
            ei_obj._meem_m_f00 = _f("meem_nvpm_m_i_f00_avg")
            ei_obj._nvpm_m_max_mgkg = _f("nvpm_m_max_mgkg")
            ei_obj._meem_n_f00 = _f("meem_nvpm_n_i_f00_avg")
            ei_obj._nvpm_n_max_nkg = _f("nvpm_n_max_nkg")

    def addEngineEmissionIndex(self, icaoIdentifier: str, ei_dict: dict) -> None:

        # Create an emission index
        if icaoIdentifier not in self._emission_indices:
            self._emission_indices[icaoIdentifier] = EngineEmissionIndex()

        # Set the values of the emission index
        self._emission_indices[icaoIdentifier].setObject(
            ei_dict.get("mode", "unknown"), ei_dict
        )

    def getEngineEmissionIndices(self):
        return self._emission_indices

    def hasEngineEmissionIndex(self, icaoIdentifier, mode=""):
        if icaoIdentifier in self._emission_indices:
            if mode:
                if mode in self._emission_indices[icaoIdentifier].getModes():
                    return True
            else:
                return True
        return False

    def getEngineEmissionIndex(
        self, icaoIdentifier="", mode="", defaultIfNotFound=False
    ):
        if not icaoIdentifier:
            return self._emission_indices
        if self.hasEngineEmissionIndex(icaoIdentifier):
            if not mode:
                return self._emission_indices[icaoIdentifier]
            else:
                if mode in self._emission_indices[icaoIdentifier].getModes():
                    return self._emission_indices[
                        icaoIdentifier
                    ].getEmissionIndexByMode(mode)

        # ToDo: default
        return None


# if __name__ == "__main__":
#     # create a logger for this module
#     logging.basicConfig(level=logging.DEBUG)
#
#     logger.setLevel(logging.DEBUG)
#     # create console handler and set level to debug
#     ch = logging.StreamHandler()
#     ch.setLevel(logging.DEBUG)
#     # create formatter
#     formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # add formatter to ch
#     ch.setFormatter(formatter)
#     # add ch to logger
#     logger.addHandler(ch)
#
#     # path_to_database = os.path.join("..", "..", "example", "testing_cases.alaqs")
#     path_to_database = os.path.join("..", "..", "example", "CAEPport_training", "caepport_out.alaqs")
#
#     #modes = EngineModeDatabase(path_to_database)
#     #logger.debug(modes.getEntries())
#
#     #start_ef = EngineEmissionFactorsStartDatabase(path_to_database)
#     #logger.debug(start_ef.getEntries())
#
#     ei_db = EngineEmissionIndicesDatabase(path_to_database)
#     # logger.debug("Found %i emission indices" % (len(ei_db.getEngineEmissionIndices())))
#
#     # for entry in ei_db.getEntries():
#     #     if ei_db.getEntries()[entry]["engine_name"] == "1AA003":
#     #         for key in ei_db.getEntries()[entry]:
#     #             print "%s:%s %s" % (str(key), str(ei_db.getEntries()[entry][key]), type(ei_db.getEntries()[entry][key]))
#     #         print "\n"
#     #         logger.info("\n")
#
#     # for entry in modes.getEntries():
#     #    print modes.getEntries()[entry]
