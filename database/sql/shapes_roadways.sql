DROP TABLE IF EXISTS "shapes_roadways";

CREATE TABLE "shapes_roadways" (
  "oid" INTEGER PRIMARY KEY NOT NULL,
  "roadway_id" TEXT,
  "vehicle_year" TEXT,
  "height" DECIMAL,
  "distance" DECIMAL,
  "speed" DECIMAL,
  "vehicle_light" DECIMAL,
  "vehicle_medium" DECIMAL,
  "vehicle_heavy" DECIMAL,
  "hour_profile" TEXT,
  "daily_profile" TEXT,
  "month_profile" TEXT,
  "co_gm_km" DECIMAL,
  "hc_gm_km" DECIMAL,
  "nox_gm_km" DECIMAL,
  "sox_gm_km" DECIMAL,
  "pm10_gm_km" DECIMAL,
  "p1_gm_km" DECIMAL,
  "p2_gm_km" DECIMAL,
  "method" TEXT,
  "scenario" TEXT,
  "instudy" TEXT,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_roadways', 'geometry', 3857, 'LINESTRING', 2);