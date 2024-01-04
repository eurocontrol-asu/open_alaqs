DROP TABLE IF EXISTS "default_apu_times";
CREATE TABLE IF NOT EXISTS "default_apu_times" (
	"oid"	INTEGER,
	"ac_category"	TEXT,
	"stand_type"	TEXT,
	"time_arr_min"	DECIMAL,
	"time_dep_min"	DECIMAL,
	PRIMARY KEY("oid")
);
