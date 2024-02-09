DROP TABLE IF EXISTS "default_merge_definition";

CREATE TABLE "default_merge_definition" (
  "oid" INTEGER PRIMARY KEY,
  "category" TEXT,
  "code" TEXT NOT NULL,
  "shp_table" TEXT,
  "id_field" TEXT,
  "elevation_field" TEXT,
  "type" TEXT,
  "size" TEXT,
  UNIQUE ("oid")
);
