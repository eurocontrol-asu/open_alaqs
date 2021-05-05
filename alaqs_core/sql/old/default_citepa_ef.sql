DROP TABLE IF EXISTS "default_citepa_ef";

CREATE TABLE "default_citepa_ef" (
  "id" DECIMAL NULL,
  "category" TEXT,
  "fuel" VARCHAR(8),
  "speed" DECIMAL NULL,
  "co_c" DECIMAL NULL,
  "co_h" DECIMAL NULL,
  "voc_c" DECIMAL NULL,
  "voc_h" DECIMAL NULL,
  "voc_hs" DECIMAL NULL,
  "voc_de" DECIMAL NULL,
  "voc_rl" DECIMAL NULL,
  "nox_c" DECIMAL NULL,
  "nox_h" DECIMAL NULL,
  "ch4" DECIMAL NULL,
  "c02" DECIMAL NULL,
  "n2o" DECIMAL NULL,
  "nh3" DECIMAL NULL,
  "so2" DECIMAL NULL,
  "remarks" TEXT,
  "oid" SERIAL NOT NULL
);