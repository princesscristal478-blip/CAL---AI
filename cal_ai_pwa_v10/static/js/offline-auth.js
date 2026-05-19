/**
 * Cal AI – Offline Auth Module
 *
 * Strategy:
 *  1. On every successful online login, derive a key from the password using
 *     PBKDF2 and store a salted HMAC of the credentials in IndexedDB.
 *  2. When the login form is submitted while offline, verify against the
 *     locally stored credential hash and restore a minimal session token
 *     so the app can function without the server.
 *  3. Offline session data (user profile + today's logs) is kept in a
 *     separate IndexedDB store, refreshed after every successful online login.
 *  4. All writes made offline are queued in a sync queue and replayed via
 *     Background Sync when connectivity is restored.
 */

const OfflineAuth = (() => {
  const DB_NAME    = 'cal-ai-offline';
  const DB_VERSION = 2;
  const STORE_AUTH       = 'auth';
  const STORE_USER       = 'user';
  const STORE_SYNC       = 'sync_queue';
  const STORE_FOODS      = 'foods_cache';
  const STORE_FOOD_QUEUE = 'food_log_queue';

  // ── IndexedDB helpers ───────────────────────────────────────────────────────
  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = e => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_AUTH)) db.createObjectStore(STORE_AUTH);
        if (!db.objectStoreNames.contains(STORE_USER)) db.createObjectStore(STORE_USER);
        if (!db.objectStoreNames.contains(STORE_SYNC)) {
          const s = db.createObjectStore(STORE_SYNC, { autoIncrement: true });
          s.createIndex('ts', 'ts');
        }
        if (!db.objectStoreNames.contains(STORE_FOODS)) {
          const fs = db.createObjectStore(STORE_FOODS, { keyPath: 'id' });
          fs.createIndex('name', 'name');
          fs.createIndex('category', 'category');
        }
        if (!db.objectStoreNames.contains(STORE_FOOD_QUEUE)) {
          db.createObjectStore(STORE_FOOD_QUEUE, { autoIncrement: true });
        }
      };
      req.onsuccess = e => resolve(e.target.result);
      req.onerror   = e => reject(e.target.error);
    });
  }

  function dbGet(db, store, key) {
    return new Promise((resolve, reject) => {
      const tx  = db.transaction(store, 'readonly');
      const req = tx.objectStore(store).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
    });
  }

  function dbPut(db, store, key, value) {
    return new Promise((resolve, reject) => {
      const tx  = db.transaction(store, 'readwrite');
      const req = tx.objectStore(store).put(value, key);
      req.onsuccess = () => resolve();
      req.onerror   = () => reject(req.error);
    });
  }

  function dbAdd(db, store, value) {
    return new Promise((resolve, reject) => {
      const tx  = db.transaction(store, 'readwrite');
      const req = tx.objectStore(store).add(value);
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
    });
  }

  function dbGetAll(db, store) {
    return new Promise((resolve, reject) => {
      const tx   = db.transaction(store, 'readonly');
      const req  = tx.objectStore(store).getAll();
      const keys = tx.objectStore(store).getAllKeys();
      let res = [], ks = [];
      req.onsuccess   = () => { res = req.result; if (ks.length) resolve(ks.map((k, i) => ({ key: k, value: res[i] }))); };
      keys.onsuccess  = () => { ks = keys.result;  if (res.length || ks.length === 0) resolve(ks.map((k, i) => ({ key: k, value: res[i] }))); };
      req.onerror     = () => reject(req.error);
    });
  }

  function dbDelete(db, store, key) {
    return new Promise((resolve, reject) => {
      const tx  = db.transaction(store, 'readwrite');
      const req = tx.objectStore(store).delete(key);
      req.onsuccess = () => resolve();
      req.onerror   = () => reject(req.error);
    });
  }

  // ── Crypto helpers ──────────────────────────────────────────────────────────
  async function deriveKey(password, salt) {
    const enc      = new TextEncoder();
    const keyMat   = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveBits']);
    const bits     = await crypto.subtle.deriveBits(
      { name: 'PBKDF2', hash: 'SHA-256', salt: enc.encode(salt), iterations: 100_000 },
      keyMat, 256
    );
    return Array.from(new Uint8Array(bits)).map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function randomSalt(len = 32) {
    return Array.from(crypto.getRandomValues(new Uint8Array(len)))
      .map(b => b.toString(16).padStart(2, '0')).join('');
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Called after a successful online login.
   * Caches a salted hash of the password and the user's session data.
   */
  async function cacheSuccessfulLogin(email, password, userJson) {
    try {
      const db   = await openDB();
      const salt = randomSalt();
      const hash = await deriveKey(password, salt + email);
      await dbPut(db, STORE_AUTH, 'credential', { email, salt, hash });
      await dbPut(db, STORE_USER, 'profile', { ...userJson, offlineCachedAt: Date.now() });
    } catch (err) {
      console.warn('[OfflineAuth] cacheSuccessfulLogin failed:', err);
    }
  }

  /**
   * Attempts an offline login.
   * Returns { ok: true, user } on success or { ok: false, error } on failure.
   */
  async function attemptOfflineLogin(email, password) {
    try {
      const db   = await openDB();
      const cred = await dbGet(db, STORE_AUTH, 'credential');
      if (!cred) return { ok: false, error: 'No offline credentials stored. Please log in online first.' };
      if (cred.email !== email) return { ok: false, error: 'Offline login only works for the last signed-in account.' };

      const hash = await deriveKey(password, cred.salt + email);
      if (hash !== cred.hash) return { ok: false, error: 'Incorrect password.' };

      const profile = await dbGet(db, STORE_USER, 'profile');
      return { ok: true, user: profile || { email } };
    } catch (err) {
      console.warn('[OfflineAuth] attemptOfflineLogin error:', err);
      return { ok: false, error: 'Offline login failed. Please check your connection.' };
    }
  }

  /**
   * Persists the user's dashboard data for offline display.
   * Call this after fetching fresh data from the server.
   */
  async function cacheUserData(key, data) {
    try {
      const db = await openDB();
      await dbPut(db, STORE_USER, key, { data, cachedAt: Date.now() });
    } catch (err) {
      console.warn('[OfflineAuth] cacheUserData failed:', err);
    }
  }

  async function getCachedUserData(key) {
    try {
      const db  = await openDB();
      const rec = await dbGet(db, STORE_USER, key);
      return rec ? rec.data : null;
    } catch { return null; }
  }

  /**
   * Queue a write operation (POST) to replay when back online.
   */
  async function queueOfflineWrite(url, body) {
    try {
      const db = await openDB();
      await dbAdd(db, STORE_SYNC, { url, body, ts: Date.now() });
      // Request a background sync if supported
      if ('serviceWorker' in navigator && 'SyncManager' in window) {
        const reg = await navigator.serviceWorker.ready;
        await reg.sync.register('offline-writes');
      }
    } catch (err) {
      console.warn('[OfflineAuth] queueOfflineWrite failed:', err);
    }
  }

  /**
   * Replays all queued writes — called by the service worker on sync,
   * and also directly when we detect we're back online.
   */
  async function replayQueuedWrites() {
    try {
      const db    = await openDB();
      const items = await dbGetAll(db, STORE_SYNC);
      if (!items.length) return;

      const results = await Promise.allSettled(
        items.map(({ key, value }) =>
          fetch(value.url, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(value.body),
          }).then(async r => {
            if (r.ok) await dbDelete(db, STORE_SYNC, key);
          })
        )
      );
      const synced = results.filter(r => r.status === 'fulfilled').length;
      if (synced) console.log(`[OfflineAuth] Replayed ${synced} offline write(s)`);
    } catch (err) {
      console.warn('[OfflineAuth] replayQueuedWrites failed:', err);
    }
  }

  /** Clears all cached offline credentials (on logout). */
  async function clearCache() {
    try {
      const db = await openDB();
      await dbPut(db, STORE_AUTH, 'credential', null);
    } catch (err) {
      console.warn('[OfflineAuth] clearCache failed:', err);
    }
  }

  // Replay queued writes when connectivity is restored
  window.addEventListener('online', replayQueuedWrites);

  /**
   * Fetches /api/dashboard-cache and persists it for offline use.
   * Call this after any successful online login or after logging food.
   */
  async function cacheDashboardData() {
    try {
      const r = await fetch('/api/dashboard-cache', { credentials: 'include' });
      if (!r.ok) return;
      const data = await r.json();
      const db   = await openDB();
      await dbPut(db, STORE_USER, 'dashboard',    data);
      await dbPut(db, STORE_USER, 'dashboard_ts', data.cached_at || Date.now());
      console.log('[OfflineAuth] Dashboard data cached.');
    } catch (err) {
      console.warn('[OfflineAuth] cacheDashboardData failed:', err);
    }
  }

  // Auto-cache dashboard on page load if online and logged in
  if (navigator.onLine) {
    window.addEventListener('load', () => {
      // Only cache on pages that suggest we're authenticated
      if (!window.location.pathname.includes('/login') &&
          !window.location.pathname.includes('/register')) {
        cacheDashboardData().catch(() => {});
      }
    });
  }

  // ── Foods Cache ──────────────────────────────────────────────────────────────

  /** Bulk-save food records to IndexedDB for offline search. */
  async function cacheFoods(foods) {
    try {
      const db  = await openDB();
      const tx  = db.transaction(STORE_FOODS, 'readwrite');
      const st  = tx.objectStore(STORE_FOODS);
      foods.forEach(f => st.put(f));
      await new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = () => rej(tx.error); });
      console.log(`[OfflineAuth] Cached ${foods.length} foods.`);
    } catch (err) { console.warn('[OfflineAuth] cacheFoods failed:', err); }
  }

  /** Search cached foods by name query. */
  async function searchCachedFoods(query, category) {
    try {
      const db  = await openDB();
      const all = await dbGetAll(db, STORE_FOODS);
      let results = all.map(r => r.value);
      if (category) results = results.filter(f => f.category === category);
      if (query)    results = results.filter(f => f.name.toLowerCase().includes(query.toLowerCase()));
      return results.slice(0, 30);
    } catch { return []; }
  }

  /** Get all distinct categories from cached foods. */
  async function getCachedCategories() {
    try {
      const db  = await openDB();
      const all = await dbGetAll(db, STORE_FOODS);
      const cats = [...new Set(all.map(r => r.value.category).filter(Boolean))].sort();
      return cats;
    } catch { return []; }
  }

  // ── Offline Food Log Queue ────────────────────────────────────────────────────

  /** Save a food log entry locally when offline. */
  async function queueFoodLog(entry) {
    try {
      const db = await openDB();
      await dbAdd(db, STORE_FOOD_QUEUE, { ...entry, ts: Date.now() });
      console.log('[OfflineAuth] Food log queued:', entry);
      return true;
    } catch (err) { console.warn('[OfflineAuth] queueFoodLog failed:', err); return false; }
  }

  /** Get all queued food logs. */
  async function getPendingFoodLogs() {
    try {
      const db = await openDB();
      return await dbGetAll(db, STORE_FOOD_QUEUE);
    } catch { return []; }
  }

  /** Sync pending food logs to server. */
  async function syncFoodLogs() {
    try {
      const db      = await openDB();
      const pending = await dbGetAll(db, STORE_FOOD_QUEUE);
      if (!pending.length) return 0;
      const entries = pending.map(p => p.value);
      const r = await fetch('/api/offline-log-sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(entries),
      });
      if (r.ok) {
        // Clear queue
        const tx = db.transaction(STORE_FOOD_QUEUE, 'readwrite');
        tx.objectStore(STORE_FOOD_QUEUE).clear();
        await new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = () => rej(tx.error); });
        console.log(`[OfflineAuth] Synced ${entries.length} food logs.`);
        return entries.length;
      }
    } catch (err) { console.warn('[OfflineAuth] syncFoodLogs failed:', err); }
    return 0;
  }

  window.addEventListener('online', async () => {
    const n = await syncFoodLogs();
    if (n > 0) {
      // Re-cache dashboard after sync
      setTimeout(() => cacheDashboardData(), 1000);
    }
  });

  return { cacheSuccessfulLogin, attemptOfflineLogin, cacheUserData, getCachedUserData,
           queueOfflineWrite, replayQueuedWrites, clearCache, cacheDashboardData,
           cacheFoods, searchCachedFoods, getCachedCategories,
           queueFoodLog, getPendingFoodLogs, syncFoodLogs };
})();

