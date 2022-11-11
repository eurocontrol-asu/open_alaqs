DROP TABLE IF EXISTS "shapes_gates";

CREATE TABLE "shapes_gates" (
  "oid" INTEGER PRIMARY KEY NOT NULL, 
  "gate_id" TEXT,
  "gate_type" TEXT,
  "gate_height" DECIMAL,
  "instudy" TEXT,
  UNIQUE ("oid")
);

SELECT AddGeometryColumn('shapes_gates', 'geometry', 3857, 'POLYGON', 2);