DROP TABLE IF EXISTS "user_taxiroute_aircraft_group";

CREATE TABLE "user_taxiroute_aircraft_group" (
  "oid" INTEGER PRIMARY KEY,
  "gate" TEXT,
  "runway" TEXT,
  "departure_arrival" VARCHAR(1),
  "instance_id" INTEGER,
  "aircraft_group" TEXT,
  "taxiway" TEXT,
  "taxiway_mes" TEXT,
  "distance" INTEGER
);
