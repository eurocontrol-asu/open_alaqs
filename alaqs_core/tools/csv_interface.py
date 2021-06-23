import csv
import os

import geopandas as gpd
import pandas as pd
from shapely.wkt import loads

from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


def write_csv(path, rows):
    path_to_file = path
    logger.debug("writing results to %s" % path_to_file)
    try:
        rows_df = pd.DataFrame(rows[1:], columns=rows[0])
        rows_df.to_csv(path_to_file, index=False, sep=',', quotechar='"',
                       quoting=csv.QUOTE_NONNUMERIC, line_terminator='\n')

    except Exception as exc:
        logger.error("Couldn't write to CSV file: '%s'" % path_to_file)
        logger.error(exc)


def read_csv(path):
    path_to_file = path  # [0]
    if os.path.isfile(path_to_file):
        input_ = []
        with open(path_to_file, 'r') as csvfile:
            csv_reader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in csv_reader:
                input_.append(row)
        return input_
    logger.error("Couldn't read CSV file: '%s'" % path_to_file)


# Read CSV file as a dictionary containing lists
def read_csv_to_dict(path):
    path_to_file = path  # [0]
    input_dict = {}

    if os.path.isfile(path_to_file):
        input_ = read_csv(path_to_file)
        # first row is header
        if not input_:
            for index_column, head_column in enumerate(input_[0]):
                if head_column not in input_dict:
                    input_dict[head_column] = []
                    for index_row, row in enumerate(input_[1:]):
                        value = row[index_column]
                        if value is None:
                            logger.error(f"Could not find column with name "
                                         f"'{head_column}' in CSV file at path "
                                         f"'{path}' for row with index "
                                         f"'{index_row + 1}'.")
                        input_dict[head_column].append(value)
                else:
                    logger.error(
                        "Header '%s' of CSV file at path '%s' is expected in "
                        "the first row, but the columns do not have a unique "
                        "name. Cannot parse this csv file." % (
                            head_column, path))
                    return {}
        else:
            logger.error("CSV file at path '%s' is empty." % path_to_file)
        return input_dict
    logger.error("Couldn't read CSV file: '%s'" % path_to_file)
    return input_dict


def read_csv_to_geodataframe(path):
    path_to_file = path  # [0]
    logger.debug("Reading %s" % path_to_file)
    if os.path.isfile(path_to_file):
        csv_df = pd.read_csv(path_to_file)
    else:
        logger.error("Couldn't read CSV file: '%s'" % path_to_file)
        csv_df = pd.DataFrame()

    gdf = gpd.GeoDataFrame()

    try:
        if "geometry" in csv_df.keys():
            # either all at once : ( coordinates in WKT format )
            # # df['geometry'] = df['geometry'].apply(loads)
            # or one by one to detect possible geometry errors

            for index, row in csv_df.iterrows():
                try:
                    # it will throw an error where the geometry WKT isn't valid
                    csv_df.loc[index, 'geometry'] = loads(row['geometry'])
                except Exception:
                    logger.error("geometry WKT isn't valid (%s)" % row)
                    continue
            if not csv_df.empty:
                gdf = gpd.GeoDataFrame(csv_df)
        else:
            if ("longitude" in csv_df.keys()) and \
                    ("latitude" in csv_df.keys()) and \
                    ("altitude" in csv_df.keys()):
                gdf = gpd.GeoDataFrame(csv_df, geometry=gpd.points_from_xy(
                    csv_df.longitude, csv_df.latitude, csv_df.altitude))
            else:
                logger.error("Couldn't find 'geometry' column in DataFrame")

    except Exception as exc_:
        logger.error("Cannot convert to GeoDataFrame (%s)" % exc_)

    return gdf
