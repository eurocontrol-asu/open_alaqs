DROP TABLE IF EXISTS "tbl_InvActivityProfileList";
CREATE TABLE IF NOT EXISTS  "tbl_InvActivityProfileList" (
	"activity_profile_id"	INTEGER PRIMARY KEY,
	"name"	TEXT,
	"time_offset"	DECIMAL,
	"name_hour_profile"	TEXT,
	"name_weekday_profile"	TEXT,
	"name_month_profile"	TEXT
);