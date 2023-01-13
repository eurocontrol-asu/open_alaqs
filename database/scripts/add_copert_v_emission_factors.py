"""
Create a csv file with COPERT V data containing the Emission Factors (EFs) of roadway vehicles.
"""
from pathlib import Path

import pandas as pd

if __name__ == "__main__":

    # Set the path to the source file and the destination file
    dst_csv = Path(__file__).parents[1] / 'data/default_vehicle_ef_copert5.csv'
    src_xlsx = Path(__file__).parents[2] / 'local/20211111_EFs_Eurocontrol.xlsx'

    # Get the data
    data = pd.read_excel(src_xlsx, sheet_name='EF_All')

    # Change the column names
    data.columns = [str(c).lower().replace(' ', '_').replace('/', '-') for c in data.columns]

    # Store the data
    data.to_csv(dst_csv, index=False)
