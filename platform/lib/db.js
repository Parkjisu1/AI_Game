const { MongoClient } = require('mongodb');

const MONGO_URI = process.env.MONGO_URI;
const DB_NAME = process.env.MONGO_DB_NAME || 'aigame';

let _client = null;
let _db = null;

async function connectDb() {
  if (_db) return _db;
  _client = new MongoClient(MONGO_URI, {
    serverSelectionTimeoutMS: 5000,
    connectTimeoutMS: 5000,
    socketTimeoutMS: 30000,
  });
  await _client.connect();
  _db = _client.db(DB_NAME);

  // Ensure indexes
  await _db.collection('activity_logs').createIndex({ timestamp: -1 });
  await _db.collection('activity_logs').createIndex({ userId: 1 });
  await _db.collection('activity_logs').createIndex({ type: 1 });
  await _db.collection('users').createIndex({ username: 1 }, { unique: true });

  return _db;
}

function getDb() {
  if (!_db) throw new Error('Database not connected');
  return _db;
}

async function closeDb() {
  if (_client) {
    await _client.close();
    _client = null;
    _db = null;
  }
}

module.exports = { connectDb, getDb, closeDb };
