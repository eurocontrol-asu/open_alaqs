DROP TABLE IF EXISTS "default_gate_profiles";

CREATE TABLE "default_gate_profiles" (
  "oid" INTEGER PRIMARY KEY,
  "gate_type" VARCHAR(20),
  "ac_group" VARCHAR(20),
  "emis_type" VARCHAR(10),
  "time_unit" VARCHAR(20),
  "op_type" VARCHAR(20),
  "time" DECIMAL,
  "emis_unit" DECIMAL,
  "co" DECIMAL,
  "hc" DECIMAL,
  "nox" DECIMAL,
  "sox" DECIMAL,
  "pm10" DECIMAL,
  "source" TEXT,
  UNIQUE ("oid")
);