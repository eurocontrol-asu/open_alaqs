DROP TABLE IF EXISTS "default_aircraft_apu_ef";

CREATE TABLE "default_aircraft_apu_ef" (
  "oid" INTEGER PRIMARY KEY,
  "apu_id" TEXT,
  "fuel_kg_h" DECIMAL,
  "co_kg_h" DECIMAL,
  "hc_kg_h" DECIMAL,
  "nox_kg_h" DECIMAL,
  "sox_kg_h" DECIMAL,
  "pm10_kg_h" DECIMAL
);
