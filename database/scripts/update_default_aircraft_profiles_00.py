import zipfile
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).parents[1] / 'data/'
SRC_PATH = Path(__file__).parents[1] / 'src/'
SRC_FILE = Path(__file__).parents[1] / 'src/DEMO_Noise_&_Emissions_Operations.zip'

if __name__ == "__main__":
    """
    Create the input files for IMPACT
    """

    # Get the aircraft
    # aircraft_data = pd.read_csv(SRC_PATH / 'ANP2.3_Aircraft.csv', sep=';')
    aircraft_data = pd.read_csv(DATA_PATH / 'default_aircraft.csv')

    # Remove nan
    aircraft_data = aircraft_data[~aircraft_data['ac_group'].isna()]

    # Remove helicopters
    aircraft_data = aircraft_data[~aircraft_data['ac_group'].str.contains('HELI')]

    # Remove supersonic
    aircraft_data = aircraft_data[~aircraft_data['ac_group'].str.contains('SUPERSONIC')]

    # Keep PISTON C170
    aircraft_data = aircraft_data[
        (aircraft_data['ac_group'].str.contains('PISTON') & aircraft_data['icao'].isin(['C170'])) |
        ~aircraft_data['ac_group'].str.contains('PISTON')
        ]

    # Keep listed items
    aircraft_data = aircraft_data[aircraft_data['icao'].isin([
        'C170',  # PISTON
        'DH60',  # PROPELLER
        'C500',
        'C510',
        'S601',
        'MU3001',
        'MD9028',
        'MD83',
        'MD82',
        'MD81',
        'B736',
        'B772',
        'B773',
        'B77L',
        'B77W',
        'A342',
        'A343',
        'A345',
        'A346',
        # 'A359',
        'A225',
        'FA20',
        'E190',
        'F100',
        'B722'
    ])]

    # Get the acft_ids
    # acft_ids = aircraft_data['ACFT_ID'].unique().tolist()
    acft_ids = aircraft_data['icao'].unique().tolist()
    # acft_ids = aircraft_data['departure_profile'].str.rsplit('-', 2, expand=True)[0].unique()

    # Set the profiles (op_type, profile_id, stage_length)
    profiles = [
        ('A', 'DEFAULT', 1),
        ('D', 'DEFAULT', 1),
        # ('D', 'DEFAULT', 2),
    ]

    # Set the constants
    constants = {
        'APT_ID': 'VIRT',
        'RWY_ID': '09L',
        'SUB_TRK_ID': 0,
        'NUM_OPS_DAY': 1,
        'NUM_OPS_EVE': 0,
        'NUM_OPS_NIGHT': 0
    }

    traffic_rows = []
    for acft_id in acft_ids:
        for (op_type, profile_id, stage_length) in profiles:
            if (acft_id in ('C170', 'C500', 'C510', 'FA20')) and (stage_length > 1):
                continue
            else:
                traffic_row = {
                    # 'ACFT_ID': acft_id,
                    'ICAO_CODE': acft_id,
                    'OP_TYPE': op_type,
                    'PROFILE_ID': profile_id,
                    'STAGE_LENGTH': stage_length
                }

                if op_type == 'A':
                    traffic_row['TRK_ID'] = 'APPROACH_P'
                else:
                    traffic_row['TRK_ID'] = 'DEPARTURE_P'

                traffic_row.update(constants)
                traffic_rows.append(traffic_row)
    traffic = pd.DataFrame(traffic_rows)

    # Add a unique flight id
    traffic['FLIGHT_ID'] = 'FLIGHT_' + (traffic.index + 1).astype(str)

    with zipfile.ZipFile(SRC_FILE, 'w') as zipped_f:
        zipped_f.writestr('operations.csv', 'OPERATIONS\n' + traffic.to_csv(index=False, sep=';'))

    pass
