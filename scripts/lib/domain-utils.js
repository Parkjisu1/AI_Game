/**
 * domain-utils.js - Unified domain/genre normalization
 * Fixes root cause of "combat"/"economy" being stored as invalid domain entries.
 *
 * Usage:
 *   const { normalizeDomain, displayDomain, normalizeGenre, displayGenre,
 *           VALID_DOMAINS, VALID_GENRES, C10_DOMAIN_MAP } = require('./lib/domain-utils');
 */

'use strict';

// ---------------------------------------------------------------------------
// Valid domains & genres (canonical lowercase for directories)
// ---------------------------------------------------------------------------

const VALID_DOMAINS = [
  'ingame', 'outgame', 'balance', 'content', 'bm',
  'liveops', 'ux', 'social', 'meta', 'projects',
];

const VALID_GENRES = [
  'generic', 'rpg', 'idle', 'merge', 'slg',
  'tycoon', 'simulation', 'puzzle', 'casual', 'playable',
];

// ---------------------------------------------------------------------------
// Domain normalization: raw input → canonical lowercase
// ---------------------------------------------------------------------------

const DOMAIN_ALIAS_MAP = {
  // Standard forms
  ingame: 'ingame',
  in_game: 'ingame',
  'in-game': 'ingame',
  outgame: 'outgame',
  out_game: 'outgame',
  'out-game': 'outgame',
  balance: 'balance',
  content: 'content',
  bm: 'bm',
  business_model: 'bm',
  monetization: 'bm',
  liveops: 'liveops',
  live_ops: 'liveops',
  'live-ops': 'liveops',
  ux: 'ux',
  social: 'social',
  meta: 'meta',
  projects: 'projects',

  // Common mis-classifications from C10+ / design-parser
  combat: 'ingame',
  battle: 'ingame',
  fight: 'ingame',
  economy: 'balance',
  currency: 'balance',
  gold: 'balance',
  gacha: 'bm',
  shop: 'outgame',
  inventory: 'outgame',
  equipment: 'outgame',
  quest: 'content',
  stage: 'content',
  tutorial: 'ux',
  guild: 'social',
  pvp: 'social',
  achievement: 'meta',
  collection: 'meta',
  event: 'liveops',
  season: 'liveops',
};

// Display names for JSON (capitalized)
const DOMAIN_DISPLAY_MAP = {
  ingame: 'InGame',
  outgame: 'OutGame',
  balance: 'Balance',
  content: 'Content',
  bm: 'BM',
  liveops: 'LiveOps',
  ux: 'UX',
  social: 'Social',
  meta: 'Meta',
  projects: 'Projects',
};

/**
 * Normalize a raw domain string to canonical lowercase.
 * Returns 'ingame' as default if unrecognized.
 * @param {string} raw - Raw domain input
 * @returns {string} Canonical lowercase domain
 */
function normalizeDomain(raw) {
  if (!raw) return 'ingame';
  const lower = raw.toLowerCase().trim();
  if (DOMAIN_ALIAS_MAP[lower]) return DOMAIN_ALIAS_MAP[lower];
  // Check if already a valid domain
  if (VALID_DOMAINS.includes(lower)) return lower;
  return 'ingame'; // safe default
}

/**
 * Get display name for a normalized domain (for JSON fields).
 * @param {string} normalized - Canonical lowercase domain
 * @returns {string} Display name (e.g., "InGame", "OutGame")
 */
function displayDomain(normalized) {
  return DOMAIN_DISPLAY_MAP[normalized] || DOMAIN_DISPLAY_MAP[normalizeDomain(normalized)] || 'InGame';
}

// ---------------------------------------------------------------------------
// Genre normalization
// ---------------------------------------------------------------------------

/**
 * Normalize genre to lowercase (for directory names).
 * @param {string} raw - Raw genre input
 * @returns {string} Lowercase genre
 */
function normalizeGenre(raw) {
  if (!raw) return 'generic';
  const lower = raw.toLowerCase().trim();
  if (VALID_GENRES.includes(lower)) return lower;
  return 'generic';
}

/**
 * Get display name for genre (capitalized for JSON).
 * @param {string} normalized - Lowercase genre
 * @returns {string} Display genre (e.g., "Rpg", "Idle")
 */
function displayGenre(normalized) {
  const g = normalized || 'generic';
  if (g === 'slg') return 'SLG';
  if (g === 'rpg') return 'RPG';
  return g.charAt(0).toUpperCase() + g.slice(1).toLowerCase();
}

// ---------------------------------------------------------------------------
// C10+ parameter → domain[] mapping (for design-parser, c10-to-design-db)
// ---------------------------------------------------------------------------

const C10_DOMAIN_MAP = {
  progression: ['content', 'balance'],
  growth: ['balance'],
  equipment: ['outgame', 'balance'],
  combat: ['ingame', 'balance'],
  gacha: ['outgame', 'bm'],
  economy: ['balance', 'bm'],
  system: ['ingame'],
  visual: ['ux'],
  architecture: null, // skip
  ui: ['ux'],
  shop: ['outgame', 'bm'],
  quest: ['content'],
  skill: ['ingame'],
  map: ['ingame'],
  pvp: ['ingame'],
  guild: ['social'],
  event: ['liveops'],
  season: ['liveops'],
  achievement: ['content'],
  leaderboard: ['social'],
  tutorial: ['ux'],
  notification: ['liveops'],
};

module.exports = {
  VALID_DOMAINS,
  VALID_GENRES,
  normalizeDomain,
  displayDomain,
  normalizeGenre,
  displayGenre,
  C10_DOMAIN_MAP,
  DOMAIN_ALIAS_MAP,
};
