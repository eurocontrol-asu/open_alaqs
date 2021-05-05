DROP TABLE IF EXISTS "user_aircraft_movements";

CREATE TABLE "user_aircraft_movements" (
  "oid" INTEGER PRIMARY KEY, 
  "runway_time" TIMESTAMP,
  "block_time" TIMESTAMP, 
  "aircraft_registration" TEXT, 
  "aircraft" TEXT, 
  "gate" TEXT, 
  "departure_arrival" TEXT, 
  "runway" TEXT, 
  "engine_name" TEXT, 
  "profile_id" TEXT, 
  "track_id" TEXT, 
  "taxi_route" TEXT,
  "tow_ratio" DECIMAL NULL, 
  "apu_code" INTEGER, 
  "taxi_engine_count" INTEGER,
  "set_time_of_main_engine_start_after_block_off_in_s" DECIMAL NULL,
  "set_time_of_main_engine_start_before_takeoff_in_s" DECIMAL NULL,
  "set_time_of_main_engine_off_after_runway_exit_in_s" DECIMAL NULL,
  "engine_thrust_level_for_taxiing" DECIMAL NULL,
  "taxi_fuel_ratio" DECIMAL NULL,
  "number_of_stop_and_gos" DECIMAL NULL,
  "domestic" TEXT,
  "annual_operations" DECIMAL NULL
);