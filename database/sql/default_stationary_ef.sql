DROP TABLE IF EXISTS "default_stationary_ef";

CREATE TABLE "default_stationary_ef" (
  "oid" INTEGER PRIMARY KEY, 
  "category" DECIMAL NULL, 
  "type" DECIMAL NULL,
  "temperature" DECIMAL NULL, 
  "diameter" DECIMAL NULL, 
  "velocity" DECIMAL NULL, 
  "z" DECIMAL NULL, 
  "description" TEXT, 
  "co_kg_k" DECIMAL NULL, 
  "hc_kg_k" DECIMAL NULL, 
  "nox_kg_k" DECIMAL NULL, 
  "sox_kg_k" DECIMAL NULL, 
  "particulate_kg_k" DECIMAL NULL, 
  "p1_kg_k" DECIMAL NULL, 
  "p2_kg_k" DECIMAL NULL, 
  "SUBSTANCE" DECIMAL NULL
);