DROP TABLE IF EXISTS "default_apu_ef";

CREATE TABLE "default_apu_ef" (
	"oid"	INTEGER PRIMARY KEY,
	"aircraft_group"	TEXT,
	"FF_NL_in_kg_s"	DECIMAL,
	"FF_NR_in_kg_s"	DECIMAL,
	"FF_HL_in_kg_s"	DECIMAL,
	"NOx_NL_in_g_s"	DECIMAL,
	"NOx_NR_in_g_s"	DECIMAL,
	"NOx_HL_in_g_s"	DECIMAL,
	"HC_NL_in_g_s"	DECIMAL,
	"HC_NR_in_g_s"	DECIMAL,
	"HC_HL_in_g_s"	DECIMAL,
	"CO_NL_in_g_s"	DECIMAL,
	"CO_NR_in_g_s"	DECIMAL,
	"CO_HL_in_g_s"	DECIMAL
);
