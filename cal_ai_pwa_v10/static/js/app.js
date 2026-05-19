/* Cal AI PWA – Main app JS */

// ─── Service Worker Registration ────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then(reg => { window._swReg = reg; })
      .catch(err => console.warn('[SW] Failed:', err));
  });

  // Note: All SW message handling (PUSH_RECEIVED, REPLAY_SYNC_QUEUE)
  // is consolidated in the listener near the bottom of this file.
}

// ─── Connectivity Banner ─────────────────────────────────────────────────────
(function () {
  function showConnBanner(online) {
    let banner = document.getElementById('conn-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'conn-banner';
      banner.style.cssText = [
        'position:fixed;top:0;left:0;right:0;z-index:10000;',
        'padding:.5rem 1rem;text-align:center;font-size:.85rem;font-weight:600;',
        'transition:transform .3s;transform:translateY(-100%)',
      ].join('');
      document.body.appendChild(banner);
    }
    if (online) {
      banner.textContent = '✅ Back online — syncing your data…';
      banner.style.background = '#22c55e';
      banner.style.color = '#fff';
    } else {
      banner.textContent = '📴 You\'re offline — using cached data';
      banner.style.background = '#f59e0b';
      banner.style.color = '#1c1917';
    }
    banner.style.transform = 'translateY(0)';
    if (online) setTimeout(() => { banner.style.transform = 'translateY(-100%)'; }, 3000);
  }

  window.addEventListener('online',  () => showConnBanner(true));
  window.addEventListener('offline', () => showConnBanner(false));
  if (!navigator.onLine) showConnBanner(false);
})();

// ─── PWA Install Banner ──────────────────────────────────────────────────────
let deferredInstallPrompt = null;

function getInstallBanner() { return document.getElementById('install-banner'); }

// On load: if already dismissed, remove the element so it never appears
document.addEventListener('DOMContentLoaded', () => {
  const banner = getInstallBanner();
  if (!banner) return;

  if (localStorage.getItem('pwa-dismissed')) {
    banner.remove();
    return;
  }

  // Dismiss button
  const dismissBtn = document.getElementById('install-dismiss');
  if (dismissBtn) {
    dismissBtn.addEventListener('click', () => {
      banner.classList.remove('show');
      localStorage.setItem('pwa-dismissed', '1');
      // Fully hide after animation
      setTimeout(() => banner.remove(), 400);
    });
  }

  // Install button
  const installBtn = document.getElementById('install-btn');
  if (installBtn) {
    installBtn.addEventListener('click', async () => {
      if (!deferredInstallPrompt) return;
      banner.classList.remove('show');
      deferredInstallPrompt.prompt();
      const { outcome } = await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
    });
  }
});

// Capture the install prompt — fires only when PWA install criteria are met
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault(); // prevent mini-infobar
  deferredInstallPrompt = e;
  const banner = getInstallBanner();
  if (banner && !localStorage.getItem('pwa-dismissed')) {
    setTimeout(() => banner.classList.add('show'), 1500);
  }
});

window.addEventListener('appinstalled', () => {
  const banner = getInstallBanner();
  if (banner) banner.classList.remove('show');
});

// ─── Service Worker: force activate immediately on desktop ────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistration().then(reg => {
    if (reg && reg.waiting) {
      reg.waiting.postMessage({ type: 'SKIP_WAITING' });
    }
  });
  // Keep SW alive and claim clients immediately
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    console.log('[SW] New service worker activated');
  });
}

