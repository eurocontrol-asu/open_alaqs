from __future__ import print_function
import ogr, osr

point_lat = 50.734444 
point_long = -3.413889

# Spatial Reference System
outputEPSG = 3857
inputEPSG = 4326

# create a geometry from coordinates
point = ogr.Geometry(ogr.wkbPoint)
point.AddPoint(point_lat, point_long)

# create coordinate transformation
inSpatialRef = osr.SpatialReference()
inSpatialRef.ImportFromEPSG(inputEPSG)

outSpatialRef = osr.SpatialReference()
outSpatialRef.ImportFromEPSG(outputEPSG)

coordTransform = osr.CoordinateTransformation(inSpatialRef, outSpatialRef)

# transform point
point.Transform(coordTransform)

# print point in EPSG 3857# fix_print_with_import

# fix_print_with_import
print(point.GetX(), point.GetY())