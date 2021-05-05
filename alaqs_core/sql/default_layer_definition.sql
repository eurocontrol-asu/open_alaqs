DROP TABLE IF EXISTS "default_layer_definition";

CREATE TABLE "default_layer_definition" (
  "oid" INTEGER PRIMARY KEY, 
  "layer_name" TEXT, 
  "table_key" TEXT, 
  "table_name" TEXT, 
  "type" TEXT, 
  "id_field" TEXT, 
  "calculated_field" TEXT, 
  "coords_fields" TEXT, 
  "renderer" TEXT
);