const { getDb } = require('./db');

async function logActivity(userId, username, type, action, details = {}) {
  try {
    const db = getDb();
    await db.collection('activity_logs').insertOne({
      userId,
      username,
      type,       // 'design' | 'system' | 'embedding' | 'review' | 'auth'
      action,     // Human-readable action description
      details,    // Additional data (inputs, outputs, counts, etc.)
      timestamp: new Date()
    });
  } catch (err) {
    console.error('Failed to log activity:', err.message);
  }
}

module.exports = { logActivity };