// ─── Push Notifications ──────────────────────────────────────────────────────
const CalPush = {
  async getVapidKey() {
    const r = await fetch('/api/vapid-public-key');
    const d = await r.json();
    return d.key;
  },

  urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
  },

  async subscribe() {
    // Push requires a secure context (HTTPS or localhost)
    if (!window.isSecureContext) {
      return {
        ok: false,
        reason: 'Push notifications require HTTPS or localhost. ' +
                'Open the app via http://localhost:5000 sa Chrome/Edge.'
      };
    }
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      return { ok: false, reason: 'Push notifications ay hindi sinusuportahan ng browser na ito. Gamitin ang Chrome o Edge.' };
    }

    // Make sure SW is registered before asking for permission
    let reg;
    try {
      reg = await navigator.serviceWorker.ready;
    } catch (err) {
      return { ok: false, reason: 'Service Worker hindi pa handa. I-reload ang page at subukan ulit.' };
    }

    const permission = await Notification.requestPermission();
    if (permission === 'denied') {
      return { ok: false, reason: 'Notifications ay naka-block. I-click ang 🔒 lock icon sa address bar → Allow Notifications, pagkatapos i-reload.' };
    }
    if (permission !== 'granted') {
      return { ok: false, reason: 'Hindi pinayagan ang notification permission.' };
    }
    try {
      // Retry fetching VAPID key up to 5x (server may still be generating it on first run)
      let vapidKey = null;
      for (let attempt = 0; attempt < 5; attempt++) {
        const resp = await this.getVapidKey();
        if (resp && resp !== 'YOUR_VAPID_PUBLIC_KEY' && resp !== 'YOUR_VAPID_PUBLIC_KEY_HERE' && resp.length >= 30) {
          vapidKey = resp;
          break;
        }
        // Wait 1.5s between retries
        await new Promise(r => setTimeout(r, 1500));
      }
      if (!vapidKey) {
        return { ok: false, reason: 'Hindi ma-load ang VAPID keys. Siguraduhing naka-install ang py-vapid (pip install py-vapid) at i-restart ang server.' };
      }

      // Unsubscribe any stale subscription first (avoids "applicationServerKey changed" error)
      const existingSub = await reg.pushManager.getSubscription();
      if (existingSub) {
        try { await existingSub.unsubscribe(); } catch (_) {}
      }

      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.urlBase64ToUint8Array(vapidKey)
      });
      const r = await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sub),
        credentials: 'include',
      });
      return { ok: r.ok };
    } catch (err) {
      console.error('[Push] Subscribe failed:', err);
      let msg = err.message || 'Unknown error';
      if (msg.includes('applicationServerKey')) {
        msg = 'VAPID key error — i-restart ang server para mag-regenerate ng keys.';
      } else if (msg.includes('registration')) {
        msg = 'Service Worker error. I-reload ang page at subukan ulit.';
      }
      return { ok: false, reason: msg };
    }
  },

  async unsubscribe() {
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) await sub.unsubscribe();
      await fetch('/api/push/unsubscribe', { method: 'POST' });
      return true;
    } catch (err) {
      console.error('[Push] Unsubscribe failed:', err);
      return false;
    }
  },

  async isSubscribed() {
    if (!('serviceWorker' in navigator)) return false;
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      return !!sub;
    } catch { return false; }
  },

  async sendTest() {
    await fetch('/api/push/send-test', { method: 'POST' });
  }
};
window.CalPush = CalPush;

// ─── Notification toggle ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const toggle = document.getElementById('notif-toggle');
  if (toggle) {
    toggle.checked = await CalPush.isSubscribed();
    toggle.addEventListener('change', async () => {
      if (toggle.checked) {
        const result = await CalPush.subscribe();
        const ok = result === true || result?.ok === true;
        toggle.checked = ok;
        if (ok) {
          showToast('🔔 Notifications enabled!', 'success');
        } else {
          const reason = result?.reason || 'Subscription failed';
          showToast('❌ ' + reason, 'danger');
        }
      } else {
        await CalPush.unsubscribe();
        showToast('🔕 Notifications disabled', 'info');
      }
    });
  }

  document.getElementById('test-push-btn')?.addEventListener('click', async () => {
    await CalPush.sendTest();
    showToast('🔔 Test notification sent!', 'success');
  });

  // ── Auto-prompt: ask once on first open (app open or closed matters here) ──
  // Shows a friendly in-app banner the FIRST time a logged-in user visits.
  // Browser permission dialog only fires when they tap "Enable" — never forced.
  if (
    'Notification' in window &&
    Notification.permission === 'default' &&           // not yet asked
    !localStorage.getItem('notif-prompt-dismissed') && // not dismissed before
    document.getElementById('notifBell')               // user is logged in (nav exists)
  ) {
    // Show banner after a short delay so the page has fully loaded
    setTimeout(() => showNotifPromptBanner(), 2000);
  }
});

