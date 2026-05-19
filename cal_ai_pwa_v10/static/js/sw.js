/**
 * Cal AI – Service Worker  (v4)
 *
 * Offline strategy:
 *   • Static shell  → Cache-first (versioned, auto-updated on deploy)
 *   • Pages/data    → Network-first, fallback to cache, fallback to shell
 *   • Background Sync → Replays queued writes when connection returns
 *
 * Push Notifications:
 *   • ALWAYS shows a native OS notification (works when app is open OR closed)
 *   • Also broadcasts to open tabs so the in-app bell + sound fires too
 */

const CACHE_VER   = 'cal-ai-v5';
const OFFLINE_URL = '/offline';

const PRECACHE = [
  '/',
  '/login',
  '/register',
  '/dashboard',
  '/scan',
  '/log',
  '/planner',
  '/analytics',
  '/offline',
  '/offline-dashboard',
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/js/offline-auth.js',
  '/static/manifest.json',
  'https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/css/bootstrap.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css',
  'https://cdn.jsdelivr.net/npm/chart.js',
];

// ── Install ──────────────────────────────────────────────────────────────────
self.addEventListener('message', e => {
  if (e.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_VER)
      .then(cache => cache.addAll(PRECACHE).catch(err => console.warn('[SW] Precache partial failure:', err)))
      .then(() => self.skipWaiting())
  );
});

// ── Activate ─────────────────────────────────────────────────────────────────
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_VER).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// ── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  if (!['http:', 'https:'].includes(url.protocol)) return;

  if (isStaticAsset(url)) {
    e.respondWith(cacheFirst(request));
  } else {
    e.respondWith(networkFirst(request));
  }
});

function isStaticAsset(url) {
  return (
    url.pathname.startsWith('/static/') ||
    url.hostname === 'cdnjs.cloudflare.com' ||
    url.hostname === 'cdn.jsdelivr.net' ||
    /\.(css|js|png|jpg|jpeg|svg|ico|woff2?)$/.test(url.pathname)
  );
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) (await caches.open(CACHE_VER)).put(request, response.clone());
    return response;
  } catch {
    return new Response('Asset unavailable offline', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) (await caches.open(CACHE_VER)).put(request, response.clone());
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.headers.get('accept')?.includes('text/html')) {
      const offlinePage = await caches.match(OFFLINE_URL);
      return offlinePage || offlineFallback();
    }
    return new Response(JSON.stringify({ error: 'offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

function offlineFallback() {
  return new Response(`<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cal AI – Offline</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    display:flex;align-items:center;justify-content:center;
    min-height:100vh;margin:0;background:#0f172a;color:#f1f5f9;text-align:center;padding:1rem}
  .card{background:#1e293b;border-radius:20px;padding:2.5rem 2rem;max-width:360px;width:100%}
  .icon{font-size:3rem}.btn{padding:.75rem 2rem;background:#22c55e;border:none;
    border-radius:12px;color:#fff;font-size:1rem;cursor:pointer;margin:.25rem}
</style></head>
<body><div class="card">
  <div class="icon">📴</div>
  <h2>You're offline</h2>
  <p style="color:#94a3b8">Cached pages are still available.</p>
  <button class="btn" onclick="history.back()">Go Back</button>
  <button class="btn" style="background:#334155" onclick="location.reload()">Retry</button>
  <small style="display:block;margin-top:1rem;color:#64748b">Cal AI will sync when you're back online.</small>
</div></body></html>`, {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}

// ── Background Sync ───────────────────────────────────────────────────────────
self.addEventListener('sync', e => {
  if (e.tag === 'offline-writes') {
    e.waitUntil(
      self.clients.matchAll({ type: 'window' })
        .then(cs => cs.forEach(c => c.postMessage({ type: 'REPLAY_SYNC_QUEUE' })))
    );
  }
  if (e.tag === 'meal-reminder') {
    e.waitUntil(self.registration.showNotification('🍽️ Meal Time!', {
      body: "Don't forget to log your meal.",
      icon: '/static/icons/icon-192.png',
    }));
  }
});

// ── Push Notifications ────────────────────────────────────────────────────────
// ALWAYS shows a native OS notification — works whether the app is open or closed.
// Unique tag per notification so each meal reminder appears separately.
// Also broadcasts to open tabs so the in-app bell and sound fire too.
self.addEventListener('push', e => {
  let data = {
    title: '🥗 Cal AI',
    body: 'Time to log your meal!',
    icon: '/static/icons/icon-192.png',
    url: '/dashboard',
  };
  if (e.data) {
    try { data = { ...data, ...JSON.parse(e.data.text()) }; } catch {}
  }

  // Always show native OS notification (required by browser — SW must show notif on push)
  // Use unique tag so repeated reminders all appear (not collapsed into one)
  const notifPromise = self.registration.showNotification(data.title, {
    body: data.body,
    icon: data.icon || '/static/icons/icon-192.png',
    badge: '/static/icons/icon-72.png',
    vibrate: [300, 100, 300, 100, 300],
    data: { url: data.url || '/dashboard' },
    requireInteraction: false,
    tag: 'cal-ai-' + Date.now(),
    renotify: false,
    actions: [
      { action: 'log',   title: '✏️ Log Food'  },
      { action: 'scan',  title: '📷 Scan Food' },
      { action: 'close', title: '✕ Dismiss'    },
    ],
  });

  // Also broadcast to open tabs → in-app bell entry + chime sound
  const broadcastPromise = clients
    .matchAll({ type: 'window', includeUncontrolled: true })
    .then(cs => {
      cs.forEach(c => c.postMessage({
        type: 'PUSH_RECEIVED',
        title: data.title,
        body: data.body,
        playSound: true,
      }));
    });

  e.waitUntil(Promise.all([notifPromise, broadcastPromise]));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  let url = '/dashboard';
  if (e.action === 'scan') url = '/scan';
  else if (e.action === 'log') url = '/log';
  else if (e.notification.data?.url) url = e.notification.data.url;

  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
      // Focus existing tab if open, else open a new window
      const existing = cs.find(c => c.url.includes(self.registration.scope));
      if (existing) {
        return existing.focus().then(c => c.navigate(url));
      }
      return clients.openWindow(url);
    })
  );
});
