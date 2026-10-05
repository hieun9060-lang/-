// 앱 화면은 캐시해 빠르게 열고, 데이터(JSON)는 항상 네트워크 우선(오프라인이면 마지막 데이터)
const SHELL = 'aeo-shell-v1';
const ASSETS = ['./', 'index.html', 'app.css', 'app.js', 'manifest.webmanifest', 'icon.svg'];
self.addEventListener('install', e => { e.waitUntil(caches.open(SHELL).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== SHELL && k !== 'aeo-data').map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.includes('/data') || url.pathname.endsWith('.json')) {
    e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open('aeo-data').then(x => x.put(e.request, c)); return r; })
      .catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(fetch(e.request).then(r => { if (r.ok && ASSETS.some(a => url.pathname.endsWith(a.replace('./', '/')))) { const c = r.clone(); caches.open(SHELL).then(x => x.put(e.request, c)); } return r; })
    .catch(() => caches.match(e.request).then(m => m || caches.match('index.html'))));
});
