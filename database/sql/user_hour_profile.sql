DROP TABLE IF EXISTS "user_hour_profile";

CREATE TABLE "user_hour_profile" (
  "oid" INTEGER PRIMARY KEY, 
  "profile_name" TEXT, 
  "h01" DECIMAL NULL, 
  "h02" DECIMAL NULL, 
  "h03" DECIMAL NULL, 
  "h04" DECIMAL NULL, 
  "h05" DECIMAL NULL, 
  "h06" DECIMAL NULL, 
  "h07" DECIMAL NULL, 
  "h08" DECIMAL NULL, 
  "h09" DECIMAL NULL, 
  "h10" DECIMAL NULL, 
  "h11" DECIMAL NULL, 
  "h12" DECIMAL NULL, 
  "h13" DECIMAL NULL, 
  "h14" DECIMAL NULL, 
  "h15" DECIMAL NULL, 
  "h16" DECIMAL NULL, 
  "h17" DECIMAL NULL, 
  "h18" DECIMAL NULL, 
  "h19" DECIMAL NULL, 
  "h20" DECIMAL NULL, 
  "h21" DECIMAL NULL, 
  "h22" DECIMAL NULL, 
  "h23" DECIMAL NULL, 
  "h24" DECIMAL NULL, 
  UNIQUE ("oid")
);

INSERT INTO "user_hour_profile" ("oid", "profile_name", "h01", "h02", "h03", "h04", "h05", "h06", "h07", "h08", "h09", "h10", "h11", "h12", "h13", "h14", "h15", "h16", "h17", "h18", "h19", "h20", "h21", "h22", "h23", "h24") VALUES (1, 'default', 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1);