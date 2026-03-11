const bcrypt = require('bcryptjs');
const { getDb } = require('./db');

function requireAuth(req, res, next) {
  if (!req.session.user) {
    if (req.xhr || req.path.startsWith('/api')) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
    return res.redirect('/login');
  }
  // Check if user is blocked (session might be stale)
  if (req.session.user.isBlocked) {
    req.session.destroy();
    if (req.xhr || req.path.startsWith('/api')) {
      return res.status(403).json({ error: 'Account blocked' });
    }
    return res.redirect('/login');
  }
  next();
}

function requireAdmin(req, res, next) {
  if (!req.session.user || !req.session.user.isAdmin) {
    if (req.xhr || req.path.startsWith('/api')) {
      return res.status(403).json({ error: 'Admin access required' });
    }
    return res.status(403).send('Admin access required');
  }
  next();
}

async function ensureAdmin() {
  const db = getDb();
  const users = db.collection('users');
  const admin = await users.findOne({ username: 'admin' });
  if (!admin) {
    const hash = await bcrypt.hash('gameforge2026', 10);
    await users.insertOne({
      username: 'admin',
      password: hash,
      displayName: 'Admin',
      isAdmin: true,
      isBlocked: false,
      createdAt: new Date()
    });
    console.log('Default admin created (admin / gameforge2026)');
  }
}

module.exports = { requireAuth, requireAdmin, ensureAdmin };
