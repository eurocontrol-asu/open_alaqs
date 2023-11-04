DROP TABLE IF EXISTS "default_class_break";

CREATE TABLE "default_class_break" (
  "oid" INTEGER PRIMARY KEY, 
  "class_id" TEXT, 
  "min_value" DECIMALNULL DEFAULT 0, 
  "max_value" DECIMALNULL DEFAULT 0, 
  "label" TEXT, 
  "rgb_red" INTEGER DEFAULT 0, 
  "rgb_green" INTEGER DEFAULT 0, 
  "rgb_blue" INTEGER DEFAULT 0
);