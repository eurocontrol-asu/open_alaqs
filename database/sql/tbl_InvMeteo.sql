DROP TABLE IF EXISTS "tbl_InvMeteo";
CREATE TABLE IF NOT EXISTS "tbl_InvMeteo" (
	"id"	INTEGER PRIMARY KEY NOT NULL,
	"Scenario"	TEXT,
	"DateTime"	DATETIME,
	"Temperature"	DECIMAL,
	"Humidity"	DECIMAL,
	"RelativeHumidity"	DECIMAL,
	"SeaLevelPressure"	DECIMAL,
	"WindSpeed"	DECIMAL,
	"WindDirection"	DECIMAL,
	"ObukhovLength"	DECIMAL,
	"MixingHeight"	DECIMAL,
	"SpeedOfSound"	DECIMAL
);
