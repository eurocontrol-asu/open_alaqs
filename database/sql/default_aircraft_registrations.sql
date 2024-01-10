DROP TABLE IF EXISTS "default_aircraft_registrations";

CREATE TABLE "default_aircraft_registrations" (
  "oid" INTEGER PRIMARY KEY,
  "aircraft_registration" TEXT,
  "icao" TEXT,
  "engine_count" INTEGER,
  "jp_reference" TEXT,
  "engine_full_name" TEXT,
  "engine_name" TEXT,
  UNIQUE ("OID")
);
