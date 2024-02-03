DROP TABLE IF EXISTS "tbl_InvLog";
CREATE TABLE IF NOT EXISTS "tbl_InvLog" (
	"log_id"	INT PRIMARY KEY,
	"log_time"	TIMESTAMP,
	"log_type"	VARCHAR(1),
	"log_message"	TEXT
);
