DROP TABLE IF EXISTS "default_aircraft_profiles";

CREATE TABLE "default_aircraft_profiles" (
  "oid" INTEGER PRIMARY KEY, 
  "profile_id" VARCHAR(20), 
  "arrival_departure" VARCHAR(1), 
  "stage" INTEGER, 
  "point" INTEGER, 
  "weight_lbs" DECIMAL NULL, 
  "horizontal_feet" DECIMAL NULL, 
  "vertical_feet" DECIMAL NULL, 
  "tas_feet" DECIMAL NULL, 
  "weight_kgs" DECIMAL NULL, 
  "horizontal_metres" DECIMAL NULL DEFAULT 0, 
  "vertical_metres" DECIMAL NULL DEFAULT 0, 
  "tas_metres" DECIMAL NULL, 
  "power" DECIMAL NULL,
  "mode" VARCHAR(5), 
  "course" VARCHAR(15)
);