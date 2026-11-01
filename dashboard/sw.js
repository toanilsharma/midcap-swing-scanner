// Midcap Swing Terminal - Service Worker
// Enables offline functionality, asset caching, and standalone PWA installation

const CACHE_NAME = 'midcap-swing-v1.0.0';
const DATA_CACHE_NAME = 'midcap-swing-data-v1';

const STATIC_ASSETS = [
  './',
  './index.html',
  './app.html',
  './style.css',
  './app.js',
  './login.js',
  './pwa.js',
  './manifest.webmanifest',
  './manifest.json',
  './icons/icon.svg',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-192.png',
  './icons/icon-maskable-512.png',
  './icons/apple-touch-icon.png',
  './icons/favicon.png'
];

// Install: Pre-cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[SW] Some assets failed to precache during install:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate: Clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME && key !== DATA_CACHE_NAME) {
            console.log('[SW] Removing old cache:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Strategy depending on request type
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle GET requests
  if (req.method !== 'GET') {
    return;
  }

  // 1. Dynamic API / Netlify Function calls: Network-First with cache fallback
  if (url.pathname.includes('/.netlify/functions/')) {
    event.respondWith(
      fetch(req)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(DATA_CACHE_NAME).then((cache) => {
              cache.put(req, responseClone);
            });
          }
          return networkResponse;
        })
        .catch(async () => {
          const cachedResponse = await caches.match(req);
          if (cachedResponse) {
            console.log('[SW] Serving cached API data for offline:', req.url);
            return cachedResponse;
          }
          return new Response(
            JSON.stringify({ error: 'You are currently offline. Showing cached terminal state.' }),
            { headers: { 'Content-Type': 'application/json' }, status: 503 }
          );
        })
    );
    return;
  }

  // 2. Navigation requests (HTML pages): Network-First, fallback to cached HTML
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((response) => {
          if (response && response.status === 200) {
            const respClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, respClone));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(req);
          if (cached) return cached;
          // Fallback to app.html or index.html
          return caches.match('./app.html') || caches.match('./index.html');
        })
    );
    return;
  }

  // 3. Static assets & CDN scripts: Stale-While-Revalidate
  event.respondWith(
    caches.match(req).then((cachedResponse) => {
      const fetchPromise = fetch(req)
        .then((networkResponse) => {
          if (networkResponse && (networkResponse.status === 200 || networkResponse.type === 'opaque')) {
            const respClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, respClone));
          }
          return networkResponse;
        })
        .catch(() => {
          // Network failed, nothing to do if cached response is present
        });

      return cachedResponse || fetchPromise;
    })
  );
});

