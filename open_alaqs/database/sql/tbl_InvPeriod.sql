DROP TABLE IF EXISTS "tbl_InvPeriod";
CREATE TABLE IF NOT EXISTS "tbl_InvPeriod" (
	"min_time"	TIMESTAMP,
	"max_time"	TIMESTAMP,
	"interval"	DECIMAL,
	"apt_elev"	DECIMAL,
	"vert_limit"	DECIMAL,
	"temp_isa"	DECIMAL,
	"copert"	INT,
	"nox_corr"	INT,
	"ffm"	INT,
	"mix_height"	INT,
	"rwy_roll_split"	DECIMAL,
	"tow_speed"	DECIMAL,
	"smsh"	INT,
	"grd_buffer"	DECIMAL
);
