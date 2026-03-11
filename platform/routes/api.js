const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const archiver = require('archiver');
const { getDb } = require('../lib/db');
const { logActivity } = require('../lib/logger');
const { requireAdmin } = require('../lib/auth');
const { spawn } = require('child_process');
const router = express.Router();

const upload = multer({
  dest: path.join(__dirname, '..', 'temp', 'uploads'),
  limits: { fileSize: 50 * 1024 * 1024 }
});

// ============================================================
// Design API
// ============================================================

// Search design DB
router.get('/design/search', async (req, res) => {
  try {
    const db = getDb();
    const { genre, domain, system, minScore, source, limit = 50 } = req.query;
    const query = {};

    if (genre && genre !== 'all') query.genre = new RegExp(genre, 'i');
    if (domain && domain !== 'all') query.domain = new RegExp(domain, 'i');
    if (system) query.system = new RegExp(system, 'i');
    if (source) query.source = source;
    if (minScore) query.score = { $gte: parseFloat(minScore) };

    // Search expert first, then base
    const expertResults = await db.collection('design_expert')
      .find(query).sort({ score: -1 }).limit(parseInt(limit)).toArray();
    const baseResults = await db.collection('design_base')
      .find(query).sort({ score: -1 }).limit(parseInt(limit)).toArray();

    // Mark source collection
    expertResults.forEach(r => r._source = 'expert');
    baseResults.forEach(r => r._source = 'base');

    // Merge, expert first, deduplicate by designId
    const seen = new Set();
    const merged = [];
    for (const r of [...expertResults, ...baseResults]) {
      const key = r.designId || r._id.toString();
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(r);
      }
    }

    res.json({ results: merged.slice(0, parseInt(limit)), total: merged.length });
  } catch (err) {
    console.error('Design search error:', err);
    res.status(500).json({ error: err.message });
  }
});

