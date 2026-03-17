/**
 * db-client.js — MongoDB Atlas client for AI Game workflow
 *
 * Replaces local JSON file reads with MongoDB queries.
 * Collections: code_base, code_expert, design_base, design_expert, rules
 */

const { MongoClient } = require('mongodb');
const path = require('path');

// Load .env from project root
function loadEnv() {
  const envPath = path.resolve(__dirname, '../../.env');
  try {
    const fs = require('fs');
    const content = fs.readFileSync(envPath, 'utf-8');
    content.split('\n').forEach(line => {
      line = line.trim();
      if (!line || line.startsWith('#')) return;
      const [key, ...rest] = line.split('=');
      if (key && rest.length) {
        process.env[key.trim()] = rest.join('=').trim();
      }
    });
  } catch (e) {
    // .env not found — rely on system env vars
  }
}

loadEnv();

const MONGO_URI = process.env.MONGO_URI;
const DB_NAME = process.env.MONGO_DB_NAME || 'aigame';

let _client = null;
let _db = null;

// ─── Connection ───

async function connect() {
  if (_db) return _db;
  _client = new MongoClient(MONGO_URI);
  await _client.connect();
  _db = _client.db(DB_NAME);
  return _db;
}

async function close() {
  if (_client) {
    await _client.close();
    _client = null;
    _db = null;
  }
}

async function getCollection(name) {
  const db = await connect();
  return db.collection(name);
}

// ─── Helpers ───

/** Case-insensitive regex match for string fields */
function ci(val) {
  return { $regex: new RegExp(`^${val.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`, 'i') };
}

// ─── Code DB ───

/**
 * Search code entries (base or expert)
 * @param {Object} filter - { genre, layer, role, system, minScore, tags }
 * @param {Object} options - { limit, sort, expert }
 */
async function findCode(filter = {}, options = {}) {
  const collName = options.expert ? 'code_expert' : 'code_base';
  const col = await getCollection(collName);

  const query = {};
  if (filter.genre) query.genre = ci(filter.genre);
  if (filter.layer) query.layer = ci(filter.layer);
  if (filter.role) query.role = ci(filter.role);
  if (filter.system) query.system = filter.system;
  if (filter.minScore) query.score = { $gte: filter.minScore };
  if (filter.fileId) query.fileId = filter.fileId;
  if (filter.tags) {
    query.$or = [
      { 'tags.major': { $in: Array.isArray(filter.tags) ? filter.tags : [filter.tags] } },
      { 'tags.minor': { $in: Array.isArray(filter.tags) ? filter.tags : [filter.tags] } }
    ];
  }

  const sort = options.sort || { score: -1 };
  const limit = options.limit || 50;

  return col.find(query).sort(sort).limit(limit).toArray();
}

/**
 * Get a single code file by fileId
 */
async function getCode(fileId, expert = false) {
  const collName = expert ? 'code_expert' : 'code_base';
  const col = await getCollection(collName);
  return col.findOne({ fileId });
}

/**
 * Upsert a code entry (insert or update)
 */
async function upsertCode(data, expert = false) {
  const collName = expert ? 'code_expert' : 'code_base';
  const col = await getCollection(collName);
  const filter = data.project
    ? { fileId: data.fileId, project: data.project }
    : { fileId: data.fileId };
  return col.updateOne(
    filter,
    { $set: { ...data, updatedAt: new Date() } },
    { upsert: true }
  );
}

/**
 * Promote code to expert (copy from base to expert)
 */
async function promoteCodeToExpert(fileId) {
  const doc = await getCode(fileId, false);
  if (!doc || doc.score < 0.6) return null;
  delete doc._id;
  return upsertCode(doc, true);
}

// ─── Design DB ───

/**
 * Search design entries (base or expert)
 * @param {Object} filter - { genre, domain, system, minScore, source, data_type, project, tags }
 * @param {Object} options - { limit, sort, expert }
 */
async function findDesign(filter = {}, options = {}) {
  const collName = options.expert ? 'design_expert' : 'design_base';
  const col = await getCollection(collName);

  const query = {};
  if (filter.genre) query.genre = ci(filter.genre);
  if (filter.domain) query.domain = ci(filter.domain);
  if (filter.system) query.system = filter.system;
  if (filter.project) query.project = filter.project;
  if (filter.source) query.source = filter.source;
  if (filter.data_type) query.data_type = filter.data_type;
  if (filter.minScore) query.score = { $gte: filter.minScore };
  if (filter.designId) query.designId = filter.designId;
  if (filter.tags) {
    query.tags = { $in: Array.isArray(filter.tags) ? filter.tags : [filter.tags] };
  }

  const sort = options.sort || { score: -1 };
  const limit = options.limit || 50;

  return col.find(query).sort(sort).limit(limit).toArray();
}

/**
 * Get a single design file by designId
 */
