# -> General constants
DATA_PATH = "../../db_updates/data"


# -> Update default aircraft table
FILE_MOST_FREQUENT_ENGINES = "most_freq_eng_per_aircraft_type.csv"
FILE_EMISSIONS = "EEA_AEM_Acft_Mapping_Eng_LTO_Indices_2022_02-05-2022_v4.xlsx"
FILE_MTOW_INFORMATION = "new_aircraft_mtow.xlsx"
TAB_AIRCRAFT_TO_ENGINE = "ACT_PRF.aircraft_engine.txt"
TAB_MANUFACTURER_INFO = "ICAO Doc 8643 - 04042022"
TAB_ENGINES_ID_LIST = "ENGINES_ID_LIST"


# -> Update default aircraft engine table
FILE_ICAO_EEDB = "edb-emissions-databank_v28c_web.xlsx"
TAB_GAS_EMISSIONS = "Gaseous Emissions and Smoke"
TAB_NVPM_EMISSIONS = "nvPM Emissions"

# Constants for PM_SUL_EI calculation
# Constants values taken from ICAO DOC 9889, Attachment D to Appendix 1
MW_OUT = 96
MW_SULPHUR = 32
FSC =  0.068
EPSILON = 2.4

# Constants for PM_Volatile calculation
# Constants values taken from ICAO DOC 9889, Attachment D to Appendix 1
REFERENCE_RATIO_PM_VOLATILE = {
    "T/O": 115,
    "C/O": 76,
    "App": 56.25,
    "Idle": 6.17
}


# -> uPDATE DEFAULT AIRCRAFT ENGINE TABLE (adding nvPM)
# Source: Table D-1: Suggested SF values to predict missing SN in the ICAO EEDB, page 88
SCALING_FACTORS = {
    "non_dac": {"TX": 0.3, "TO": 1.0, "CL": 0.9, "AP": 0.3},
    "aviadvigatel": {"TX": 0.3, "TO": 1.0, "CL": 1.0, "AP": 0.8},
    "ge_cf34": {"TX": 0.3, "TO": 1.0, "CL": 0.4, "AP": 0.3},
    "textron_lycoming": {"TX": 0.3, "TO": 1.0, "CL": 1.0, "AP": 0.6},
    "cfm_dac": {"TX": 1.0, "TO": 0.3, "CL": 0.3, "AP": 0.3},
}

# Source: Table D-2. Representative AFRk listed by ICAO power settings (mode k), page 89
AIR_FUEL_RATIO = {"TX": 106, "TO": 45, "CL": 51, "AP": 83}

# Source: Table D-4. Standard values for GMDk listed by ICAO thrust settings (mode k), page 91
GEOMTRIC_MEAN_DIAMETERS = {"TX": 20, "TO": 40, "CL": 40, "AP": 20}

NR = 10**24
STANDARD_DEVIATION_PM = 1.8
PARTICLE_EFFECTIVE_DENSITY = 1000
