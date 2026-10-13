// 삭제 전 백업 덤프 공용 함수 (2026-10-13).
// - Extended JSON canonical(ObjectId·Date·int/double 타입 보존) → restore_mongo_dump.js 로 그대로 되살린다.
// - 이미 있는 파일은 절대 덮어쓰지 않는다(flag "wx"): 같은 경로면 실패. 경로를 안 주면 시각이 붙은 새 이름을 만든다.
const fs = require("fs"), path = require("path");
const { BSON } = require("mongodb");

function stampedPath(dir, base) {
  const ts = new Date().toISOString().replace(/[-:]/g, "").replace(/\..*$/, "").replace("T", "_");
  return path.join(dir, `${base}_${ts}.ejson`);
}

// docs 를 EJSON canonical 배열로 기록. 파일이 있으면 throw.
function writeDumpOnce(file, docs) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, BSON.EJSON.stringify(docs, null, 1, { relaxed: false }), { flag: "wx" });
  return file;
}

module.exports = { writeDumpOnce, stampedPath };
