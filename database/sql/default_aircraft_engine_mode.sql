DROP TABLE IF EXISTS "default_aircraft_engine_mode";

CREATE TABLE "default_aircraft_engine_mode" (
  "oid" INTEGER PRIMARY KEY,
  "mode" VARCHAR(2),
  "thrust" DECIMAL NULL,
  "description" TEXT
);