async function getDesign(designId, expert = false) {
  const collName = expert ? 'design_expert' : 'design_base';
  const col = await getCollection(collName);
  return col.findOne({ designId });
}

/**
 * Upsert a design entry
 */
async function upsertDesign(data, expert = false) {
  const collName = expert ? 'design_expert' : 'design_base';
  const col = await getCollection(collName);
  const filter = data.project
    ? { designId: data.designId, project: data.project }
    : { designId: data.designId };
  return col.updateOne(
    filter,
    { $set: { ...data, updatedAt: new Date() } },
    { upsert: true }
  );
}

/**
 * Promote design to expert
 */
async function promoteDesignToExpert(designId) {
  const doc = await getDesign(designId, false);
  if (!doc || doc.score < 0.6) return null;
  delete doc._id;
  return upsertDesign(doc, true);
}

// ─── Rules DB ───

async function findRules(filter = {}) {
  const col = await getCollection('rules');
  const query = {};
  if (filter.category) query.category = filter.category;
  if (filter.genre) query.genre = filter.genre;
  if (filter.type) query.type = filter.type;
  return col.find(query).toArray();
}

async function upsertRule(data) {
  const col = await getCollection('rules');
  return col.updateOne(
    { ruleId: data.ruleId },
    { $set: { ...data, updatedAt: new Date() } },
    { upsert: true }
  );
}

// ─── Search (CLAUDE.md priority order) ───

/**
 * Search with CLAUDE.md priority:
 * 1. Expert DB (matching genre)
 * 2. Expert DB (Generic)
 * 3. Base DB (matching genre)
 * 4. Base DB (Generic)
 */
async function searchCodeByPriority(genre, filter = {}, limit = 10) {
  const results = [];

  // Priority 1: Expert, matching genre
  const expert = await findCode({ ...filter, genre, minScore: 0.6 }, { expert: true, limit });
  results.push(...expert.map(r => ({ ...r, _priority: 1 })));

  // Priority 2: Expert, Generic
  if (genre !== 'Generic') {
    const expertGeneric = await findCode({ ...filter, genre: 'Generic', minScore: 0.6 }, { expert: true, limit });
    results.push(...expertGeneric.map(r => ({ ...r, _priority: 2 })));
  }

  // Priority 3: Base, matching genre
  const base = await findCode({ ...filter, genre }, { limit });
  results.push(...base.map(r => ({ ...r, _priority: 3 })));

  // Priority 4: Base, Generic
  if (genre !== 'Generic') {
    const baseGeneric = await findCode({ ...filter, genre: 'Generic' }, { limit });
    results.push(...baseGeneric.map(r => ({ ...r, _priority: 4 })));
  }

  // Deduplicate by fileId, keep highest priority
  const seen = new Map();
  for (const r of results) {
    if (!seen.has(r.fileId)) seen.set(r.fileId, r);
  }

  return Array.from(seen.values())
    .sort((a, b) => a._priority - b._priority || b.score - a.score)
    .slice(0, limit);
}

async function searchDesignByPriority(genre, filter = {}, limit = 10) {
  const results = [];

  const expert = await findDesign({ ...filter, genre, minScore: 0.6 }, { expert: true, limit });
  results.push(...expert.map(r => ({ ...r, _priority: 1 })));

  if (genre !== 'Generic') {
    const expertGeneric = await findDesign({ ...filter, genre: 'Generic', minScore: 0.6 }, { expert: true, limit });
    results.push(...expertGeneric.map(r => ({ ...r, _priority: 2 })));
  }

  const base = await findDesign({ ...filter, genre }, { limit });
  results.push(...base.map(r => ({ ...r, _priority: 3 })));

  if (genre !== 'Generic') {
    const baseGeneric = await findDesign({ ...filter, genre: 'Generic' }, { limit });
    results.push(...baseGeneric.map(r => ({ ...r, _priority: 4 })));
  }

  const seen = new Map();
  for (const r of results) {
    if (!seen.has(r.designId)) seen.set(r.designId, r);
  }

  return Array.from(seen.values())
    .sort((a, b) => a._priority - b._priority || b.score - a.score)
    .slice(0, limit);
}

// ─── Stats ───

async function getStats() {
  const db = await connect();
  const stats = {};
  for (const col of ['code_base', 'code_expert', 'design_base', 'design_expert', 'rules']) {
    stats[col] = await db.collection(col).countDocuments();
  }
  return stats;
}

module.exports = {
  connect,
  close,
  getCollection,
  // Code
  findCode,
  getCode,
  upsertCode,
  promoteCodeToExpert,
  searchCodeByPriority,
  // Design
  findDesign,
  getDesign,
  upsertDesign,
  promoteDesignToExpert,
  searchDesignByPriority,
  // Rules
  findRules,
  upsertRule,
  // Utils
  getStats,
};
