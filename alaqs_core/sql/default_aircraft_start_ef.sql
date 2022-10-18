DROP TABLE IF EXISTS "default_aircraft_start_ef";

CREATE TABLE "default_aircraft_start_ef" (
  "oid" INTEGER PRIMARY KEY, 
  "aircraft_group" VARCHAR(23) NOT NULL, 
  "aircraft_code" VARCHAR(13), 
  "emission_unit" VARCHAR(16), 
  "co" DOUBLE PRECISION NULL, 
  "hc" DOUBLE PRECISION NULL, 
  "nox" DOUBLE PRECISION NULL, 
  "sox" DOUBLE PRECISION NULL, 
  "pm_total" DOUBLE PRECISION NULL,
  "p1" DOUBLE PRECISION NULL, 
  "p2" DOUBLE PRECISION NULL, 
  UNIQUE ("oid")
);