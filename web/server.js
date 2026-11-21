// Minimal demo server: serves the flood map, a demo login, and community help requests.
// NOTE: login is display-name only. There is no real authentication, by design.
const express = require('express');
const cookieParser = require('cookie-parser');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const MAP_DIR = path.join(__dirname, '..', 'oakland-flood-vulnerability', 'outputs');
const PUBLIC_DIR = path.join(__dirname, 'public');
const DB_FILE = process.env.DB_FILE || path.join(__dirname, 'data', 'db.json');

const CATEGORIES = ['flooding', 'sandbags', 'evacuation', 'cleanup', 'supplies', 'other'];
const BOUNDS = { minLat: 37.69, maxLat: 37.89, minLng: -122.36, maxLng: -122.11 };
const INJECT = '<link rel="stylesheet" href="/app/community.css"><script src="/app/community.js"></script>';

// ---- storage ----
let db = { users: [], requests: [] };
if (fs.existsSync(DB_FILE)) {
  db = JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
} else {
  save();
}
function save() {
  fs.mkdirSync(path.dirname(DB_FILE), { recursive: true });
  fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2));
}

const app = express();
app.use(express.json());
app.use(cookieParser());

// ---- pages ----
app.get('/', (req, res) => res.redirect('/flood_vulnerability_map.html'));

let mapHtml = null;
app.get('/flood_vulnerability_map.html', (req, res) => {
  if (!mapHtml) {
    const html = fs.readFileSync(path.join(MAP_DIR, 'flood_vulnerability_map.html'), 'utf8');
    const i = html.lastIndexOf('</body>');
    mapHtml = i === -1 ? html + INJECT : html.slice(0, i) + INJECT + html.slice(i);
  }
  res.type('html').send(mapHtml);
});

app.get('/login', (req, res) => res.sendFile(path.join(PUBLIC_DIR, 'login.html')));
app.use('/app', express.static(PUBLIC_DIR));
app.use(express.static(MAP_DIR));

// ---- demo login ----
function currentUser(req) {
  const id = req.cookies.fw_user;
  return db.users.find((u) => u.id === id) || null;
}
function requireUser(req, res, next) {
  req.user = currentUser(req);
  if (!req.user) return res.status(401).json({ error: 'Log in first' });
  next();
}

app.post('/api/login', (req, res) => {
  const name = String((req.body || {}).name || '').trim();
  if (name.length < 1 || name.length > 40) {
    return res.status(400).json({ error: 'Name must be 1-40 characters' });
  }
  let user = db.users.find((u) => u.name.toLowerCase() === name.toLowerCase());
  if (!user) {
    user = { id: crypto.randomUUID(), name, createdAt: new Date().toISOString() };
    db.users.push(user);
    save();
  }
  res.cookie('fw_user', user.id, {
    httpOnly: true, sameSite: 'lax', path: '/', maxAge: 30 * 24 * 60 * 60 * 1000,
  });
  res.json({ user });
});

app.post('/api/logout', (req, res) => {
  res.clearCookie('fw_user', { path: '/' });
  res.json({ ok: true });
});

app.get('/api/me', (req, res) => res.json({ user: currentUser(req) }));

// ---- help requests ----
app.get('/api/requests', (req, res) => {
  const requests = [...db.requests].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  res.json({ requests });
});

app.post('/api/requests', requireUser, (req, res) => {
  const { lat, lng, category, details, people = 1 } = req.body || {};
  if (typeof lat !== 'number' || lat < BOUNDS.minLat || lat > BOUNDS.maxLat ||
      typeof lng !== 'number' || lng < BOUNDS.minLng || lng > BOUNDS.maxLng) {
    return res.status(400).json({ error: 'Location must be inside Oakland' });
  }
  if (!CATEGORIES.includes(category)) {
    return res.status(400).json({ error: 'Invalid category' });
  }
  const text = typeof details === 'string' ? details.trim() : '';
  if (!text || text.length > 500) {
    return res.status(400).json({ error: 'Details are required (max 500 characters)' });
  }
  if (!Number.isInteger(people) || people < 1 || people > 50) {
    return res.status(400).json({ error: 'People must be a whole number from 1 to 50' });
  }
  const now = new Date().toISOString();
  const request = {
    id: crypto.randomUUID(), lat, lng, category, details: text, people,
    status: 'open', requesterId: req.user.id, requesterName: req.user.name,
    volunteers: [], createdAt: now, updatedAt: now,
  };
  db.requests.push(request);
  save();
  res.status(201).json({ request });
});

app.post('/api/requests/:id/volunteer', requireUser, (req, res) => {
  const request = db.requests.find((r) => r.id === req.params.id);
  if (!request) return res.status(404).json({ error: 'Request not found' });
  if (request.requesterId === req.user.id) {
    return res.status(400).json({ error: 'You cannot volunteer for your own request' });
  }
  if (request.status === 'resolved') {
    return res.status(400).json({ error: 'This request is already resolved' });
  }
  if (!request.volunteers.some((v) => v.userId === req.user.id)) {
    request.volunteers.push({ userId: req.user.id, name: req.user.name, at: new Date().toISOString() });
  }
  if (request.status === 'open') request.status = 'help_on_the_way';
  request.updatedAt = new Date().toISOString();
  save();
  res.json({ request });
});

app.post('/api/requests/:id/resolve', requireUser, (req, res) => {
  const request = db.requests.find((r) => r.id === req.params.id);
  if (!request) return res.status(404).json({ error: 'Request not found' });
  if (request.requesterId !== req.user.id) {
    return res.status(403).json({ error: 'Only the requester can resolve this' });
  }
  request.status = 'resolved';
  request.updatedAt = new Date().toISOString();
  save();
  res.json({ request });
});

module.exports = app;

if (require.main === module) {
  const port = process.env.PORT || 3000;
  app.listen(port, () => console.log(`Listening on http://localhost:${port}`));
}
