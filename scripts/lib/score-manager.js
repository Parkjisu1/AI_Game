/**
 * score-manager.js - Trust score lifecycle automation
 * Manages score updates, Expert DB promotion, and score event tracking.
 *
 * Usage:
 *   const { updateScore, promoteToExpert, SCORE_EVENTS, EXPERT_THRESHOLD } = require('./lib/score-manager');
 *   updateScore('rpg', 'ingame', 'MyDesign_v1', 'FEEDBACK_PASS');
 *   promoteToExpert('rpg', 'ingame', 'MyDesign_v1');
 */

'use strict';

const path = require('path');
const { readJsonSafe, writeJsonAtomic, upsertIndex, ensureDir } = require('./safe-io');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DESIGN_DB_ROOT = process.env.DESIGN_DB_ROOT || 'E:/AI/db/design';

const SCORE_EVENTS = {
  INITIAL:          { delta: 0.4,   description: 'Initial save' },
  DIRECTOR_PASS:    { delta: 0.2,   description: 'Validation passed (Director feedback)' },
  FEEDBACK_PASS:    { delta: 0.1,   description: 'Feedback incorporated successfully' },
  REUSE_SUCCESS:    { delta: 0.1,   description: 'Reused successfully in another project' },
  REUSE_FAIL:       { delta: -0.15, description: 'Reuse attempt failed' },
  CROSS_GENRE_REUSE:{ delta: 0.1,   description: 'Reused in different genre (Generic promotion candidate)' },
};

const EXPERT_THRESHOLD = 0.6;

// ---------------------------------------------------------------------------
// Score update
// ---------------------------------------------------------------------------

/**
 * Update the trust score for a design entry.
 * Updates both the detail file and the index entry atomically.
 *
 * @param {string} genre - Lowercase genre directory
 * @param {string} domain - Lowercase domain directory
 * @param {string} designId - Design entry ID
 * @param {string} eventName - Key from SCORE_EVENTS (e.g., 'FEEDBACK_PASS')
 * @returns {{ newScore: number, promoted: boolean, error: string|null }}
 */
function updateScore(genre, domain, designId, eventName) {
  const event = SCORE_EVENTS[eventName];
  if (!event) {
    return { newScore: 0, promoted: false, error: `Unknown score event: ${eventName}` };
  }

  // Paths
  const baseDir = path.join(DESIGN_DB_ROOT, 'base', genre, domain);
  const detailPath = path.join(baseDir, 'files', `${designId}.json`);
  const indexPath = path.join(baseDir, 'index.json');

  // Read detail
  const detail = readJsonSafe(detailPath);
  if (!detail) {
    return { newScore: 0, promoted: false, error: `Detail file not found: ${detailPath}` };
  }

  // Update score
  const oldScore = typeof detail.score === 'number' ? detail.score : 0.4;
  const newScore = Math.max(0, Math.min(1.0, oldScore + event.delta));
  const roundedScore = Math.round(newScore * 100) / 100;

  detail.score = roundedScore;

  // Add score event to feedback_history if it exists
  if (Array.isArray(detail.feedback_history)) {
    detail.feedback_history.push({
      event: eventName,
      delta: event.delta,
      old_score: oldScore,
      new_score: roundedScore,
      timestamp: new Date().toISOString(),
    });
  }

  // Write detail atomically
  writeJsonAtomic(detailPath, detail);

  // Update index entry score
  const index = readJsonSafe(indexPath);
  if (Array.isArray(index)) {
    const entry = index.find(e => e.designId === designId);
    if (entry) {
      entry.score = roundedScore;
      writeJsonAtomic(indexPath, index);
    }
  }

  // Auto-promote to Expert if threshold reached
  let promoted = false;
  if (roundedScore >= EXPERT_THRESHOLD) {
    const result = promoteToExpert(genre, domain, designId);
    promoted = !result.error;
  }

  return { newScore: roundedScore, promoted, error: null };
}

// ---------------------------------------------------------------------------
// Expert DB promotion
// ---------------------------------------------------------------------------

/**
 * Promote a design entry to Expert DB when score >= 0.6.
 * Copies detail file to expert/files/ and adds index entry to expert/index.json.
 *
 * @param {string} genre - Lowercase genre directory
 * @param {string} domain - Lowercase domain directory
 * @param {string} designId - Design entry ID
 * @returns {{ error: string|null }}
 */
function promoteToExpert(genre, domain, designId) {
  const baseDir = path.join(DESIGN_DB_ROOT, 'base', genre, domain);
  const detailPath = path.join(baseDir, 'files', `${designId}.json`);
  const indexPath = path.join(baseDir, 'index.json');

  // Read source data
  const detail = readJsonSafe(detailPath);
  if (!detail) {
    return { error: `Detail file not found: ${detailPath}` };
  }

  if ((detail.score || 0) < EXPERT_THRESHOLD) {
    return { error: `Score ${detail.score} below threshold ${EXPERT_THRESHOLD}` };
  }

  // Expert paths
  const expertDir = path.join(DESIGN_DB_ROOT, 'expert');
  const expertFilesDir = path.join(expertDir, 'files');
  const expertIndexPath = path.join(expertDir, 'index.json');
  const expertDetailPath = path.join(expertFilesDir, `${designId}.json`);

  ensureDir(expertFilesDir);

  // Copy detail to expert
  writeJsonAtomic(expertDetailPath, detail);

  // Build index entry from detail or base index
  const baseIndex = readJsonSafe(indexPath);
  let indexEntry = null;
  if (Array.isArray(baseIndex)) {
    indexEntry = baseIndex.find(e => e.designId === designId);
  }

  if (!indexEntry) {
    // Build from detail
    indexEntry = {
      designId: detail.designId || designId,
      domain: detail.domain,
      genre: detail.genre,
      system: detail.system || '',
      score: detail.score,
      source: detail.source || detail.source_type || 'internal_produced',
      data_type: detail.data_type || 'spec',
      balance_area: detail.balance_area || null,
      version: detail.version || '1.0.0',
      project: detail.project || null,
      provides: detail.provides || [],
      requires: detail.requires || [],
      tags: detail.tags || [],
    };
  } else {
    // Ensure score is up to date
    indexEntry = { ...indexEntry, score: detail.score };
  }

  // Upsert into expert index
  upsertIndex(expertIndexPath, indexEntry, 'designId');

  return { error: null };
}

module.exports = {
  SCORE_EVENTS,
  EXPERT_THRESHOLD,
  updateScore,
  promoteToExpert,
};
