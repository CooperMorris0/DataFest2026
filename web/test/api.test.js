const { test, before, after } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const dbFile = path.join(os.tmpdir(), `fw-test-${process.pid}-${Date.now()}.json`);
process.env.DB_FILE = dbFile;
const app = require('../server');

let server;
let base;

before(async () => {
  server = app.listen(0);
  await new Promise((resolve) => server.once('listening', resolve));
  base = `http://localhost:${server.address().port}`;
});

after(() => {
  server.close();
  fs.rmSync(dbFile, { force: true });
});

function api(method, url, body, cookie) {
  const headers = {};
  if (body) headers['Content-Type'] = 'application/json';
  if (cookie) headers.Cookie = cookie;
  return fetch(base + url, { method, headers, body: body && JSON.stringify(body), redirect: 'manual' });
}

async function login(name) {
  const res = await api('POST', '/api/login', { name });
  assert.strictEqual(res.status, 200);
  return res.headers.get('set-cookie').split(';')[0];
}

const goodRequest = { lat: 37.8, lng: -122.27, category: 'sandbags', details: 'Water at the door', people: 3 };

test('GET / redirects to the map', async () => {
  const res = await api('GET', '/');
  assert.strictEqual(res.status, 302);
  assert.strictEqual(res.headers.get('location'), '/flood_vulnerability_map.html');
});

test('map page includes the community script', async () => {
  const res = await api('GET', '/flood_vulnerability_map.html');
  assert.strictEqual(res.status, 200);
  assert.match(res.headers.get('content-type'), /text\/html/);
  assert.ok((await res.text()).includes('<script src="/app/community.js"></script>'));
});

test('login sets a cookie and /api/me returns the user', async () => {
  const res = await api('POST', '/api/login', { name: '  Alice  ' });
  assert.strictEqual(res.status, 200);
  const setCookie = res.headers.get('set-cookie');
  assert.match(setCookie, /fw_user=/);
  assert.match(setCookie, /HttpOnly/);
  const me = await (await api('GET', '/api/me', null, setCookie.split(';')[0])).json();
  assert.strictEqual(me.user.name, 'Alice');
  assert.deepStrictEqual(await (await api('GET', '/api/me')).json(), { user: null });
});

test('creating a request without login is 401', async () => {
  const res = await api('POST', '/api/requests', goodRequest);
  assert.strictEqual(res.status, 401);
  assert.deepStrictEqual(await res.json(), { error: 'Log in first' });
});

test('invalid lat is 400', async () => {
  const cookie = await login('Alice');
  const res = await api('POST', '/api/requests', { ...goodRequest, lat: 40 }, cookie);
  assert.strictEqual(res.status, 400);
});

test('full help request flow', async () => {
  const alice = await login('Alice');
  const bob = await login('Bob');

  let res = await api('POST', '/api/requests', goodRequest, alice);
  assert.strictEqual(res.status, 201);
  const { request } = await res.json();
  assert.strictEqual(request.status, 'open');
  assert.strictEqual(request.requesterName, 'Alice');

  res = await api('POST', `/api/requests/${request.id}/volunteer`, null, alice);
  assert.strictEqual(res.status, 400, 'requester cannot volunteer');

  res = await api('POST', `/api/requests/${request.id}/volunteer`, null, bob);
  assert.strictEqual(res.status, 200);
  let body = await res.json();
  assert.strictEqual(body.request.status, 'help_on_the_way');
  assert.strictEqual(body.request.volunteers[0].name, 'Bob');

  res = await api('POST', `/api/requests/${request.id}/resolve`, null, bob);
  assert.strictEqual(res.status, 403);

  res = await api('POST', `/api/requests/${request.id}/resolve`, null, alice);
  assert.strictEqual(res.status, 200);
  body = await res.json();
  assert.strictEqual(body.request.status, 'resolved');

  const list = await (await api('GET', '/api/requests')).json();
  assert.ok(list.requests.some((r) => r.id === request.id));
});

test('comments on a request', async () => {
  const alice = await login('Alice');
  const bob = await login('Bob');
  const { request } = await (await api('POST', '/api/requests', goodRequest, alice)).json();
  assert.deepStrictEqual(request.comments, []);

  let res = await api('POST', `/api/requests/${request.id}/comments`, { text: 'On my way' });
  assert.strictEqual(res.status, 401, 'must be logged in');

  res = await api('POST', `/api/requests/${request.id}/comments`, { text: '   ' }, bob);
  assert.strictEqual(res.status, 400, 'empty comment');

  res = await api('POST', `/api/requests/${request.id}/comments`, { text: ' Bringing 10 sandbags ' }, bob);
  assert.strictEqual(res.status, 201);
  res = await api('POST', `/api/requests/${request.id}/comments`, { text: 'Thank you!' }, alice);
  const { request: updated } = await res.json();
  assert.deepStrictEqual(updated.comments.map((c) => [c.name, c.text]), [['Bob', 'Bringing 10 sandbags'], ['Alice', 'Thank you!']]);

  res = await api('POST', '/api/requests/nope/comments', { text: 'hi' }, bob);
  assert.strictEqual(res.status, 404);
});
