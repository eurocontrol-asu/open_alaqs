DROP TABLE IF EXISTS "shapes_area_sources";

CREATE TABLE "shapes_area_sources" (
  "oid" INTEGER PRIMARY KEY, 
  "source_id" TEXT,
  "unit_year" TEXT,
  "height" DECIMAL,
  "heat_flux" DECIMAL,
  "hourly_profile" TEXT,
  "daily_profile" TEXT,
  "monthly_profile" TEXT,
  "co_kg_unit" DECIMAL,
  "hc_kg_unit" DECIMAL,
  "nox_kg_unit" DECIMAL,
  "sox_kg_unit" DECIMAL,
  "pm_total_kg_unit" DECIMAL,
  "p1_kg_unit" DECIMAL,
  "p2_kg_unit" DECIMAL,
  "instudy" TEXT,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_area_sources', 'geometry', 3857, 'POLYGON', 2);
