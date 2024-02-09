DROP TABLE IF EXISTS "default_change_log";

CREATE TABLE "default_change_log" (
  "oid" INTEGER PRIMARY KEY,
  "date" TIMESTAMP,
  "table_name" TEXT,
  "version" TEXT,
  "description" TEXT
);
