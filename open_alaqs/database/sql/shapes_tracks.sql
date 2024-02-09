DROP TABLE IF EXISTS "shapes_tracks";

CREATE TABLE "shapes_tracks" (
  "oid" INTEGER PRIMARY KEY NOT NULL,
  "track_id" TEXT,
  "runway" TEXT,
  "departure_arrival" TEXT,
  "instudy" INT,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_tracks', 'geometry', 3857, 'LINESTRING', 2);
