DROP TABLE IF EXISTS "tbl_InvMeteo";
CREATE TABLE IF NOT EXISTS "tbl_InvMeteo" (
	"meteo_id"	INTEGER PRIMARY KEY,
	"time_meteo"	TIMESTAMP,
	"mix_height"	DECIMAL,
	"temperature"	DECIMAL,
	"rel_humidity"	DECIMAL,
	"surf_pressure"	DECIMAL,
	"humidity_ratio"	DECIMAL,
	"humidty_coeff"	DECIMAL,
	"sound_speed"	DECIMAL,
	"temperature_ratio"	DECIMAL,
	"pressure_ratio"	DECIMAL,
	"ffm_cf1"	DECIMAL,
	"ffm_cf2"	DECIMAL,
	"ffm_cf3"	DECIMAL
);