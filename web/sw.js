// 화면 파일만 캐시합니다. /api 응답(개인 데이터)은 절대 캐시하지 않습니다.
const SHELL = 'monitor-shell-v1';
const ASSETS = ['/', '/static/app.css', '/static/icons/icon.svg'];
self.addEventListener('install', (e) => { e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin || u.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok && (u.pathname.startsWith('/static/') || u.pathname === '/')) { const c = r.clone(); caches.open(SHELL).then((x) => x.put(e.request, c)); }
    return r;
  }).catch(() => caches.match(e.request)));
});
