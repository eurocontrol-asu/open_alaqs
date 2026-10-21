DROP TABLE IF EXISTS "shapes_receptor_points";

CREATE TABLE "shapes_receptor_points" (
  "oid" INTEGER PRIMARY KEY NOT NULL,
  "source_id" TEXT,
  "xcoord" REAL,
  "ycoord" REAL,
  "height" REAL,
  "instudy" TEXT,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_receptor_points', 'geometry', 3857, 'POINT', 2);
