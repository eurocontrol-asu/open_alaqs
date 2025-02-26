DROP TABLE IF EXISTS "default_vehicle_hc_ef";

CREATE TABLE "default_vehicle_hc_ef" (
  "oid" INTEGER PRIMARY KEY,
  "vehicle_type" TEXT,
  "class" TEXT,
  "legislation" TEXT,
  "a1" DECIMAL NULL DEFAULT 0,
  "b1" DECIMAL NULL DEFAULT 0,
  "c1" DECIMAL NULL DEFAULT 0,
  "d1" DECIMAL NULL DEFAULT 0,
  "e1" DECIMAL NULL DEFAULT 0,
  "f1" DECIMAL NULL DEFAULT 0,
  "g1" DECIMAL NULL DEFAULT 0,
  "h1" DECIMAL NULL DEFAULT 0,
  "corr1" DECIMAL NULL DEFAULT 0,
  "a2" DECIMAL NULL DEFAULT 0,
  "b2" DECIMAL NULL DEFAULT 0,
  "c2" DECIMAL NULL DEFAULT 0,
  "d2" DECIMAL NULL DEFAULT 0,
  "e2" DECIMAL NULL DEFAULT 0,
  "f2" DECIMAL NULL DEFAULT 0,
  "g2" DECIMAL NULL DEFAULT 0,
  "h2" DECIMAL NULL DEFAULT 0,
  "corr2" DECIMAL NULL DEFAULT 0
);
