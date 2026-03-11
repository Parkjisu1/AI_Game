const express = require('express');
const bcrypt = require('bcryptjs');
const { getDb } = require('../lib/db');
const { logActivity } = require('../lib/logger');
const router = express.Router();

router.post('/login', async (req, res) => {
  try {
    const { username, password } = req.body;
    if (!username || !password) {
      return res.status(400).json({ error: 'Username and password required' });
    }

    const db = getDb();
    const user = await db.collection('users').findOne({ username });
    if (!user || !(await bcrypt.compare(password, user.password))) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    if (user.isBlocked) {
      return res.status(403).json({ error: 'Account is blocked. Contact an administrator.' });
    }

    req.session.user = {
      id: user._id.toString(),
      username: user.username,
      displayName: user.displayName,
      isAdmin: user.isAdmin || false,
      isBlocked: false
    };

    await logActivity(user._id.toString(), user.username, 'auth', 'Login');
    res.json({ success: true, redirect: '/' });
  } catch (err) {
    console.error('Login error:', err);
    res.status(500).json({ error: 'Server error' });
  }
});

router.post('/logout', (req, res) => {
  req.session.destroy();
  res.json({ success: true, redirect: '/login' });
});

router.post('/register', async (req, res) => {
  try {
    const { username, password, displayName } = req.body;
    if (!username || !password) {
      return res.status(400).json({ error: 'Username and password required' });
    }

    const db = getDb();
    const exists = await db.collection('users').findOne({ username });
    if (exists) {
      return res.status(409).json({ error: 'Username already exists' });
    }

    const hash = await bcrypt.hash(password, 10);
    await db.collection('users').insertOne({
      username,
      password: hash,
      displayName: displayName || username,
      isAdmin: false,
      isBlocked: false,
      createdAt: new Date()
    });

    res.json({ success: true });
  } catch (err) {
    console.error('Register error:', err);
    res.status(500).json({ error: 'Server error' });
  }
});

module.exports = router;
