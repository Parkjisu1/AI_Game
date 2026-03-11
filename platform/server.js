require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const express = require('express');
const session = require('express-session');
const path = require('path');
const { connectDb, getDb } = require('./lib/db');
const { requireAuth, requireAdmin } = require('./lib/auth');

const app = express();
const PORT = process.env.PLATFORM_PORT || 3000;

// View engine
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// Middleware
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));
app.use(express.static(path.join(__dirname, 'public')));
app.use('/uploads', express.static(path.join(__dirname, 'public', 'uploads')));

app.use(session({
  secret: process.env.SESSION_SECRET || 'gameforge-secret-2026',
  resave: false,
  saveUninitialized: false,
  cookie: { maxAge: 24 * 60 * 60 * 1000 }
}));

// Make user available in all views
app.use((req, res, next) => {
  res.locals.user = req.session.user || null;
  res.locals.currentPath = req.path;
  next();
});

// Page routes
app.get('/login', (req, res) => {
  if (req.session.user) return res.redirect('/');
  res.render('login', { error: null });
});

app.get('/', requireAuth, async (req, res) => {
  try {
    const db = getDb();
    const [codeBaseCount, codeExpertCount, designBaseCount, designExpertCount, rulesCount, pendingCount, recentLogs] = await Promise.all([
      db.collection('code_base').countDocuments(),
      db.collection('code_expert').countDocuments(),
      db.collection('design_base').countDocuments(),
      db.collection('design_expert').countDocuments(),
      db.collection('rules').countDocuments(),
      db.collection('pending').countDocuments({ status: 'pending' }),
      db.collection('activity_logs').find().sort({ timestamp: -1 }).limit(10).toArray()
    ]);

    // Genre distribution
    const genreAgg = await db.collection('code_base').aggregate([
      { $group: { _id: '$genre', count: { $sum: 1 } } },
      { $sort: { count: -1 } }
    ]).toArray();

    const designGenreAgg = await db.collection('design_base').aggregate([
      { $group: { _id: '$genre', count: { $sum: 1 } } },
      { $sort: { count: -1 } }
    ]).toArray();

    res.render('dashboard', {
      stats: { codeBaseCount, codeExpertCount, designBaseCount, designExpertCount, rulesCount, pendingCount },
      genreDistribution: genreAgg,
      designGenreDistribution: designGenreAgg,
      recentLogs
    });
  } catch (err) {
    console.error('Dashboard error:', err);
    res.render('dashboard', {
      stats: { codeBaseCount: 0, codeExpertCount: 0, designBaseCount: 0, designExpertCount: 0, rulesCount: 0, pendingCount: 0 },
      genreDistribution: [],
      designGenreDistribution: [],
      recentLogs: []
    });
  }
});

app.get('/design', requireAuth, (req, res) => res.render('design'));
app.get('/system', requireAuth, (req, res) => res.render('system'));
app.get('/embedding', requireAuth, (req, res) => res.render('embedding'));
app.get('/review', requireAuth, (req, res) => res.render('review'));
app.get('/log', requireAuth, (req, res) => res.render('log'));
app.get('/users', requireAuth, requireAdmin, (req, res) => res.render('users'));

// API routes
app.use('/api/auth', require('./routes/auth'));
app.use('/api', requireAuth, require('./routes/api'));

// Error handler
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});

// Start
(async () => {
  try {
    await connectDb();
    console.log('MongoDB connected');

    // Ensure default admin exists
    const { ensureAdmin } = require('./lib/auth');
    await ensureAdmin();

    app.listen(PORT, () => {
      console.log(`GameForge Platform running at http://localhost:${PORT}`);
    });
  } catch (err) {
    console.error('Failed to start:', err);
    process.exit(1);
  }
})();
