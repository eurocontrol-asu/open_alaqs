# database.py

import os
import pandas as pd
import sqlite3
from typing import List, Literal, Any
from dataclasses import dataclass, asdict

# --- DATA MODELS ---

@dataclass
class GSE:
    type: str
    description: str
    power: float
    load: float
    fuel: str
    Stage: str
    time: float
    deterioration_factor: float

    @staticmethod
    def from_dict(d: dict):
        try:
            obj = GSE(
                type=str(d.get('type', '')),
                description=str(d.get('description', '')),
                power=float(d.get('power', 0)),
                load=float(d.get('load', 0)),
                fuel=str(d.get('fuel', '')),
                Stage=str(d.get('Stage', '')),
                time=float(d.get('time', 0)),
                deterioration_factor=float(d.get('deterioration_factor', 1)),
            )
            # Simple checks (customize as needed)
            if obj.power < 0:
                raise ValueError("power must be >= 0")
            if obj.load < 0:
                raise ValueError("load must be >= 0")
            if obj.time < 0:
                raise ValueError("time must be >= 0")
            if obj.deterioration_factor < 0:
                raise ValueError("deterioration_factor must be >= 0")
            return obj
        except Exception as e:
            raise ValueError(f"Invalid GSE: {e}")

@dataclass
class EmissionFactor:
    stage: str
    category: str
    power_range: str
    valid_as_of: str
    CO_g_per_kWh: float
    HC_g_per_kWh: float
    NOx_g_per_kWh: float
    PM_g_per_kWh: float
    SOx_g_per_kWh: float

    @staticmethod
    def from_dict(d: dict):
        try:
            obj = EmissionFactor(
                stage=str(d.get('stage', '')),
                category=str(d.get('category', '')),
                power_range=str(d.get('power_range', '')),
                valid_as_of=str(d.get('valid_as_of', '')),
                CO_g_per_kWh=float(d.get('CO_g_per_kWh', 0)),
                HC_g_per_kWh=float(d.get('HC_g_per_kWh', 0)),
                NOx_g_per_kWh=float(d.get('NOx_g_per_kWh', 0)),
                PM_g_per_kWh=float(d.get('PM_g_per_kWh', 0)),
                SOx_g_per_kWh=float(d.get('SOx_g_per_kWh', 0)),
            )
            # Optionally, add validation here
            return obj
        except Exception as e:
            raise ValueError(f"Invalid EmissionFactor: {e}")


@dataclass
class Movement:
    id: int
    ac_group: str
    gate_type: str
    gse_id: int
    time_min: float
    count: int
    op_type: str  # "A" or "D"

    @staticmethod
    def from_dict(d: dict):
        try:
            obj = Movement(
                id=int(d.get('id', 0)),
                ac_group=str(d.get('ac_group', '')),
                gate_type=str(d.get('gate_type', '')),
                gse_id=int(d.get('gse_id', 0)),
                time_min=float(d.get('time_min', 0)),
                count=int(d.get('count', 1)),
                op_type=str(d.get('op_type', '')).upper(),
            )
            if obj.time_min < 0:
                raise ValueError("time_min must be >= 0")
            if obj.count < 1:
                raise ValueError("count must be >= 1")
            if obj.op_type not in ("A", "D"):
                raise ValueError("op_type must be 'A' or 'D'")
            return obj
        except Exception as e:
            raise ValueError(f"Invalid Movement: {e}")

@dataclass
class EmissionResult:
    ac_group: str
    gate_type: str
    gse_type: str
    A_min: float
    D_min: float
    CO_g_per_h: float
    HC_g_per_h: float
    NOx_g_per_h: float
    PM_g_per_h: float
    SOx_g_per_h: float
    kWh: float

    @staticmethod
    def from_dict(d: dict):
        try: 
            obj = EmissionResult(
                ac_group=str(d.get('ac_group', '')),
                gate_type=str(d.get('gate_type', '')),
                gse_type=str(d.get('gse_type', '')),
                A_min=float(d.get('A_min', 0)),
                D_min=float(d.get('D_min', 0)),
                CO_g_per_h=float(d.get('CO_g_per_h', 0)),
                HC_g_per_h=float(d.get('HC_g_per_h', 0)),
                NOx_g_per_h=float(d.get('NOx_g_per_h', 0)),
                PM_g_per_h=float(d.get('PM_g_per_h', 0)),
                SOx_g_per_h=float(d.get('SOx_g_per_h', 0)),
                kWh=float(d.get('kWh', 0)),
            )

            if obj.A_min == 0 and obj.D_min == 0:
                raise ValueError("arrival or departure time has to be non zero")
            
        except Exception as e:
            raise ValueError(f"Invalid Emissions Computed: {e}")
    
