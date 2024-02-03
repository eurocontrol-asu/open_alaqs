DROP TABLE IF EXISTS "user_month_profile";

CREATE TABLE "user_month_profile" (
  "oid" INTEGER PRIMARY KEY,
  "profile_name" TEXT,
  "jan" DECIMAL NULL,
  "feb" DECIMAL NULL,
  "mar" DECIMAL NULL,
  "apr" DECIMAL NULL,
  "may" DECIMAL NULL,
  "jun" DECIMAL NULL,
  "jul" DECIMAL NULL,
  "aug" DECIMAL NULL,
  "sep" DECIMAL NULL,
  "oct" DECIMAL NULL,
  "nov" DECIMAL NULL,
  "dec" DECIMAL NULL,
  UNIQUE ("oid")
);

INSERT INTO "user_month_profile" ("oid", "profile_name", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec") VALUES (1, 'default', 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1);
