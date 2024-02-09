DROP TABLE IF EXISTS "user_day_profile";

CREATE TABLE "user_day_profile" (
  "oid" INTEGER PRIMARY KEY,
  "profile_name" TEXT,
  "mon" DECIMAL NULL,
  "tue" DECIMAL NULL,
  "wed" DECIMAL NULL,
  "thu" DECIMAL NULL,
  "fri" DECIMAL NULL,
  "sat" DECIMAL NULL,
  "sun" DECIMAL NULL,
  UNIQUE ("oid")
);

INSERT INTO "user_day_profile" ("oid", "profile_name", "sun", "mon", "tue", "wed", "thu", "fri", "sat") VALUES (1, 'default', 1, 1, 1, 1, 1, 1, 1);