# --- DATABASE LOADER AND SAVER ---

class GSEDatabase:
    def __init__(self, source: str, backend: Literal['csv', 'sqlite'] = 'csv'):
        self.source = source  # path to one of the data files
        self.backend = backend.lower()
        self.gse: List[GSE] = []
        self.emission_factors: List[EmissionFactor] = []
        self.movements: List[Movement] = []
        self.emission_results: List[EmissionResult] = []

    def open(self):
        if self.backend == 'csv':
            self._load_from_csv()
        elif self.backend == 'sqlite':
            self._load_from_sqlite()
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

    def _load_from_csv(self):
        # Assume self.source is a path to any of the CSVs, get the containing folder
        db_dir = os.path.dirname(self.source)
        gse_path = os.path.join(db_dir, "default_gse.csv")
        ef_path = os.path.join(db_dir, "default_emission_factors.csv")
        move_path = os.path.join(db_dir, "movements.csv")

        self.gse = self._load_validated_csv(gse_path, GSE)
        self.emission_factors = self._load_validated_csv(ef_path, EmissionFactor)
        self.movements = []
        if os.path.exists(move_path):
            self.movements = self._load_validated_csv(move_path, Movement)

    def _load_validated_csv(self, path: str, model: Any) -> List[Any]:
        try:
            df = pd.read_csv(path)
        except Exception as e:
            raise RuntimeError(f"Failed to read {path}: {e}")

        records = []
        errors = []
        for idx, row in df.iterrows():
            try:
                rec = model.from_dict(row.to_dict())
                records.append(rec)
            except Exception as ve:
                errors.append(f"Row {idx}: {ve}")

        if errors:
            raise RuntimeError(f"Validation errors in {os.path.basename(path)}:\n" + "\n".join(errors))
        return records

    def _load_from_sqlite(self):
        if not os.path.exists(self.source):
            raise FileNotFoundError(f"SQLite file {self.source} does not exist")
        conn = sqlite3.connect(self.source)
        try:
            gse_df = pd.read_sql("SELECT * FROM gse", conn)
            self.gse = [GSE.from_dict(row) for row in gse_df.to_dict("records")]
            ef_df = pd.read_sql("SELECT * FROM emission_factors", conn)
            self.emission_factors = [EmissionFactor.from_dict(row) for row in ef_df.to_dict("records")]
            try:
                move_df = pd.read_sql("SELECT * FROM movements", conn)
                self.movements = [Movement.from_dict(row) for row in move_df.to_dict("records")]
            except Exception:
                self.movements = []
        except Exception as e:
            raise RuntimeError(f"Failed to load from sqlite: {e}")
        finally:
            conn.close()

    def save(self):
        if self.backend == 'csv':
            self._save_to_csv()
        elif self.backend == 'sqlite':
            self._save_to_sqlite()
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

    def _save_to_csv(self):
        db_dir = os.path.dirname(self.source)
        pd.DataFrame([asdict(x) for x in self.gse]).to_csv(os.path.join(db_dir, "default_gse.csv"), index=False)
        pd.DataFrame([asdict(x) for x in self.emission_factors]).to_csv(os.path.join(db_dir, "default_emission_factors.csv"), index=False)
        if self.movements:
            pd.DataFrame([asdict(x) for x in self.movements]).to_csv(os.path.join(db_dir, "movements.csv"), index=False)

    def _save_to_sqlite(self):
        conn = sqlite3.connect(self.source)
        try:
            pd.DataFrame([asdict(x) for x in self.gse]).to_sql("gse", conn, if_exists="replace", index=False)
            pd.DataFrame([asdict(x) for x in self.emission_factors]).to_sql("emission_factors", conn, if_exists="replace", index=False)
            if self.movements:
                pd.DataFrame([asdict(x) for x in self.movements]).to_sql("movements", conn, if_exists="replace", index=False)
        finally:
            conn.close()

# --- Example usage ---

if __name__ == "__main__":
    # Example: CSV usage
    db = GSEDatabase("../model/database/default_gse.csv", backend='csv')
    try:
        db.open()
        print("GSE loaded:", db.gse[:2])
        print("Emission Factors loaded:", db.emission_factors[:2])
        print("Movements loaded:", db.movements[:2])
        print("Emission Results:", db.emission_results[:2])
    except Exception as e:
        print("Error:", e)
