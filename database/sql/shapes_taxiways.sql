DROP TABLE IF EXISTS "shapes_taxiways";

CREATE TABLE "shapes_taxiways" (
  "oid" INTEGER PRIMARY KEY NOT NULL, 
  "taxiway_id" TEXT,
  "speed" DECIMAL,
  "time" DECIMAL,
  "instudy" DECIMAL,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_taxiways', 'geometry', 3857, 'LINESTRING', 2);