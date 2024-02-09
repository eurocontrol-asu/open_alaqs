DROP TABLE IF EXISTS "tbl_InvTime";
CREATE TABLE IF NOT EXISTS "tbl_InvTime" (
	"time_id"	INTEGER PRIMARY KEY,
	"time"	TIMESTAMP,
	"year"	INT,
	"month"	INT,
	"day"	INT,
	"hour"	INT,
	"weekday_id"	INT,
	"mix_height"	INT
);
