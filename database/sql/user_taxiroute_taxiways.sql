DROP TABLE IF EXISTS "user_taxiroute_taxiways";

CREATE TABLE "user_taxiroute_taxiways" (
  "oid" INTEGER PRIMARY KEY,
  "gate" TEXT,
  "route_name" TEXT,
  "runway" TEXT,
  "departure_arrival" VARCHAR(1) NOT NULL,
  "instance_id" INTEGER NOT NULL,
  "sequence" TEXT,
  "groups" TEXT,
  UNIQUE ("oid")
);
