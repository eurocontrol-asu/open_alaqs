from typing import Tuple
from pathlib import Path
import sys
import shutil

from update_default_aircraft import update_default_aircraft
from update_emissions_based_on_eedb import update_emissions_based_on_eedb

import constants as c


def get_values_from_command_line() -> Tuple[str, str]:
    """_summary_

    Raises:
        Exception: _description_

    Returns:
        Tuple[str, str, str]: _description_
    """

    args = sys.argv

    if len(args) != 3:
        raise Exception(
            "Wrong number of arguments. Expected call: python " \
                "main_update.py <old_blank_alaqs_study_name> <new_blank_alaqs_study_name>"
        )

    old_database = args[1]
    new_database = args[2]

    # Data files folder
    file_path = Path(__file__).parent

    if not (file_path / (old_database + ".alaqs")).exists():
        raise Exception(f"The input file that you try to use does not exist.\n{old_database}")

    if (file_path / (new_database + ".alaqs")).exists():
        raise Exception(f"The output file already exists.\n{new_database}")

    # Copy the file
    shutil.copy(
        str(file_path / (old_database + ".alaqs")),
        str(file_path / (new_database + ".alaqs"))
    )

    return old_database, new_database


if __name__ == '__main__':

    # Get values from the command line for the old database and new database links
    old_database, new_database = get_values_from_command_line()

    # Update default aircraft table
    update_default_aircraft(old_database, new_database)

    # Update default engine emissions EI table, based on ICAO EEDB. Includes the creation of nvPM
    # columns
    update_emissions_based_on_eedb(old_database, new_database)
