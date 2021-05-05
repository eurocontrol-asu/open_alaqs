DROP TABLE IF EXISTS "default_grid_definition";

CREATE TABLE "default_grid_definition" (
  "oid" INTEGER PRIMARY KEY, 
  "layerset_id" INTEGER, 
  "max_elev" DECIMAL NULL, 
  "num_levels" INTEGER, 
  "cell_size" INTEGER
);