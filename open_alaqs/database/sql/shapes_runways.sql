DROP TABLE IF EXISTS "shapes_runways";

CREATE TABLE "shapes_runways" (
  "oid" INTEGER PRIMARY KEY NOT NULL,
  "runway_id" TEXT,
  "capacity" INT,
  "touchdown" INT,
  "max_queue_speed" DECIMAL,
  "peak_queue_time" DECIMAL,
  "instudy" DECIMAL,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_runways', 'geometry', 3857, 'LINESTRING', 2);
