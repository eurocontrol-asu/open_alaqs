DROP TABLE IF EXISTS "default_edms_mobile5a";

CREATE TABLE "default_edms_mobile5a" (
  "oid" INTEGER PRIMARY KEY, 
  "year" VARCHAR(4), 
  "altitude" VARCHAR(1), 
  "temperature" INTEGER, 
  "speed" DECIMAL NULL, 
  "co_gm_m" DECIMAL NULL, 
  "hc_gm_m" DECIMAL NULL, 
  "nox_gm_m" DECIMAL NULL, 
  "sox_gm_m" DECIMAL NULL, 
  "part_gm_m" DECIMAL NULL, 
  UNIQUE ("oid")
);