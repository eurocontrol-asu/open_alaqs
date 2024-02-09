DROP TABLE IF EXISTS "default_dictionary";

CREATE TABLE "default_dictionary" (
  "oid" INTEGER PRIMARY KEY,
  "table_key" TEXT,
  "table_name" TEXT,
  "field_number" INTEGER,
  "field_key" TEXT,
  "field_name" TEXT,
  "unit" TEXT,
  "description" TEXT,
  UNIQUE ("oid")
);
