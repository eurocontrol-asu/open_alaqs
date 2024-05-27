DROP TABLE IF EXISTS "tbl_InvTime";
CREATE TABLE IF NOT EXISTS "tbl_InvTime" (
	"time_id"	INTEGER PRIMARY KEY,
	"time"	TIMESTAMP,
	"mix_height"	INT
);
