const CACHE_NAME = "planpal-app-v13";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/style.css?v=app23",
  "/app.js?v=app23",
  "/manifest.json",
  "/icon.svg",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS).catch(() => undefined)),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((name) => name.startsWith("planpal-app-") && name !== CACHE_NAME).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);

  if (event.request.method !== "GET" || requestUrl.origin !== self.location.origin
    || requestUrl.pathname.startsWith("/api/") || requestUrl.pathname === "/health") {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          const cacheKey = event.request.mode === "navigate" ? "/index.html" : event.request;
          event.waitUntil(caches.open(CACHE_NAME)
            .then((cache) => cache.put(cacheKey, copy)).catch(() => undefined));
        }
        return response;
      })
      .catch(async () => (await caches.match(event.request.mode === "navigate" ? "/index.html" : event.request)) || Response.error()),
  );
});
