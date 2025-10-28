# model/storage.py

from typing import List

import pandas as pd

from .gse_types import GSE, EmissionFactor, Movement


def load_gse_csv(path: str) -> List[GSE]:
    df = pd.read_csv(path)
    return [GSE(**row) for row in df.to_dict("records")]


def save_gse_csv(gse_list: List[GSE], path: str):
    df = pd.DataFrame([gse.__dict__ for gse in gse_list])
    df.to_csv(path, index=False)


def load_emission_factors_csv(path: str) -> List[EmissionFactor]:
    df = pd.read_csv(path)
    return [EmissionFactor(**row) for row in df.to_dict("records")]


def save_emission_factors_csv(factors: List[EmissionFactor], path: str):
    df = pd.DataFrame([f.__dict__ for f in factors])
    df.to_csv(path, index=False)


def load_movements_csv(path: str) -> List[Movement]:
    df = pd.read_csv(path)
    return [Movement(**row) for row in df.to_dict("records")]


def save_movements_csv(movements: List[Movement], path: str):
    df = pd.DataFrame([m.__dict__ for m in movements])
    df.to_csv(path, index=False)
