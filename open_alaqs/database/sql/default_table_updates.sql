DROP TABLE IF EXISTS "default_table_updates";

CREATE TABLE "default_table_updates" (
  "oid" INTEGER PRIMARY KEY,
  "table_key" TEXT,
  "table_name" TEXT,
  "update_date" TIMESTAMP,
  "check_date" TIMESTAMP,
  "force_update" BOOLEAN DEFAULT '0'
);