window.OfflineAuth = OfflineAuth;

// ── Offline Registration Queue ───────────────────────────────────────────────
const OfflineRegister = (() => {
  const DB_NAME    = 'cal-ai-offline';
  const DB_VERSION = 1;
  const STORE_SYNC = 'sync_queue';
  const PENDING_KEY = 'pending_registrations';

  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = e => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains('auth')) db.createObjectStore('auth');
        if (!db.objectStoreNames.contains('user')) db.createObjectStore('user');
        if (!db.objectStoreNames.contains(STORE_SYNC)) {
          const s = db.createObjectStore(STORE_SYNC, { autoIncrement: true });
          s.createIndex('ts', 'ts');
        }
      };
      req.onsuccess = e => resolve(e.target.result);
      req.onerror   = e => reject(e.target.error);
    });
  }

  function dbGet(db, store, key) {
    return new Promise((res, rej) => {
      const req = db.transaction(store, 'readonly').objectStore(store).get(key);
      req.onsuccess = () => res(req.result);
      req.onerror   = () => rej(req.error);
    });
  }

  function dbPut(db, store, key, value) {
    return new Promise((res, rej) => {
      const req = db.transaction(store, 'readwrite').objectStore(store).put(value, key);
      req.onsuccess = () => res();
      req.onerror   = () => rej(req.error);
    });
  }

  /**
   * Save registration form data locally so it can be submitted when back online.
   * Also pre-caches credentials so offline login works immediately after.
   */
  async function queueRegistration(formData) {
    try {
      const db = await openDB();
      // Save the pending registration payload
      const pending = (await dbGet(db, 'user', PENDING_KEY)) || [];
      const ts = Date.now();
      pending.push({ ...formData, ts });
      await dbPut(db, 'user', PENDING_KEY, pending);

      // Pre-cache credentials so offline login works right away
      if (window.OfflineAuth) {
        await window.OfflineAuth.cacheSuccessfulLogin(formData.email, formData.password, {
          email: formData.email,
          username: formData.username,
          offlinePending: true,
        });
      }
      console.log('[OfflineRegister] Registration queued for sync.');
      return true;
    } catch (err) {
      console.warn('[OfflineRegister] queueRegistration failed:', err);
      return false;
    }
  }

  /**
   * Replay all pending registrations — called when back online.
   */
  async function replayPendingRegistrations() {
    try {
      const db      = await openDB();
      const pending = (await dbGet(db, 'user', PENDING_KEY)) || [];
      if (!pending.length) return;

      const remaining = [];
      for (const reg of pending) {
        try {
          const body = new URLSearchParams();
          Object.entries(reg).forEach(([k, v]) => { if (k !== 'ts') body.append(k, v); });
          const resp = await fetch('/register', { method: 'POST', body, headers: { 'X-Offline-Sync': '1' } });
          if (!resp.ok && resp.status !== 302) remaining.push(reg); // keep if failed
          else console.log('[OfflineRegister] Synced registration for', reg.email);
        } catch { remaining.push(reg); }
      }
      await dbPut(db, 'user', PENDING_KEY, remaining);
    } catch (err) {
      console.warn('[OfflineRegister] replayPendingRegistrations failed:', err);
    }
  }

  window.addEventListener('online', replayPendingRegistrations);

  return { queueRegistration, replayPendingRegistrations };
})();

window.OfflineRegister = OfflineRegister;
