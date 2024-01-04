DROP TABLE IF EXISTS "shapes_aircraft_tracks";

CREATE TABLE "shapes_aircraft_tracks" (
  "oid" INTEGER PRIMARY KEY NOT NULL,
  "track_id" TEXT,
  "runway" TEXT,
  "departure_arrival" TEXT,
  "points" DECIMAL,
  "shape_length" DECIMAL,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_aircraft_tracks', 'geometry', 3857, 'LINESTRING', 2);
