DROP TABLE IF EXISTS "default_helicopter_engine_ei";
CREATE TABLE IF NOT EXISTS "default_helicopter_engine_ei" (
	"oid"	INTEGER,
	"engine_name"	TEXT,
	"engine_type"	TEXT,
	"max_shp_per_engine"	INTEGER,
	"shp_correction_factor"	INTEGER,
	"number_of_engines"	INTEGER,
	"gi1_time_min"	INTEGER,
	"gi2_time_min"	INTEGER,
	"to_time_min"	INTEGER,
	"ap_time_min"	REAL,
	"gi1_ff_per_engine_kg_s"	REAL,
	"gi2_ff_per_engine_kg_s"	REAL,
	"to_ff_per_engine_kg_s"	REAL,
	"ap_ff_per_engine_kg_s"	REAL,
	"gi1_einox_g_kg"	REAL,
	"gi2_einox_g_kg"	REAL,
	"to_einox_g_kg"	REAL,
	"ap_einox_g_kg"	REAL,
	"gi1_eihc_g_kg"	REAL,
	"gi2_eihc_g_kg"	REAL,
	"to_eihc_g_kg"	REAL,
	"ap_eihc_g_kg"	REAL,
	"gi1_eico_g_kg"	REAL,
	"gi2_eico_g_kg"	REAL,
	"to_eico_g_kg"	REAL,
	"ap_eico_g_kg"	REAL,
	"gi1_eipm_g_kg"	REAL,
	"gi2_eipm_g_kg"	REAL,
	"to_eipm_g_kg"	REAL,
	"ap_eipm_g_kg"	REAL
);