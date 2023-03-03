DROP TABLE IF EXISTS "default_aircraft_profiles";

CREATE TABLE IF NOT EXISTS "default_aircraft_profiles" (
	"oid"	INTEGER,
	"profile_id"	VARCHAR(20),
	"arrival_departure"	VARCHAR(1),
	"stage"	INTEGER,
	"point"	INTEGER,
	"weight_lbs"	DECIMAL,
	"horizontal_feet"	DECIMAL,
	"vertical_feet"	DECIMAL,
	"tas_knots"	DECIMAL,
	"weight_kgs"	DECIMAL,
	"horizontal_metres"	DECIMAL DEFAULT 0,
	"vertical_metres"	DECIMAL DEFAULT 0,
	"tas_metres"	DECIMAL,
	"power"	DECIMAL,
	"mode"	VARCHAR(5),
	"course"	VARCHAR(15),
	"fuel_flow_kgm"	DECIMAL,
	PRIMARY KEY("oid")
);