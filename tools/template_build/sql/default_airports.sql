DROP TABLE IF EXISTS "default_airports";

CREATE TABLE "default_airports" (
  "oid" INTEGER PRIMARY KEY,
  "airport_code" VARCHAR(7) NOT NULL,
  "airport_name" TEXT,
  "airport_country" TEXT,
  "airport_latitude" DECIMAL,
  "airport_longitude" DECIMAL,
  "airport_elevation" INTEGER
);
