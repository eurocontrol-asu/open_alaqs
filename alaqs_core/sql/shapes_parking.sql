DROP TABLE IF EXISTS "shapes_parking";

CREATE TABLE "shapes_parking" (
  "oid" INTEGER PRIMARY KEY NOT NULL, 
  "parking_id" TEXT,
  "height" DECIMAL,
  "distance" DECIMAL,
  "idle_time" DECIMAL,
  "park_time" DECIMAL,
  "vehicle_light" DECIMAL,
  "vehicle_medium" DECIMAL,
  "vehicle_heavy" DECIMAL,
  "vehicle_year" DECIMAL,
  "speed" DECIMAL,
  "hour_profile" TEXT,
  "daily_profile" TEXT,
  "month_profile" TEXT,
  "co_gm_vh" DECIMAL,
  "hc_gm_vh" DECIMAL,
  "nox_gm_vh" DECIMAL,
  "sox_gm_vh" DECIMAL,
  "pm_total_gm_vh" DECIMAL,
  "p1_gm_vh" DECIMAL,
  "p2_gm_vh" DECIMAL,
  "method" TEXT,
  "instudy" TEXT,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_parking', 'geometry', 3857, 'POLYGON', 2);