// Get single design detail
router.get('/design/:id', async (req, res) => {
  try {
    const db = getDb();
    const { ObjectId } = require('mongodb');
    let doc = null;

    try {
      doc = await db.collection('design_expert').findOne({ _id: new ObjectId(req.params.id) });
    } catch (e) { /* not ObjectId format */ }

    if (!doc) {
      doc = await db.collection('design_expert').findOne({ designId: req.params.id });
    }
    if (!doc) {
      try {
        doc = await db.collection('design_base').findOne({ _id: new ObjectId(req.params.id) });
      } catch (e) { /* not ObjectId format */ }
    }
    if (!doc) {
      doc = await db.collection('design_base').findOne({ designId: req.params.id });
    }

    if (!doc) return res.status(404).json({ error: 'Not found' });
    res.json(doc);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Generate design
router.post('/design/generate', async (req, res) => {
  try {
    const { prompt, genre, stages, references } = req.body;
    const user = req.session.user;

    await logActivity(user.id, user.username, 'design', 'Design generation started', {
      genre, stages, promptLength: prompt?.length
    });

    const db = getDb();

    if (user.isAdmin) {
      // Admin: direct task queue
      const task = {
        type: 'design_generate',
        status: 'queued',
        input: { prompt, genre, stages, references },
        userId: user.id,
        username: user.username,
        createdAt: new Date(),
        results: []
      };
      const result = await db.collection('tasks').insertOne(task);
      res.json({ success: true, taskId: result.insertedId.toString(), message: 'Design generation task queued' });
    } else {
      // Non-admin: submit for review
      const pendingDoc = {
        type: 'design',
        category: 'generation',
        targetCollection: 'design_base',
        status: 'pending',
        data: { prompt, genre, stages, references, source: 'generated' },
        submittedBy: user.username,
        submittedById: user.id,
        createdAt: new Date()
      };
      const result = await db.collection('pending').insertOne(pendingDoc);
      res.json({ success: true, taskId: result.insertedId.toString(), message: 'Submitted for admin review' });
    }
  } catch (err) {
    console.error('Design generate error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// Code/System API
// ============================================================

// Search code DB
router.get('/code/search', async (req, res) => {
  try {
    const db = getDb();
    const { genre, layer, role, system, minScore, limit = 50 } = req.query;
    const query = {};

    if (genre && genre !== 'all') query.genre = new RegExp(genre, 'i');
    if (layer && layer !== 'all') query.layer = new RegExp(layer, 'i');
    if (role && role !== 'all') query.role = new RegExp(role, 'i');
    if (system) query.system = new RegExp(system, 'i');
    if (minScore) query.score = { $gte: parseFloat(minScore) };

    const expertResults = await db.collection('code_expert')
      .find(query).sort({ score: -1 }).limit(parseInt(limit)).toArray();
    const baseResults = await db.collection('code_base')
      .find(query).sort({ score: -1 }).limit(parseInt(limit)).toArray();

    expertResults.forEach(r => r._source = 'expert');
    baseResults.forEach(r => r._source = 'base');

    const seen = new Set();
    const merged = [];
    for (const r of [...expertResults, ...baseResults]) {
      const key = r.fileId || r._id.toString();
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(r);
      }
    }

    res.json({ results: merged.slice(0, parseInt(limit)), total: merged.length });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Generate code
router.post('/code/generate', upload.array('designFiles', 20), async (req, res) => {
  try {
    const { genre, engine, resolution, selectedDbIds, prompt } = req.body;
    const user = req.session.user;
    const files = req.files || [];

    await logActivity(user.id, user.username, 'system', 'Code generation started', {
      genre, engine, resolution, fileCount: files.length
    });

    const db = getDb();

    if (user.isAdmin) {
      const task = {
        type: 'code_generate',
        status: 'queued',
        input: { genre, engine, resolution, selectedDbIds: JSON.parse(selectedDbIds || '[]'), prompt },
        uploadedFiles: files.map(f => ({ originalName: f.originalname, path: f.path, size: f.size })),
        userId: user.id,
        username: user.username,
        createdAt: new Date(),
        results: []
      };
      const result = await db.collection('tasks').insertOne(task);
      res.json({ success: true, taskId: result.insertedId.toString(), message: 'Code generation task queued' });
    } else {
      const pendingDoc = {
        type: 'code',
        category: 'generation',
        targetCollection: 'code_base',
        status: 'pending',
        data: {
          genre, engine, resolution,
          selectedDbIds: JSON.parse(selectedDbIds || '[]'),
          prompt,
          uploadedFiles: files.map(f => ({ originalName: f.originalname, path: f.path, size: f.size })),
          source: 'generated'
        },
        submittedBy: user.username,
        submittedById: user.id,
        createdAt: new Date()
      };
      const result = await db.collection('pending').insertOne(pendingDoc);
      res.json({ success: true, taskId: result.insertedId.toString(), message: 'Submitted for admin review' });
    }
  } catch (err) {
    console.error('Code generate error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// Embedding API
// ============================================================

// Upload and parse files for embedding (all users can parse, commit is gated)
router.post('/embedding/parse', upload.array('files', 100), async (req, res) => {
  try {
    const files = req.files || [];
    const parsed = [];

    for (const file of files) {
      const content = fs.readFileSync(file.path, 'utf-8');
      const ext = path.extname(file.originalname).toLowerCase();
      const info = {
        filename: file.originalname,
        size: file.size,
        ext,
        path: file.path
      };

      if (ext === '.cs') {
        // Detect C# patterns
        const classMatch = content.match(/class\s+(\w+)/g);
        const namespaceMatch = content.match(/namespace\s+([\w.]+)/);
        info.type = 'C# Source';
        info.classes = classMatch ? classMatch.map(c => c.replace('class ', '')) : [];
        info.namespace = namespaceMatch ? namespaceMatch[1] : null;
        info.targetDb = 'code_base';

        // Auto-detect layer/genre/role
        info.detectedLayer = detectLayer(content, file.originalname);
        info.detectedRole = detectRole(file.originalname);
        info.detectedGenre = 'Generic';
      } else if (['.yaml', '.yml'].includes(ext)) {
        info.type = 'Design Document';
        info.targetDb = 'design_base';
        info.detectedDomain = detectDomain(content);
        info.detectedGenre = 'Generic';
      } else if (ext === '.json') {
        info.type = 'JSON Data';
        info.targetDb = 'design_base';
        info.detectedDomain = detectDomain(content);
        info.detectedGenre = 'Generic';
      } else {
        info.type = 'Unknown';
        info.targetDb = 'design_base';
      }

      parsed.push(info);
    }

    res.json({ files: parsed });
  } catch (err) {
    console.error('Parse error:', err);
    res.status(500).json({ error: err.message });
  }
});

// Commit parsed files to MongoDB
// Admin → direct insert, Non-admin → pending queue
router.post('/embedding/commit', async (req, res) => {
  try {
    const { files } = req.body;
    const user = req.session.user;
    const db = getDb();
    const isAdmin = user.isAdmin;
    let codeCount = 0, designCount = 0, pendingCount = 0;

    for (const file of files) {
      let content = '';
      try { content = fs.readFileSync(file.path, 'utf-8'); } catch (e) { content = file.content || ''; }
      const targetDb = file.targetDb || 'code_base';

      const docData = targetDb === 'code_base' ? {
        fileId: path.basename(file.filename, path.extname(file.filename)),
        filename: file.filename,
        layer: file.layer || file.detectedLayer || 'Game',
        genre: file.genre || file.detectedGenre || 'Generic',
        role: file.role || file.detectedRole || 'Helper',
        system: file.system || '',
        score: 0.4,
        content: content,
        source: 'uploaded',
        createdAt: new Date(),
        uploadedBy: user.username
      } : {
        designId: path.basename(file.filename, path.extname(file.filename)),
        filename: file.filename,
        domain: file.domain || file.detectedDomain || 'InGame',
        genre: file.genre || file.detectedGenre || 'Generic',
        system: file.system || '',
        data_type: file.data_type || 'config',
        score: 0.4,
        content: content,
        source: 'uploaded',
        createdAt: new Date(),
        uploadedBy: user.username
      };

      if (isAdmin) {
        // Admin: direct insert
        await db.collection(targetDb).insertOne(docData);
        if (targetDb === 'code_base') codeCount++; else designCount++;
      } else {
        // Non-admin: queue for review
        await db.collection('pending').insertOne({
          type: targetDb === 'code_base' ? 'code' : 'design',
          category: 'embedding',
          targetCollection: targetDb,
          status: 'pending',
          data: docData,
          submittedBy: user.username,
          submittedById: user.id,
          createdAt: new Date()
        });
        pendingCount++;
      }
    }

    // Cleanup temp files
    for (const file of files) {
      try { fs.unlinkSync(file.path); } catch (e) { /* ignore */ }
    }

    if (isAdmin) {
      await logActivity(user.id, user.username, 'embedding', `Direct upload: ${codeCount + designCount} files`, { codeCount, designCount });
      res.json({ success: true, codeCount, designCount, message: 'Files uploaded directly to DB' });
    } else {
      await logActivity(user.id, user.username, 'embedding', `Submitted ${pendingCount} files for review`, { pendingCount });
      res.json({ success: true, pendingCount, message: `${pendingCount} files submitted for admin review` });
    }
  } catch (err) {
    console.error('Commit error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// Review/Pending API
// ============================================================

// Get pending items
// Admin: all items (filterable by status)
// Non-admin: own submissions only (all statuses)
router.get('/pending', async (req, res) => {
  try {
    const db = getDb();
    const user = req.session.user;
    const { status = 'all' } = req.query;
    const query = {};

    if (user.isAdmin) {
      if (status && status !== 'all') query.status = status;
    } else {
      // Non-admin: own submissions only
      query.submittedById = user.id;
      if (status && status !== 'all') query.status = status;
    }

    const items = await db.collection('pending')
      .find(query)
      .sort({ createdAt: -1 })
      .limit(100)
      .toArray();
    res.json({ items, isAdmin: user.isAdmin });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Approve (admin only)
router.post('/pending/:id/approve', requireAdmin, async (req, res) => {
  try {
    const db = getDb();
    const { ObjectId } = require('mongodb');
    const item = await db.collection('pending').findOne({ _id: new ObjectId(req.params.id) });
    if (!item) return res.status(404).json({ error: 'Not found' });

    // Determine target collection
    const targetCollection = item.targetCollection || (item.type === 'code' ? 'code_base' : 'design_base');
    const doc = { ...item.data, score: item.data.score || 0.4, approvedAt: new Date(), approvedBy: req.session.user.username };
    delete doc._id;
    await db.collection(targetCollection).insertOne(doc);

    await db.collection('pending').updateOne(
      { _id: new ObjectId(req.params.id) },
      { $set: { status: 'approved', reviewedAt: new Date(), reviewedBy: req.session.user.username } }
    );

    await logActivity(req.session.user.id, req.session.user.username, 'review',
      `Approved: ${item.data?.designId || item.data?.fileId || item.data?.filename || req.params.id}`,
      { submittedBy: item.submittedBy, targetCollection });

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Reject (admin only)
router.post('/pending/:id/reject', requireAdmin, async (req, res) => {
  try {
    const db = getDb();
    const { ObjectId } = require('mongodb');
    const { reason } = req.body;

    const item = await db.collection('pending').findOne({ _id: new ObjectId(req.params.id) });
    if (!item) return res.status(404).json({ error: 'Not found' });

    await db.collection('pending').updateOne(
      { _id: new ObjectId(req.params.id) },
      { $set: { status: 'rejected', rejectReason: reason || '', reviewedAt: new Date(), reviewedBy: req.session.user.username } }
    );

    await logActivity(req.session.user.id, req.session.user.username, 'review',
      `Rejected: ${item.data?.designId || item.data?.fileId || item.data?.filename || req.params.id}`,
      { reason, submittedBy: item.submittedBy });

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Update reject reason (admin only)
router.patch('/pending/:id/reason', requireAdmin, async (req, res) => {
  try {
    const db = getDb();
    const { ObjectId } = require('mongodb');
    const { reason } = req.body;

    await db.collection('pending').updateOne(
      { _id: new ObjectId(req.params.id) },
      { $set: { rejectReason: reason, reasonUpdatedAt: new Date(), reasonUpdatedBy: req.session.user.username } }
    );

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// Activity Logs API
// ============================================================

router.get('/logs', async (req, res) => {
  try {
    const db = getDb();
    const { startDate, endDate, userId, type, limit = 100 } = req.query;
    const query = {};

    if (startDate || endDate) {
      query.timestamp = {};
      if (startDate) query.timestamp.$gte = new Date(startDate);
      if (endDate) {
        const end = new Date(endDate);
        end.setHours(23, 59, 59, 999);
        query.timestamp.$lte = end;
      }
    }
    if (userId && userId !== 'all') query.userId = userId;
    if (type && type !== 'all') query.type = type;

    const logs = await db.collection('activity_logs')
      .find(query)
      .sort({ timestamp: -1 })
      .limit(parseInt(limit))
      .toArray();

    // Get unique users for filter dropdown
    const users = await db.collection('activity_logs').distinct('username');

    res.json({ logs, users });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// Stats API
// ============================================================

router.get('/stats', async (req, res) => {
  try {
    const db = getDb();
    const [codeBase, codeExpert, designBase, designExpert, rules, pending] = await Promise.all([
      db.collection('code_base').countDocuments(),
      db.collection('code_expert').countDocuments(),
      db.collection('design_base').countDocuments(),
      db.collection('design_expert').countDocuments(),
      db.collection('rules').countDocuments(),
      db.collection('pending').countDocuments({ status: 'pending' })
    ]);
    res.json({ codeBase, codeExpert, designBase, designExpert, rules, pending });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// Download as ZIP
// ============================================================

router.post('/download/zip', async (req, res) => {
  try {
    const { files, zipName = 'download' } = req.body;
    if (!files || !files.length) return res.status(400).json({ error: 'No files to download' });

    res.setHeader('Content-Type', 'application/zip');
    res.setHeader('Content-Disposition', `attachment; filename="${zipName}.zip"`);

    const archive = archiver('zip', { zlib: { level: 9 } });
    archive.pipe(res);

    for (const file of files) {
      archive.append(file.content, { name: file.name });
    }

    await archive.finalize();
  } catch (err) {
    console.error('ZIP error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// Users Management API (Admin only)
// ============================================================

router.get('/users', requireAdmin, async (req, res) => {
  try {
    const db = getDb();
    const { search } = req.query;
    const query = {};

    if (search) {
      query.$or = [
        { username: new RegExp(search, 'i') },
        { displayName: new RegExp(search, 'i') }
      ];
    }

    const users = await db.collection('users')
      .find(query, { projection: { password: 0 } })
      .sort({ createdAt: -1 })
      .toArray();

    res.json({ users });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.patch('/users/:id/role', requireAdmin, async (req, res) => {
  try {
    const db = getDb();
    const { ObjectId } = require('mongodb');
    const { isAdmin } = req.body;
    const userId = req.params.id;

    // Prevent demoting the default admin
    const target = await db.collection('users').findOne({ _id: new ObjectId(userId) });
    if (!target) return res.status(404).json({ error: 'User not found' });
    if (target.username === 'admin' && !isAdmin) {
      return res.status(400).json({ error: 'Cannot demote the default admin' });
    }

    await db.collection('users').updateOne(
      { _id: new ObjectId(userId) },
      { $set: { isAdmin: !!isAdmin } }
    );

    await logActivity(req.session.user.id, req.session.user.username, 'auth',
      `${isAdmin ? 'Promoted' : 'Demoted'} user: ${target.username}`);

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.patch('/users/:id/block', requireAdmin, async (req, res) => {
  try {
    const db = getDb();
    const { ObjectId } = require('mongodb');
    const { isBlocked } = req.body;
    const userId = req.params.id;

    const target = await db.collection('users').findOne({ _id: new ObjectId(userId) });
    if (!target) return res.status(404).json({ error: 'User not found' });
    if (target.username === 'admin') {
      return res.status(400).json({ error: 'Cannot block the default admin' });
    }

    await db.collection('users').updateOne(
      { _id: new ObjectId(userId) },
      { $set: { isBlocked: !!isBlocked, blockedAt: isBlocked ? new Date() : null, blockedBy: isBlocked ? req.session.user.username : null } }
    );

    await logActivity(req.session.user.id, req.session.user.username, 'auth',
      `${isBlocked ? 'Blocked' : 'Unblocked'} user: ${target.username}`);

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.delete('/users/:id', requireAdmin, async (req, res) => {
  try {
    const db = getDb();
    const { ObjectId } = require('mongodb');
    const userId = req.params.id;

    const target = await db.collection('users').findOne({ _id: new ObjectId(userId) });
    if (!target) return res.status(404).json({ error: 'User not found' });
    if (target.username === 'admin') {
      return res.status(400).json({ error: 'Cannot delete the default admin' });
    }

    await db.collection('users').deleteOne({ _id: new ObjectId(userId) });

    await logActivity(req.session.user.id, req.session.user.username, 'auth',
      `Deleted user: ${target.username}`);

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ============================================================
// Helper functions
// ============================================================

function detectLayer(content, filename) {
  const lcContent = content.toLowerCase();
  const lcName = filename.toLowerCase();
  if (lcContent.includes('singleton') || lcName.includes('base') || lcName.includes('util') || lcName.includes('pool')) return 'Core';
  if (lcContent.includes('partial class') || lcName.includes('page') || lcName.includes('popup')) return 'Game';
  return 'Domain';
}

function detectRole(filename) {
  const name = filename.replace(/\.[^.]+$/, '');
  const rolePatterns = [
    [/Manager$/i, 'Manager'], [/Controller$/i, 'Controller'], [/Calculator$/i, 'Calculator'],
    [/Processor$/i, 'Processor'], [/Handler$/i, 'Handler'], [/Listener$/i, 'Listener'],
    [/Provider$/i, 'Provider'], [/Factory$/i, 'Factory'], [/Service$/i, 'Service'],
    [/Validator$/i, 'Validator'], [/Converter$/i, 'Converter'], [/Builder$/i, 'Builder'],
    [/Pool$/i, 'Pool'], [/State$/i, 'State'], [/Command$/i, 'Command'],
    [/Observer$/i, 'Observer'], [/Helper$/i, 'Helper'], [/Wrapper$/i, 'Wrapper'],
    [/Context$/i, 'Context'], [/Config$/i, 'Config'], [/Effect$/i, 'UX']
  ];
  for (const [pattern, role] of rolePatterns) {
    if (pattern.test(name)) return role;
  }
  return 'Helper';
}

function detectDomain(content) {
  const lc = content.toLowerCase();
  const domainKeywords = {
    'InGame': ['battle', 'combat', 'skill', 'character', 'stage', 'enemy'],
    'OutGame': ['inventory', 'shop', 'item', 'equipment', 'gacha'],
    'Balance': ['formula', 'growth', 'curve', 'economy', 'rate'],
    'Content': ['quest', 'mission', 'level', 'reward', 'dungeon'],
    'BM': ['purchase', 'package', 'iap', 'price', 'subscription'],
    'LiveOps': ['event', 'season', 'update', 'maintenance'],
    'UX': ['ui', 'tutorial', 'flow', 'navigation', 'hud'],
    'Social': ['guild', 'pvp', 'friend', 'chat', 'clan'],
    'Meta': ['achievement', 'collection', 'badge', 'rank']
  };
  let bestDomain = 'InGame';
  let bestCount = 0;
  for (const [domain, keywords] of Object.entries(domainKeywords)) {
    const count = keywords.filter(k => lc.includes(k)).length;
    if (count > bestCount) { bestCount = count; bestDomain = domain; }
  }
  return bestDomain;
}

module.exports = router;
