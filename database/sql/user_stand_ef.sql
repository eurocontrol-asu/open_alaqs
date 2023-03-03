DROP TABLE IF EXISTS "user_stand_ef";

CREATE TABLE "user_stand_ef" (
  "oid" INTEGER PRIMARY KEY, 
  "gate_type" TEXT, 
  "aircraft_group" TEXT, 
  "emission_type" TEXT, 
  "time_unit" TEXT, 
  "departure" DECIMAL NULL, 
  "arrival" DECIMAL NULL, 
  "emission_unit" TEXT, 
  "co" DECIMAL NULL, 
  "hc" DECIMAL NULL, 
  "nox" DECIMAL NULL, 
  "sox" DECIMAL NULL, 
  "pm10" DECIMAL NULL, 
  "p1" DECIMAL NULL, 
  "p2" DECIMAL NULL
);

CREATE INDEX "oid" ON "user_stand_ef" ("oid");