// ── Notification permission prompt banner ─────────────────────────────────────
function showNotifPromptBanner() {
  if (document.getElementById('notif-prompt-banner')) return; // already shown

  const banner = document.createElement('div');
  banner.id = 'notif-prompt-banner';
  banner.style.cssText = [
    'position:fixed;bottom:5rem;left:50%;transform:translateX(-50%);',
    'z-index:99999;width:calc(100% - 2rem);max-width:420px;',
    'background:var(--surface,#1e293b);border:1px solid var(--border,#2d333b);',
    'border-radius:16px;padding:1.25rem 1rem;box-shadow:0 8px 32px rgba(0,0,0,.4);',
    'display:flex;flex-direction:column;gap:.75rem;',
    'animation:slideUpFade .35s ease;',
  ].join('');

  banner.innerHTML = `
    <style>
      @keyframes slideUpFade {
        from { opacity:0; transform:translateX(-50%) translateY(20px); }
        to   { opacity:1; transform:translateX(-50%) translateY(0); }
      }
    </style>
    <div style="display:flex;align-items:flex-start;gap:.75rem">
      <span style="font-size:1.75rem;line-height:1">🔔</span>
      <div>
        <div style="font-weight:700;font-size:.95rem;color:var(--text,#f1f5f9);margin-bottom:.2rem">
          Stay on track with meal reminders
        </div>
        <div style="font-size:.82rem;color:var(--text-muted,#94a3b8);line-height:1.4">
          Get notified at breakfast, lunch &amp; dinner — even when the app is closed.
        </div>
      </div>
    </div>
    <div style="display:flex;gap:.6rem;justify-content:flex-end">
      <button id="notif-prompt-no" style="
        padding:.5rem 1rem;border-radius:10px;border:1px solid var(--border,#2d333b);
        background:transparent;color:var(--text-muted,#94a3b8);font-size:.85rem;cursor:pointer">
        Not now
      </button>
      <button id="notif-prompt-yes" style="
        padding:.5rem 1.25rem;border-radius:10px;border:none;
        background:#22c55e;color:#fff;font-weight:600;font-size:.85rem;cursor:pointer">
        Enable Reminders
      </button>
    </div>
  `;

  document.body.appendChild(banner);

  document.getElementById('notif-prompt-no').addEventListener('click', () => {
    localStorage.setItem('notif-prompt-dismissed', '1');
    banner.style.animation = 'none';
    banner.style.opacity = '0';
    banner.style.transform = 'translateX(-50%) translateY(20px)';
    banner.style.transition = 'opacity .3s,transform .3s';
    setTimeout(() => banner.remove(), 350);
  });

  document.getElementById('notif-prompt-yes').addEventListener('click', async () => {
    banner.remove();
    localStorage.setItem('notif-prompt-dismissed', '1');
    const result = await CalPush.subscribe();
    const ok = result === true || result?.ok === true;
    if (ok) {
      showToast('🔔 Meal reminders enabled!', 'success');
      if (typeof window.addNotif === 'function') {
        window.addNotif('🔔 Reminders Enabled', 'You will get meal reminders at 7am, 12pm & 6:30pm.', '🔔');
      }
      // Sync toggle UI
      ['pushToggle','notifToggle'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.checked = true;
      });
    } else {
      const reason = result?.reason || 'Could not enable notifications.';
      showToast('⚠️ ' + reason, 'warning');
    }
  });
}

