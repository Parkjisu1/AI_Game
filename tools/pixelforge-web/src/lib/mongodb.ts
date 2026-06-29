import { MongoClient, Db } from "mongodb";

const uri = process.env.MONGODB_URI;
const dbName = process.env.MONGODB_DB || "aigame";

if (!uri) {
  throw new Error("MONGODB_URI 환경변수가 설정되지 않았습니다.");
}

// Vercel serverless 환경에서 cold start 시 connection 누수를 방지하기 위해
// global 객체에 client promise를 캐시한다.
declare global {
  // eslint-disable-next-line no-var
  var __pixelforgeMongoClient: Promise<MongoClient> | undefined;
}

const clientPromise: Promise<MongoClient> =
  global.__pixelforgeMongoClient ??
  (global.__pixelforgeMongoClient = new MongoClient(uri).connect());

export async function getDb(): Promise<Db> {
  const client = await clientPromise;
  return client.db(dbName);
}
