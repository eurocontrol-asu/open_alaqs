DROP TABLE IF EXISTS "default_citepa_category";

CREATE TABLE "default_citepa_category" (
  "category" TEXT,
  "petrol" DECIMAL NULL,
  "diesel" DECIMAL NULL,
  "lpg" DECIMAL NULL,
  "oid" SERIAL NOT NULL
);