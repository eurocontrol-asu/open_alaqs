from pathlib import Path

import pandas as pd

if __name__ == "__main__":

    # Set the path to the source file and the destination file
    dst_csv = Path(__file__).parents[1] / 'data/default_aircraft_profiles.csv'
    src_operations_csv = Path(__file__).parents[1] / 'src/DEMO_Noise_&_Emissions_TEST_1_Operations.csv'
    src_trajectories_csv = Path(__file__).parents[1] / 'src/DEMO_Noise_&_Emissions_TEST_1_Dep_Arr_Trajectories.csv'

    # Read the IMPACT output files
    trj = pd.read_csv(src_trajectories_csv, sep=';')
    ops = pd.read_csv(src_operations_csv, sep=';', index_col='FLIGHT_ID')

    # Create profiles from trajectories
    all_profiles = []
    for (flight_id, type_of_operation), trajectory in trj.groupby(['FLIGHT_ID', 'FLIGHT_PHASE']):

        # Get the operation
        op = ops.loc[flight_id]

        # Set the relevant columns
        profile_columns = [
            'POINT_INDEX',
            'WEIGHT_KG',
            'ANP_POWER_SETTING_1ENG_LB',
            'TAS_KT',
            'LOCAL_DISTANCE_FT',
            'ELEVATION_FT',
        ]

        # Get the relevant columns
        profile = trajectory[profile_columns]

        # Change the columns names
        profile = profile.rename(columns={
            'POINT_INDEX': 'point',
            'WEIGHT_KG': 'weight_kgs',
            'ANP_POWER_SETTING_1ENG_LB': 'power',
            'TAS_KT': 'tas_knots',
            'LOCAL_DISTANCE_FT': 'horizontal_feet',
            'ELEVATION_FT': 'vertical_feet',
        })

        # Add mode
        if type_of_operation == 'ARRIVAL':
            profile['mode'] = 'AP'
        else:

            # Determine the mode based on the cutoff (power cutback)
            delta = trajectory['ANP_POWER_SETTING_1ENG_LB'].diff() / trajectory['TOTAL_DISTANCE_NM'].diff()

            # Get the biggest (scaled) power cutback which is not on the ground
            cutback = delta.loc[(trajectory['ELEVATION_FT'] > 0) & ~delta.isna()].min()

            # Get the location of the cutback
            cutoff = trajectory[(trajectory['ELEVATION_FT'] > 0) & ~delta.isna() & (delta == cutback)]

            # Set the mode
            profile['mode'] = 'TO'
            profile.loc[profile.index >= cutoff.index[0], 'mode'] = 'CL'

        # Add arrival/departure
        profile['arrival_departure'] = type_of_operation[0].upper()

        # Add stage
        profile['stage'] = op['STAGE_LENGTH']

        # Add profile_id
        profile_ids = op[['PROFILE_ID', 'DEP_PROFILE_ID', 'DES_PROFILE_ID']]
        profile_ids = profile_ids[~profile_ids.isna()]
        if "PROFILE_ID" in profile_ids:
            profile_id = profile_ids["PROFILE_ID"]
        else:
            profile_id = profile_ids[f"{'DEP' if type_of_operation == 'DEPARTURE' else 'DES'}_PROFILE_ID"]
        profile['profile_id'] = f'{op["INPUT_ACFT_ID"]}-{profile_id}'

        # Add the profile to the list
        all_profiles.append(profile)

    # Combine the profiles in a single dataframe
    all_profiles = pd.concat(all_profiles)

    # Make necessary unit conversions
    all_profiles['horizontal_metres'] = all_profiles['horizontal_feet'] * .3048
    all_profiles['vertical_metres'] = all_profiles['vertical_feet'] * .3048
    all_profiles['tas_metres'] = all_profiles['tas_knots'] * 1852 / 3600
    all_profiles['weight_lbs'] = all_profiles['weight_kgs'] * 1000 / 453.59237

    # Add course
    all_profiles['course'] = 'IMPACT trajectory'

    # Set the relevant columns
    columns = [
        'profile_id',
        'arrival_departure',
        'stage',
        'point',
        'weight_lbs',
        'horizontal_feet',
        'vertical_feet',
        'tas_knots',
        'weight_kgs',
        'horizontal_metres',
        'vertical_metres',
        'tas_metres',
        'power',
        'mode',
        'course',
    ]

    # Write to data/default_aircraft_profiles.csv
    all_profiles[columns].to_csv(dst_csv, index_label='oid')
