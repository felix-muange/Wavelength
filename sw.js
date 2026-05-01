// Wavelength Service Worker
// Caches static assets for offline/PWA support

const CACHE_NAME = 'wavelength-v3';

// ── IMPORTANT: do NOT include '/index.html' here.
// The server serves the frontend at '/' only.
// Including '/index.html' causes addAll() to fail with a 404
// which crashes the entire service worker install and breaks the app.
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/icon.svg',
];

// Install: pre-cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
      .catch(err => {
        console.warn('[SW] Cache install failed:', err.message);
        // Don't let a cache failure block the SW from installing
        return self.skipWaiting();
      })
  );
});

// Activate: delete old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(k => k !== CACHE_NAME)
          .map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// Fetch: network-first for API calls, cache-first for static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Never intercept proxy/stream/health API calls — always go to network
  const apiPaths = ['/proxy', '/stream', '/health', '/.well-known'];
  if (apiPaths.some(p => url.pathname.startsWith(p))) {
    return; // let browser handle it normally
  }

  // For navigation requests (HTML), use network-first
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .catch(() => caches.match('/'))
    );
    return;
  }

  // For static assets: cache-first, fallback to network
  event.respondWith(
    caches.match(event.request)
      .then(cached => cached || fetch(event.request)
        .then(response => {
          // Cache successful responses for static assets
          if (response.ok && ['/', '/manifest.json', '/icon.svg'].includes(url.pathname)) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        })
      )
  );
});
