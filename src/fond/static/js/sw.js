// Fond service worker: zorgt dat de lessen, de kookmodus en je lijst offline werken.
//
// - Pagina's: eerst het netwerk (dan zie je altijd het nieuwste), en als dat niet
//   lukt of te lang duurt de bewaarde kopie.
// - Statische bestanden (CSS, JS, lettertypen): uit de cache. Hun URL bevat een
//   versie-hash, dus een nieuwe versie heeft vanzelf een nieuwe URL.
// - Op verzoek van de app ("bijwerken") haalt hij alle open lessen alvast op.
"use strict";

const PAGINAS = "fond-paginas-v1";
const STATISCH = "fond-statisch-v1";
const OFFLINE = "/offline";
const NETWERK_GEDULD = 4000; // ms; in een kelder met één streepje liever de kopie

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(PAGINAS).then((c) => c.add(OFFLINE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const houden = [PAGINAS, STATISCH];
    for (const naam of await caches.keys()) if (!houden.includes(naam)) await caches.delete(naam);
    await self.clients.claim();
  })());
});

function bewaarbaar(res) {
  // Geen redirects (bv. naar de login) en geen foutpagina's bewaren.
  return res && res.ok && !res.redirected && res.type === "basic";
}

async function netwerkEerst(request) {
  const cache = await caches.open(PAGINAS);
  const netwerk = fetch(request).then((res) => {
    if (bewaarbaar(res)) cache.put(request, res.clone());
    return res;
  });
  const wachten = new Promise((resolve) => setTimeout(resolve, NETWERK_GEDULD, null));
  try {
    const snel = await Promise.race([netwerk, wachten]);
    if (snel) return snel;
  } catch (e) { /* offline: val terug op de kopie */ }
  const kopie = await cache.match(request, { ignoreVary: true });
  if (kopie) return kopie;
  try { return await netwerk; } catch (e) {}
  return (await cache.match(OFFLINE)) || new Response("Offline", { status: 503 });
}

async function cacheEerst(request) {
  const cache = await caches.open(STATISCH);
  const kopie = await cache.match(request);
  if (kopie) return kopie;
  const res = await fetch(request);
  if (bewaarbaar(res)) cache.put(request, res.clone());
  return res;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname === "/sw.js" || url.pathname === "/login") return;
  if (url.pathname.startsWith("/static/") || url.pathname.startsWith("/foto/")) {
    event.respondWith(cacheEerst(request));
  } else if (request.mode === "navigate" || request.headers.get("HX-Request") || url.pathname === "/offline.json") {
    event.respondWith(netwerkEerst(request));
  }
});

async function allesBijwerken() {
  const res = await fetch("/offline.json", { credentials: "same-origin" });
  if (!res.ok || res.redirected) return;
  const { urls, statisch } = await res.json();
  const paginas = await caches.open(PAGINAS);
  const bestanden = await caches.open(STATISCH);
  // Eén voor één: de server is klein en er is geen haast.
  for (const url of statisch) {
    if (!(await bestanden.match(url))) {
      try { const r = await fetch(url); if (bewaarbaar(r)) await bestanden.put(url, r); } catch (e) {}
    }
  }
  for (const url of urls) {
    try { const r = await fetch(url, { credentials: "same-origin" }); if (bewaarbaar(r)) await paginas.put(url, r); } catch (e) {}
  }
}

self.addEventListener("message", (event) => {
  if (event.data === "bijwerken") event.waitUntil(allesBijwerken());
  if (event.data === "vergeten") {
    // Bij uitloggen: bewaarde pagina's weg (je reflecties en lijst staan erin).
    event.waitUntil(caches.delete(PAGINAS));
  }
});
