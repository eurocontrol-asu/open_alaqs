"""
Create a csv file with COPERT V data containing the Emission Factors (EFs) of roadway vehicles.
"""

from pathlib import Path

import pandas as pd

if __name__ == "__main__":

    # Set the path to the source file and the destination file
    dst_csv = Path(__file__).parents[1] / "data/default_vehicle_ef_copert5.csv"
    dst_euro_standards_csv = (
        Path(__file__).parents[1] / "data/default_vehicle_fleet_euro_standards.csv"
    )
    src_xlsx = Path(__file__).parents[2] / "local/20211111_EFs_Eurocontrol.xlsx"
    src_euro_standards = Path(__file__).parents[1] / "src/euro_standards.csv"
    src_vehicle_age = Path(__file__).parents[1] / "src/vehicle_age.csv"

    # Get the data
    data = pd.read_excel(src_xlsx, sheet_name="EF_All")

    # Change the column names
    data.columns = [
        str(c).lower().replace(" ", "_").replace("/", "-") for c in data.columns
    ]

    # Keep the non-numerical and tens columns
    keep_num_columns = [str(i) for i in range(10, 150, 10)]
    data = data[
        data.columns[
            ~data.columns.str.isnumeric() | (data.columns.isin(keep_num_columns))
        ]
    ]

    # Make sure the all tens columns contain numerical values
    for column in data.columns[data.columns.isin(keep_num_columns)]:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)

    # Store the data
    data.to_csv(dst_csv, index=False)

    # Determine fleet composition

    # Get the Euro standards and their introductory dates (simplified)
    # Source https://www.transportpolicy.net/standard/eu-heavy-duty-emissions/
    # Source https://nl.wikipedia.org/wiki/Europese_emissiestandaard
    euro_standards = pd.read_csv(src_euro_standards)

    # Get the average vehicle age (simplified, passenger car only)
    # source https://www.acea.auto/files/ACEA-report-vehicles-in-use-europe-2022.pdf
    vehicle_age = pd.read_csv(src_vehicle_age)

    # Determine the combinations
    vehicle_categories = data[["vehicle_category", "euro_standard"]].drop_duplicates()
    vehicle_categories = vehicle_categories.merge(
        euro_standards, how="left", on="euro_standard"
    )

    # Set the average fleet years
    fleet_years = range(1990, 2035, 5)

    # Determine the average euro standard for each fleet year - country combinations
    fleet_euro_standards = []
    for fleet_year in fleet_years:
        for _, country_vehicle_age in vehicle_age.iterrows():

            country = country_vehicle_age["country"]
            age = country_vehicle_age["age"]

            # Get the available euro standards for each vehicle category
            vc_available = vehicle_categories[
                vehicle_categories["introduction"] <= fleet_year
            ]

            # Get the applicable euro standards for each vehicle category (corrected for average vehicle age)
            vc_applicable = vc_available[
                vc_available["introduction"] <= (fleet_year - age)
            ]

            # Get the average euro standard for each vehicle category
            vc_average = (
                vc_applicable.sort_values("introduction")
                .groupby("vehicle_category", as_index=False)
                .last()
            )

            # Add country and fleet year
            vc_average["country"] = country
            vc_average["fleet_year"] = fleet_year

            fleet_euro_standards.append(vc_average.drop(columns={"introduction"}))
    fleet_euro_standards_df = pd.concat(fleet_euro_standards)

    # Store the data
    fleet_euro_standards_df.to_csv(dst_euro_standards_csv, index=False)
