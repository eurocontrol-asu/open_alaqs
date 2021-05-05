DROP TABLE IF EXISTS "default_lasport_road";

CREATE TABLE "default_lasport_road" (
  "oid" INTEGER PRIMARY KEY, 
  "category_d" TEXT, 
  "vehicle_category" TEXT, 
  "year" DECIMAL NULL, 
  "scenario_code" TEXT, 
  "description" TEXT, 
  "scenario" TEXT, 
  "average_speed" DECIMAL NULL, 
  "buwal_scenario" TEXT, 
  "unit" TEXT, 
  "benzol" DECIMAL NULL, 
  "co" DECIMAL NULL, 
  "hc" DECIMAL NULL, 
  "nox" DECIMAL NULL, 
  "pm10" DECIMAL NULL
);