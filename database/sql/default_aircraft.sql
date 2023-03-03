DROP TABLE IF EXISTS "default_aircraft";

CREATE TABLE "default_aircraft" (
  "oid" INTEGER PRIMARY KEY, 
  "icao" TEXT, 
  "ac_group_code" TEXT, 
  "ac_group" TEXT, 
  "manufacturer" TEXT, 
  "name" TEXT, 
  "class" TEXT, 
  "mtow" DECIMAL, 
  "engine_count" INTEGER, 
  "engine_name" TEXT, 
  "engine" TEXT, 
  "departure_profile" TEXT, 
  "arrival_profile" TEXT, 
  "bada_id" TEXT, 
  "wake_category" TEXT,
  "apu_id" TEXT, 
  UNIQUE("icao")
);