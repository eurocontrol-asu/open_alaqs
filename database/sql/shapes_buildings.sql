DROP TABLE IF EXISTS "shapes_buildings";

CREATE TABLE "shapes_buildings" (
  "oid" INTEGER PRIMARY KEY NOT NULL, 
  "building_id" TEXT,
  "height" DECIMAL,
  "instudy" INT,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_buildings', 'geometry', 3857, 'POLYGON', 2);