// ─── Notification sound (Web Audio API — no external file needed) ────────────
function playNotifSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const notes = [880, 1108, 1318]; // A5, C#6, E6 — pleasant ding chord
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.value = freq;
      const t = ctx.currentTime + i * 0.12;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.25, t + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.5);
      osc.start(t); osc.stop(t + 0.5);
    });
  } catch {}
}

// ─── Foreground push: SW messages notification to page ───────────────────────
// Fires when the app is open (either visible or in the background tab).
// The OS-level notification is already shown by the SW; this adds the
// in-app bell entry + toast + sound so the user sees it inside the UI too.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('message', event => {
    if (event.data?.type === 'PUSH_RECEIVED') {
      const { title, body, playSound } = event.data;

      // Play chime regardless of visibility (audible even in background tab)
      if (playSound) playNotifSound();

      // Add to in-app bell + show toast (works visible or hidden)
      if (typeof window.addNotif === 'function') {
        window.addNotif(title, body, '🔔');
      }
      showToast(`🔔 ${body}`, 'info');
    }

    // Background-sync queue replay
    if (event.data?.type === 'REPLAY_SYNC_QUEUE') {
      window.OfflineAuth?.replayQueuedWrites();
    }
  });
}

// ─── Toast helper ────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = `alert alert-${type} fade-in`;
  t.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:9999;max-width:300px;font-size:.85rem;word-break:break-word;white-space:normal;overflow:hidden;';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}
window.showToast = showToast;

// ─── Delete log item ──────────────────────────────────────────────────────────
document.addEventListener('click', async e => {
  const btn = e.target.closest('[data-delete-log]');
  if (!btn) return;
  const id = btn.dataset.deleteLog;
  if (!confirm('Remove this food log?')) return;
  const r = await fetch(`/log/delete/${id}`, { method: 'POST' });
  if (r.ok) {
    btn.closest('.log-item')?.remove();
    showToast('Food log removed', 'info');
  }
});

// ─── Food search autocomplete (log page) ─────────────────────────────────────
const foodSearchInput = document.getElementById('food-search');
const foodResults = document.getElementById('food-results');
if (foodSearchInput) {
  let timeout;
  foodSearchInput.addEventListener('input', () => {
    clearTimeout(timeout);
    timeout = setTimeout(async () => {
      const q = foodSearchInput.value.trim();
      if (q.length < 2) return;
      const r = await fetch(`/api/foods/search?q=${encodeURIComponent(q)}`);
      const foods = await r.json();
      if (foodResults) {
        foodResults.innerHTML = foods.map(f => `
          <div class="food-item" style="cursor:pointer" onclick="selectFood(${f.id},'${f.name.replace(/'/g,"\\'")}',${f.calories})">
            <div class="food-icon">${foodEmoji(f.category)}</div>
            <div class="flex-1">
              <div class="food-name">${f.name}</div>
              <div class="food-meta">${f.protein}g P · ${f.carbs}g C · ${f.fat}g F</div>
            </div>
            <div class="food-cal">${f.calories}<small>kcal</small></div>
          </div>
        `).join('');
      }
    }, 300);
  });
}

function selectFood(id, name, cal) {
  document.getElementById('selected-food-id').value = id;
  document.getElementById('selected-food-name').textContent = name;
  document.getElementById('selected-food-cal').textContent = `${cal} kcal / 100g`;
  document.getElementById('food-selected-panel').style.display = 'block';
  if (foodResults) foodResults.innerHTML = '';
  if (foodSearchInput) foodSearchInput.value = name;
}
window.selectFood = selectFood;

function foodEmoji(cat) {
  const map = {
    'Fruits':'🍎','Vegetables':'🥦','Grains':'🍚','Protein':'🍗',
    'Dairy':'🥛','Snacks':'🍿','Beverages':'🥤','Filipino':'🇵🇭','General':'🍽️'
  };
  return map[cat] || '🍽️';
}
window.foodEmoji = foodEmoji;
