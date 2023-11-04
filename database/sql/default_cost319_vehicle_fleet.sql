DROP TABLE IF EXISTS "default_cost319_vehicle_fleet";

CREATE TABLE "default_cost319_vehicle_fleet" (
  "oid" INTEGER PRIMARY KEY,
  "country" TEXT,
  "category_abbreviation" VARCHAR(3),
  "fuel_engine" TEXT,
  "size" TEXT,
  "emission_class" TEXT,
  "base_year_1990" INTEGER,
  "base_year_1995" INTEGER, 
  "base_year_2000" INTEGER, 
  "base_year_2005" INTEGER, 
  "base_year_2010" INTEGER, 
  "base_year_2015" INTEGER, 
  "base_year_2020" INTEGER, 
  "annual_mileage" INTEGER, 
  "average_mileage" INTEGER DEFAULT 0, 
  "urban_percent" DECIMAL NULL, 
  "rural_percent" DECIMAL NULL, 
  "highway_percent" DECIMAL NULL, 
  "urban_kmh" DECIMAL NULL, 
  "rural_kmh" DECIMAL NULL, 
  "highway_kmh" DECIMAL NULL
);