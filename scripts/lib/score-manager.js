/**
 * score-manager.js - Trust score lifecycle automation
 * Manages score updates, Expert DB promotion, and score event tracking.
 * Uses MongoDB via db-client for persistence.
 *
 * Usage:
 *   const { updateScore, promoteToExpert, SCORE_EVENTS, EXPERT_THRESHOLD } = require('./lib/score-manager');
 *   await updateScore('rpg', 'ingame', 'MyDesign_v1', 'FEEDBACK_PASS');
 *   await promoteToExpert('rpg', 'ingame', 'MyDesign_v1');
 */

'use strict';

const { readJsonSafe, writeJsonAtomic, upsertIndex, ensureDir } = require('./safe-io');
const { getDesign, upsertDesign, promoteDesignToExpert } = require('./db-client');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

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
 * Reads from MongoDB, updates score, writes back, and auto-promotes if >= 0.6.
 *
 * @param {string} genre - Lowercase genre directory
 * @param {string} domain - Lowercase domain directory
 * @param {string} designId - Design entry ID
 * @param {string} eventName - Key from SCORE_EVENTS (e.g., 'FEEDBACK_PASS')
 * @returns {Promise<{ newScore: number, promoted: boolean, error: string|null }>}
 */
async function updateScore(genre, domain, designId, eventName) {
  const event = SCORE_EVENTS[eventName];
  if (!event) {
    return { newScore: 0, promoted: false, error: `Unknown score event: ${eventName}` };
  }

  // Read detail from MongoDB (base collection)
  const detail = await getDesign(designId, false);
  if (!detail) {
    return { newScore: 0, promoted: false, error: `Design not found in DB: ${designId}` };
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

  // Write updated detail back to MongoDB (base collection)
  await upsertDesign(detail, false);

  // Auto-promote to Expert if threshold reached
  let promoted = false;
  if (roundedScore >= EXPERT_THRESHOLD) {
    const result = await promoteToExpert(genre, domain, designId);
    promoted = !result.error;
  }

  return { newScore: roundedScore, promoted, error: null };
}

// ---------------------------------------------------------------------------
// Expert DB promotion
// ---------------------------------------------------------------------------

/**
 * Promote a design entry to Expert DB when score >= 0.6.
 * Reads from base collection and copies to expert collection via db-client.
 *
 * @param {string} genre - Lowercase genre directory
 * @param {string} domain - Lowercase domain directory
 * @param {string} designId - Design entry ID
 * @returns {Promise<{ error: string|null }>}
 */
async function promoteToExpert(genre, domain, designId) {
  // Read source data from base collection
  const detail = await getDesign(designId, false);
  if (!detail) {
    return { error: `Design not found in DB: ${designId}` };
  }

  if ((detail.score || 0) < EXPERT_THRESHOLD) {
    return { error: `Score ${detail.score} below threshold ${EXPERT_THRESHOLD}` };
  }

  // Promote to expert collection via db-client
  await promoteDesignToExpert(designId);

  return { error: null };
}

module.exports = {
  SCORE_EVENTS,
  EXPERT_THRESHOLD,
  updateScore,
  promoteToExpert,
};
