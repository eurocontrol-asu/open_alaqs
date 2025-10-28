from dataclasses import dataclass


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


@dataclass
class Movement:
    gate_type: str
    aircraft_group: str
    gse_type: str
    count: int
    time: float
