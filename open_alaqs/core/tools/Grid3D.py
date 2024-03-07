from collections import OrderedDict
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools import conversion, sql_interface
from open_alaqs.core.tools.SizeLimitedDict import SizeLimitedDict

logger = get_logger(__name__)


class Grid3D:
    """
    Class that contains the grid definition (number of cells in x,y,z
    dimensions, the resolution, and the reference (middle) x, y coordinates)
    and provides helper methods to work with the grid
    """

    def __init__(
        self,
        db_path: str = "",
        grid_config: dict = None,
        deserialize: bool = True,
    ):
        if grid_config is None:
            grid_config = {}

        self._db_path = db_path

        # Definition of the grid
        # number of cells in x,y,z dimensions
        self._x_cells = grid_config.get("x_cells", 1)
        self._y_cells = grid_config.get("y_cells", 1)
        self._z_cells = grid_config.get("z_cells", 1)

        # resolution of each cells in x,y,z dimensions
        self._x_resolution = grid_config.get("x_resolution", 1)
        self._y_resolution = grid_config.get("y_resolution", 1)
        self._z_resolution = grid_config.get("z_resolution", 1)

        # center of the grid
        self._reference_latitude = conversion.convertToFloat(
            grid_config.get("reference_latitude", 0.0)
        )
        self._reference_longitude = conversion.convertToFloat(
            grid_config.get("reference_longitude", 0.0)
        )
        self._reference_altitude = conversion.convertToFloat(
            grid_config.get("reference_altitude", 0.0)
        )

        if self._db_path and deserialize:
            self.deserialize()

        logger.info("3D Grid Definition:")
        logger.info("\t Number of cells in x-direction: %i", self._x_cells)
        logger.info("\t Number of cells in y-direction: %i", self._y_cells)
        logger.info("\t Number of cells in z-direction: %i", self._z_cells)
        logger.info("\t Resolution in x-direction: %i", self._x_resolution)
        logger.info("\t Resolution in y-direction: %i", self._y_resolution)
        logger.info("\t Resolution in z-direction: %i", self._x_resolution)
        logger.info(
            "\t Reference latitude (center of grid): %.5f", self._reference_latitude
        )
        logger.info(
            "\t Reference longitude (center of grid): %.5f", self._reference_longitude
        )
        logger.info(
            "\t Reference altitude (center of grid): %.5f", self._reference_altitude
        )

        # calculate the grid origin from reference coordinates, which is the
        # bottom left
        self._grid_origin_x = 0.0
        self._grid_origin_y = 0.0
        self._grid_origin_z = 0.0
        self._grid_origin_x, self._grid_origin_y = self._calculate_origin_xy()

        self._elements = OrderedDict()

        # Restrict this list to a certain length, can give memory buffer
        # overflow otherwise
        self._hash_coordinates_map = SizeLimitedDict(size=1000)

    def getResolutionX(self) -> float:
        return self._x_resolution

    def getResolutionY(self) -> float:
        return self._y_resolution

    def getResolutionZ(self) -> float:
        return self._z_resolution

    def getAirportAltitude(self):
        return self._reference_altitude

    def getSortedElements(self):
        return OrderedDict(sorted(list(self._elements.items()), key=lambda t: t[0]))

    def deserialize(self):
        query = """
            SELECT
                table_name_cell_coordinates,
                x_cells,
                y_cells,
                z_cells,
                x_resolution,
                y_resolution,
                z_resolution,
                reference_latitude,
                reference_longitude
            FROM "grid_3d_definition"
        """

        result = sql_interface.execute_sql(self._db_path, query)

        result = sql_interface.query_text(self._db_path, query)

        self._x_cells = result["x_cells"]
        self._y_cells = result["y_cells"]
        self._z_cells = result["z_cells"]

        self._x_resolution = result["x_resolution"]
        self._y_resolution = result["y_resolution"]
        self._z_resolution = result["z_resolution"]

        self._reference_latitude = result["reference_latitude"]
        self._reference_longitude = result["reference_longitude"]

        logger.info("Deserialized Grid3D definition from db '%s' ", self._db_path)

    def _calculate_origin_xy(self) -> tuple[float, float]:
        """
        Calculates the origin of the grid to the bottom-left corner.
        "Reference" coordinates need to be related to the center of the grid.
        """
        point_wkt = "POINT ({} {})".format(
            self._reference_longitude,
            self._reference_latitude,
        )
        sql = """
            SELECT
                X(
                    ST_Transform(
                        ST_PointFromText(?, 4326),
                        3857
                    )
                ) AS y,
                Y(
                    ST_Transform(
                        ST_PointFromText(?, 4326),
                        3857
                    )
                ) AS x
        """
        row = sql_interface.execute_sql(self._db_path, sql, [point_wkt, point_wkt])

        # Calculate the coordinates of the bottom left of the grid
        origin_x = row["x"] - (self._x_cells / 2.0) * self._x_resolution
        origin_y = row["y"] - (self._y_cells / 2.0) * self._y_resolution

        return origin_x, origin_y

    def _polygonise_2Dcells(df_row):
        return Polygon(
            [
                (df_row.xmin, df_row.ymin),
                (df_row.xmax, df_row.ymin),
                (df_row.xmax, df_row.ymax),
                (df_row.xmin, df_row.ymax),
            ]
        )

    def get_df_from_2d_grid_cells(self):
        grid_cells_df = pd.DataFrame(
            list(self.get_3d_grid_cells()),
            columns=["hash", "xmin", "xmax", "ymin", "ymax", "zmin", "zmax"],
        )
        grid_cells_2d = grid_cells_df[grid_cells_df.zmin == 0].reset_index(drop=True)
        polys = grid_cells_2d.apply(self._polygonise_2Dcells, axis=1)
        gdf = gpd.GeoDataFrame(grid_cells_2d, columns=["hash", "geometry"])
        gdf.loc[:, "geometry"] = polys
        return gdf

    def get_df_from_3d_grid_cells(self):
        grid_cells_df = pd.DataFrame(
            list(self.get_3d_grid_cells()),
            columns=["hash", "xmin", "xmax", "ymin", "ymax", "zmin", "zmax"],
        )
        polys = grid_cells_df.apply(self._polygonise_2Dcells, axis=1)
        gdf = gpd.GeoDataFrame(
            grid_cells_df, columns=["hash", "geometry", "zmin", "zmax"]
        )
        gdf.loc[:, "geometry"] = polys
        return gdf

    def get_3d_grid_cells(self) -> list[list[Any]]:
        """
        This function builds a table that contains the locations of every cell that make up the user defined 3D grid. The
        result is a list of cells, each with a unique ID and the coordinates of the minimum and maximum x, y, and z
        positions defined in meters according to the EPSG 3857 projection.
        """
        # Calculate the planar and ellipsoidal coordinates of every cell
        cell_coordinates = []
        for x_idx in range(self._x_cells):
            for y_idx in range(self._y_cells):
                for z_idx in range(self._z_cells):
                    cell = self.convertXYZIndicesToGridCellMinMax(x_idx, y_idx, z_idx)
                    cell_coordinates.append(
                        [
                            self.convertXYZIndicesToCellHash(x_idx, y_idx, z_idx),
                            cell["x_min"],
                            cell["x_max"],
                            cell["y_min"],
                            cell["y_max"],
                            cell["z_min"],
                            cell["z_max"],
                        ]
                    )
        return cell_coordinates

    def serialize(self, database_path: str) -> bool:
        """
        Create a new table to hold the definition of the Grid3D Object

        :param database_path: the path to the database being written to
        :return: bool
        """

        try:
            logger.debug("Droping the existing 3D grid definition table...")

            sql_interface.perform_sql(
                database_path,
                """
                    DROP TABLE IF EXISTS "grid_3d_definition"
                """,
            )

            logger.debug("Creating a new 3D grid definition table...")

            sql_interface.perform_sql(
                database_path,
                """
                    CREATE TABLE "grid_3d_definition"
                    (
                        "table_name_cell_coordinates" VARCHAR,
                        "x_cells" DECIMAL,
                        "y_cells" DECIMAL,
                        "z_cells" DECIMAL,
                        "x_resolution" DECIMAL,
                        "y_resolution" DECIMAL,
                        "z_resolution" DECIMAL,
                        "reference_latitude" DECIMAL,
                        "reference_longitude" DECIMAL
                    )
                """,
            )

            logger.debug("Populating the newly created 3D grid definition table...")

            sql_interface.insert_into_table(
                database_path,
                "grid_3d_definition",
                {
                    "table_name_cell_coordinates": "grid_3d_cell_coordinates",
                    "x_cells": self._x_cells,
                    "y_cells": self._y_cells,
                    "z_cells": self._z_cells,
                    "x_resolution": self._x_resolution,
                    "y_resolution": self._y_resolution,
                    "z_resolution": self._z_resolution,
                    "reference_latitude": self._reference_latitude,
                    "reference_longitude": self._reference_longitude,
                },
            )

        except Exception as error:
            logger.error(
                f"Error while recreating and populating the 3D grid definition table: {error}",
                exc_info=error,
            )

            return False

        return True

    def convertXYZIndicesToGridCellMinMax(self, x_idx, y_idx, z_idx):
        val = {
            "x_min": self._grid_origin_x + (x_idx * self._x_resolution),
            "y_min": self._grid_origin_y + (y_idx * self._y_resolution),
            "z_min": self._grid_origin_z + z_idx * self._z_resolution,
        }
        val.update(
            {
                "x_max": val["x_min"] + self._x_resolution,
                "y_max": val["y_min"] + self._y_resolution,
                "z_max": val["z_min"] + self._z_resolution,
            }
        )
        return val

    def convertCellHashListToCenterGridCellCoordinates(self, cellhash_list):
        val = {}

        for _hash in cellhash_list:
            if _hash not in val:
                if _hash not in self._hash_coordinates_map:
                    (x_idx, y_idx, z_idx) = self.convertCellHashToXYZIndices(_hash)
                    cell = self.convertXYZIndicesToGridCellMinMax(x_idx, y_idx, z_idx)

                    if not (
                        "x_min" in cell
                        and "x_max" in cell
                        and "y_min" in cell
                        and "y_max" in cell
                        and "z_min" in cell
                        and "z_max" in cell
                    ):
                        logger.error(
                            "Could not convert cell hash '%s' because either x_min, x_max, y_min, y_max, z_min, or z_max was not found.",
                            str(_hash),
                        )
                        logger.error(
                            "Output of '%s' was '%s'.",
                            "self.convertXYZIndicesToGridCellMinMax(x_idx,y_idx,z_idx)",
                            str(cell),
                        )
                    else:
                        self._hash_coordinates_map[_hash] = (
                            (cell["x_min"] + cell["x_max"]) / 2.0,
                            (cell["y_min"] + cell["y_max"]) / 2.0,
                            (cell["z_min"] + cell["z_max"]) / 2.0,
                        )

                val[_hash] = self._hash_coordinates_map[_hash]
        return val

    def convertXYZIndicesToCellHash(self, x_idx, y_idx, z_idx):
        """
        This function generates a unique cell hash based on an XYZ position
        within a grid. This reduces the complexity of cell lookups to O
        from O^3

        :param x_idx: the position of the cell on the x-axis (furthest west is 0)
        :param y_idx: the position of the cell on the y-axis (furthest south is 0)
        :param z_idx: the vertical interval
        :return cell_hash: the unique hash of the cell
        :rtype: int
        """
        return "%s%s%s" % (
            "%05.0f" % x_idx,
            "%05.0f" % y_idx,
            "%05.0f" % z_idx,
        )

    @staticmethod
    def convertCellHashToXYZIndices(cell_hash):
        """
        This function generates a unique cell hash based on an XYZ position within a grid.
        :param cell_hash: the unique hash of the cell
        :rtype: tuple with (x_idx, y_idx, z_idx)
        """
        try:
            if len(cell_hash) != 15:
                raise Exception(
                    "Cell hash '%s' expected to be 15 characters, but %s given",
                    cell_hash,
                    len(cell_hash),
                )

            x_idx = int(cell_hash[0:5])
            y_idx = int(cell_hash[5:10])
            z_idx = int(cell_hash[10:15])

            return x_idx, y_idx, z_idx
        except Exception as err:
            raise Exception(
                'Failed to get cell indices for "%s" hash: %s', cell_hash, err
            )

    def convertCoordinatesToXYZIndices(self, x, y, z):
        x_idx = int((x - self._grid_origin_x) / self._x_resolution)
        y_idx = int((y - self._grid_origin_y) / self._y_resolution)
        z_idx = int((z - self._grid_origin_z) / self._z_resolution)

        # linestr = "LINESTRING Z (%s %s %s,%s %s %s)"%(x, y, z, self._grid_origin_x, self._grid_origin_y, self._grid_origin_z)
        if x_idx < 0:
            # logger.error("'%s'=%i out of defined grid ... You should enlarge the grid! Coordinate is %s= %f,%s= %f,%s= %f" % ("x_idx", x_idx, "x", x, "y", y, "z", z))
            x_idx = 0
        if y_idx < 0:
            # logger.error("'%s'=%i out of defined grid ...You should enlarge the grid! Coordinate is %s= %f" % ("y_idx", y_idx, "y", y))
            y_idx = 0
        if z_idx < 0:
            # logger.error("'%s'=%i out of defined grid ... You should enlarge the grid! Coordinate is %s= %f" % ("z_idx", z_idx, "z", z))
            z_idx = 0
        return x_idx, y_idx, z_idx

    def matchBoundingBoxToXYZindices(self, bbox, z_as_list=False):
        keys_ = ["x_min", "y_min", "z_min", "x_max", "y_max", "z_max"]
        for e in keys_:
            if e not in bbox:
                logger.error(
                    "Expected bounding box as dictionary with keys "
                    "'%s' but got '%s'",
                    ",".join(keys_),
                    str(bbox),
                )
                logger.error("\t Return empty matches")
                return []

        x_idx_low, y_idx_low, z_idx_low = self.convertCoordinatesToXYZIndices(
            bbox["x_min"], bbox["y_min"], bbox["z_min"]
        )
        x_idx_high, y_idx_high, z_idx_high = self.convertCoordinatesToXYZIndices(
            bbox["x_max"], bbox["y_max"], bbox["z_max"]
        )

        matched_cells = []
        for x in range(x_idx_low, x_idx_high + 1):
            for y in range(y_idx_low, y_idx_high + 1):
                if z_as_list:
                    z_list = []
                    for z in range(z_idx_low, z_idx_high + 1):
                        if (
                            not x > self._x_cells
                            or y > self._y_cells
                            or z > self._z_cells
                        ):
                            z_list.append(z)
                    matched_cells.append((x, y, z_list))
                else:
                    for z in range(z_idx_low, z_idx_high + 1):
                        if (
                            not x > self._x_cells
                            or y > self._y_cells
                            or z > self._z_cells
                        ):
                            matched_cells.append((x, y, z))

        return matched_cells

    def matchBoundingBoxToCellHashList(
        self, bbox: dict, z_as_list: bool = False
    ) -> list:
        matched_cells = []
        for (x, y, z) in self.matchBoundingBoxToXYZindices(bbox, z_as_list):
            if not z_as_list:
                matched_cells.append(self.convertXYZIndicesToCellHash(x, y, z))
            else:
                z_list = []
                for z_idx in z:
                    z_list.append(self.convertXYZIndicesToCellHash(x, y, z_idx))

                if len(z_list) > 0:
                    matched_cells.append(z_list)

        return matched_cells
