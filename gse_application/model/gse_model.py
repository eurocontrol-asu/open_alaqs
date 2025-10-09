import logging
import pandas as pd
from typing import List
from .gse_types import GroundSupportEquipment, EmissionFactor

logger = logging.getLogger(__name__)

class GSEModel:
    def __init__(self, gse_csv: str, factors_csv: str):
        self.gse_csv = gse_csv
        self.factors_csv = factors_csv

    def get_gse_list(self) -> List[GroundSupportEquipment]:
        try:
            df = pd.read_csv(self.gse_csv)
            return [GroundSupportEquipment(**row) for row in df.to_dict("records")]
        except Exception as e:
            logger.error(f"Failed to load GSE data: {e}")
            return []

    def get_emission_factors(self) -> List[EmissionFactor]:
        try:
            df = pd.read_csv(self.factors_csv)
            return [EmissionFactor(**row) for row in df.to_dict("records")]
        except Exception as e:
            logger.error(f"Failed to load EmissionFactors: {e}")
            return []
