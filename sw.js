// 오프라인 대비: 앱 화면과 자막을 휴대폰에 저장해 두고, 신호가 약해도 열리게 한다.
// (유튜브 영상 자체는 저장할 수 없어서 재생에는 인터넷이 필요해요.)
const CACHE = "english-tube-v2";
const SHELL = ["./", "index.html", "app.js", "style.css", "manifest.json", "icon-192.png", "icon-180.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// 앱이 코스 목록을 읽은 뒤 모든 자막 파일을 미리 받아 두라고 보낸다
self.addEventListener("message", (e) => {
  if (e.data?.type === "precache" && Array.isArray(e.data.urls)) {
    e.waitUntil(caches.open(CACHE).then(async (c) => {
      for (const u of e.data.urls) {
        if (!(await c.match(u))) { try { await c.add(u); } catch {} }
      }
    }));
  }
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return; // 유튜브 등은 그대로
  // 네트워크 우선: 새 강의·번역이 있으면 바로 반영, 신호가 없으면 저장본 사용
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
        return res;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }).then((r) => r || caches.match("index.html")))
  );
});
