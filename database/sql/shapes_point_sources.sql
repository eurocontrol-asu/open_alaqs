DROP TABLE IF EXISTS "shapes_point_sources";

CREATE TABLE "shapes_point_sources" (
  "oid" INTEGER PRIMARY KEY NOT NULL,
  "source_id" TEXT,
  "height" DECIMAL,
  "category" TEXT,
  "point_type" TEXT,
  "substance" TEXT,
  "temperature" DECIMAL,
  "diameter" DECIMAL,
  "velocity" DECIMAL,
  "ops_year" TEXT,
  "hour_profile" TEXT,
  "daily_profile" TEXT,
  "month_profile" TEXT,
  "co_kg_k" DECIMAL,
  "hc_kg_k" DECIMAL,
  "nox_kg_k" DECIMAL,
  "sox_kg_k" DECIMAL,
  "pm10_kg_k" DECIMAL,
  "p1_kg_k" DECIMAL,
  "p2_kg_k" DECIMAL,
  "instudy" TEXT,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_point_sources', 'geometry', 3857, 'POINT', 2);
