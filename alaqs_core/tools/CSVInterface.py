import csv
import os

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads

from open_alaqs.alaqs_core import alaqslogging

logger = alaqslogging.logging.getLogger(__name__)
logger.setLevel('DEBUG')
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def writeCSV(path, rows):
    path_to_file = path  # [0]
    logger.debug("writing results to %s" % path_to_file)
    # t0 = time.time()
    try:
        rows_df = pd.DataFrame(rows[1:], columns=rows[0])
        rows_df.to_csv(path_to_file, index=False, sep=',', quotechar='"',
                       quoting=csv.QUOTE_NONNUMERIC, line_terminator='\n')

    except Exception as exc:
        logger.error("Couldn't write to CSV file: '%s'" % (path_to_file))
        logger.error(exc)
    # logger.debug("pandas --- %s seconds ---" % (time.time() - t0))

    # try:
    # # if os.path.isfile(path_to_file):
    #     with open(path_to_file, 'w') as csvfile:
    #         csv_writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONNUMERIC, lineterminator='\n')
    #         for row in rows:
    #             row_ = [round(var, 5) if isinstance(var, (int, long, float)) else var for var in row]
    #             csv_writer.writerow(row_)
    #
    # except Exception as exc:
    #     logger.error("Couldn't write to CSV file: '%s'" % (path_to_file))
    #     logger.error(exc)
    # logger.debug("csv_writer --- %s seconds ---" % (time.time() - t0))


def readCSV(path):
    path_to_file = path  # [0]
    if os.path.isfile(path_to_file):
        input_ = []
        with open(path_to_file, 'r') as csvfile:
            csv_reader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in csv_reader:
                input_.append(row)
        return input_
    else:
        logger.error("Couldn't read CSV file: '%s'" % (path_to_file))


# Read CSV file as a dictionary containing lists
def readCSVtoDict(path):
    path_to_file = path  # [0]
    input_dict = {}

    if os.path.isfile(path_to_file):
        input_ = readCSV(path_to_file)
        # first row is header
        if len(input_):
            for index_column, head_column in enumerate(input_[0]):
                if not head_column in input_dict:
                    input_dict[head_column] = []
                    for index_row, row in enumerate(input_[1:]):
                        value = row[index_column]
                        if value is None:
                            logger.error(
                                "Could not find column with name '%s' in CSV file at path '%s' for row with index '%i'." % (
                                head_column, path, index_row + 1))
                        input_dict[head_column].append(value)
                else:
                    logger.error(
                        "Header '%s' of CSV file at path '%s' is expected in the first row, but the columns do not have a unique name. Cannot parse this csv file." % (
                        head_column, path))
                    return {}
        else:
            logger.error("CSV file at path '%s' is empty." % (path_to_file))
        return input_dict
    else:
        logger.error("Couldn't read CSV file: '%s'" % (path_to_file))
        return input_dict


def readCSVtoGeoDataFrame(path):
    path_to_file = path  # [0]
    logger.debug("Reading %s" % path_to_file)
    if os.path.isfile(path_to_file):
        csv_df = pd.read_csv(path_to_file)
    else:
        logger.error("Couldn't read CSV file: '%s'" % (path_to_file))
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
                except:
                    logger.error("geometry WKT isn't valid (%s)" % row)
                    continue
                    # csv_df.loc[index, 'geometry'] = loads("GEOMETRYCOLLECTION EMPTY")
            if not csv_df.empty:
                gdf = gpd.GeoDataFrame(csv_df)
        else:
            if "longitude" in csv_df.keys() and "latitude" and "altitude" in csv_df.keys():
                gdf = gpd.GeoDataFrame(csv_df, geometry=gpd.points_from_xy(
                    csv_df.longitude, csv_df.latitude, csv_df.altitude))
            else:
                logger.error("Couldn't find 'geometry' column in DataFrame")

    except Exception as exc_:
        logger.error("Cannot convert to GeoDataFrame (%s)" % exc_)

    return gdf
