/**
 * safe-io.js - Atomic file writes + safe JSON I/O
 * Prevents data corruption during parallel Agent Team execution.
 *
 * Usage:
 *   const { readJsonSafe, writeJsonAtomic, upsertIndex, ensureDir } = require('./lib/safe-io');
 */

'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Read JSON file safely. Returns null on any error (missing, corrupt, etc.).
 * @param {string} filePath - Absolute path to JSON file
 * @returns {*|null} Parsed data or null
 */
function readJsonSafe(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Write JSON atomically: write to .tmp.{pid} file, then rename.
 * On Windows, fs.renameSync may fail if the target is locked by another process,
 * so we fall back to copyFileSync + unlinkSync.
 *
 * @param {string} filePath - Target file path
 * @param {*} data - Data to serialize as JSON
 */
function writeJsonAtomic(filePath, data) {
  const dir = path.dirname(filePath);
  ensureDir(dir);

  const tmpPath = `${filePath}.tmp.${process.pid}`;
  const json = JSON.stringify(data, null, 2);

  fs.writeFileSync(tmpPath, json, 'utf-8');

  try {
    fs.renameSync(tmpPath, filePath);
  } catch {
    // Windows fallback: copy + unlink temp
    try {
      fs.copyFileSync(tmpPath, filePath);
      fs.unlinkSync(tmpPath);
    } catch (e2) {
      // Last resort: direct write (non-atomic)
      try { fs.unlinkSync(tmpPath); } catch { /* ignore */ }
      fs.writeFileSync(filePath, json, 'utf-8');
    }
  }
}

/**
 * Atomic read-modify-write for index.json files.
 * Reads the current index, upserts the entry by key, writes back atomically.
 *
 * @param {string} indexPath - Path to index.json
 * @param {object} entry - The entry to upsert
 * @param {string} key - The field to match on (default: 'designId')
 * @returns {Array} The updated index array
 */
function upsertIndex(indexPath, entry, key = 'designId') {
  let index = readJsonSafe(indexPath);
  if (!Array.isArray(index)) index = [];

  const existingIdx = index.findIndex(e => e[key] === entry[key]);
  if (existingIdx >= 0) {
    index[existingIdx] = entry;
  } else {
    index.push(entry);
  }

  writeJsonAtomic(indexPath, index);
  return index;
}

/**
 * Ensure directory exists (mkdir -p equivalent).
 * @param {string} dirPath - Directory path to create
 */
function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

module.exports = { readJsonSafe, writeJsonAtomic, upsertIndex, ensureDir };
