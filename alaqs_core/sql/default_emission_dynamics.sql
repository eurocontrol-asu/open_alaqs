DROP TABLE IF EXISTS "default_emission_dynamics";

CREATE TABLE "default_emission_dynamics" (
  "oid" INTEGER PRIMARY KEY, 
  "dynamics_id" INTEGER DEFAULT 0, 
  "dynamics_name" VARCHAR(20), 
  "horizontal_extent_m" DECIMAL NULL DEFAULT 0, 
  "vertical_extent_m" DECIMAL NULL DEFAULT 0, 
  "exit_velocity_m_per_s" DECIMAL NULL DEFAULT 0, 
  "decay_time_s" DECIMAL NULL DEFAULT 0, 
  "horizontal_shift_m" DECIMAL NULL DEFAULT 0, 
  "vertical_shift_m" DECIMAL NULL DEFAULT 0, 
  "horizontal_extent_m_sas" DECIMAL NULL DEFAULT 0, 
  "vertical_extent_m_sas" DECIMAL NULL DEFAULT 0, 
  "vertical_shift_m_sas" DECIMAL NULL DEFAULT 0, 
);