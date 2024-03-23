--
-- Table structure for table 'user_study_setup'
-- This table is used to store user defined details of each airport included
-- in an Open ALAQS study.
--

DROP TABLE IF EXISTS "user_study_setup";
CREATE TABLE "user_study_setup" (
  "oid" INTEGER PRIMARY KEY NOT NULL,
  "airport_id" INTEGER NOT NULL,
  "alaqs_version" TEXT,
  "project_name" TEXT,
  "airport_name" TEXT,
  "airport_code" TEXT,
  "airport_country" TEXT,
  "airport_latitude" DECIMAL,
  "airport_longitude" DECIMAL,
  "airport_elevation" DECIMAL,
  "airport_temperature" DECIMAL,
  "vertical_limit" DECIMAL,
  "roadway_method" TEXT,
  "roadway_fleet_year" TEXT,
  "roadway_country" TEXT,
  "parking_method" TEXT,
  "study_info" TEXT,
  "date_created" TIMESTAMP WITH TIME ZONE,
  "date_modified" TIMESTAMP WITH TIME ZONE
);

INSERT INTO user_study_setup (
  airport_id,
  alaqs_version,
  project_name,
  airport_name,
  airport_code,
  airport_country,
  airport_latitude,
  airport_longitude,
  airport_elevation,
  airport_temperature,
  vertical_limit,
  roadway_method,
  roadway_fleet_year,
  roadway_country,
  parking_method,
  study_info,
  date_created,
  date_modified
)
VALUES (
  1,
  '0.0.1',
  NULL,
  NULL,
  NULL,
  NULL,
  0.0000,
  0.0000,
  0.0,
  15.0,
  913,
  NULL,
  NULL,
  NULL,
  'DEFAULT',
  NULL,
  DATETIME('now'),
  DATETIME('now')
);
