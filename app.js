// English Tube — 개인 공부용 유튜브 영어 학습 앱
const $ = (s, el = document) => el.querySelector(s);
const app = $("#app");

// ---------- 저장소 (브라우저 localStorage) ----------
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem("et:" + k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("et:" + k, JSON.stringify(v)); } catch {} },
};
let progress = store.get("progress", {});   // { videoId: { done, pos } }
let starred = store.get("starred", []);      // [{ vid, i, s, en, ko, title }]
let settings = store.get("settings", { mode: "both", rate: 1, follow: true });
const saveProgress = () => store.set("progress", progress);
const saveStarred = () => store.set("starred", starred);
const saveSettings = () => store.set("settings", settings);

const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (sec) => { sec = Math.floor(sec || 0); return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`; };

let courses = [];
async function loadCourses() {
  const r = await fetch("data/courses.json", { cache: "no-store" }).catch(() => null);
  courses = r && r.ok ? (await r.json()).courses : [];
}

const ytReady = new Promise((res) => {
  if (window.YT && YT.Player) return res();
  window.onYouTubeIframeAPIReady = res;
});

// ---------- 라우팅 ----------
let cleanup = null;
async function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  await loadCourses();
  const m = location.hash.match(/^#\/c\/([^/]+)\/(\d+)/);
  if (m) {
    const c = courses.find((c) => c.id === decodeURIComponent(m[1]));
    if (c && c.lessons[+m[2]]) return showLesson(c, +m[2]);
  }
  showHome();
}
window.addEventListener("hashchange", route);

// ---------- 홈 ----------
function nextIndex(c) {
  const i = c.lessons.findIndex((l) => !progress[l.videoId]?.done);
  return i < 0 ? 0 : i;
}

function showHome() {
  $("#crumb").textContent = "";
  document.title = "English Tube";
  if (!courses.length) {
    app.innerHTML = `<div class="empty"><b>아직 코스가 없어요.</b><br><br>터미널에서 이렇게 추가하세요:<br><br>
      <code>./tube add "코스 이름" https://www.youtube.com/playlist?list=...</code><br><br>
      영상, 재생목록, 채널 URL 모두 가능해요. 추가한 뒤 이 페이지를 새로고침하세요.</div>`;
    return;
  }
  let html = `<h2 class="h2">내 코스</h2>`;
  for (const c of courses) {
    const done = c.lessons.filter((l) => progress[l.videoId]?.done).length;
    const pct = c.lessons.length ? Math.round((done / c.lessons.length) * 100) : 0;
    const ni = nextIndex(c);
    html += `<div class="course">
      <div class="course-head"><h3>${esc(c.title)}</h3>
        <a href="#/c/${encodeURIComponent(c.id)}/${ni}"><button class="primary">${done ? "이어서 학습" : "시작하기"} · ${ni + 1}강</button></a></div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div style="color:var(--sub);font-size:13px;margin-bottom:6px">${done}/${c.lessons.length} 완료 (${pct}%)</div>
      <details ${c.lessons.length <= 12 ? "open" : ""}><summary style="cursor:pointer;color:var(--sub);font-size:14px">레슨 목록</summary>
      <ul class="lessons">${c.lessons.map((l, i) => {
        const p = progress[l.videoId];
        const meta = [l.channel, l.duration ? fmt(l.duration) : "", l.ko === "none" ? "영어 자막만" : ""].filter(Boolean).join(" · ");
        return `<li class="${p?.done ? "done" : ""}"><a href="#/c/${encodeURIComponent(c.id)}/${i}">
          <span class="n">${i + 1}</span><span class="t">${esc(l.title)}</span><span class="m">${esc(meta)}</span></a></li>`;
      }).join("")}</ul></details></div>`;
  }
  if (starred.length) {
    html += `<h2 class="h2">복습 문장 (${starred.length})</h2><div class="course"><ul class="starred">${starred.slice().reverse().map((s) => {
      const c = courses.find((c) => c.lessons.some((l) => l.videoId === s.vid));
      const li = c ? c.lessons.findIndex((l) => l.videoId === s.vid) : -1;
      const link = c ? `#/c/${encodeURIComponent(c.id)}/${li}?t=${s.i}` : "";
      return `<li><div>${esc(s.en)}</div>${s.ko ? `<div class="ko">${esc(s.ko)}</div>` : ""}
        <div class="src">${esc(s.title)} · ${fmt(s.s)}${link ? ` <a href="${link}"><button>들으러 가기</button></a>` : ""}
        <button data-unstar="${s.vid}:${s.i}">삭제</button></div></li>`;
    }).join("")}</ul></div>`;
  }
  app.innerHTML = html;
  app.querySelectorAll("[data-unstar]").forEach((b) => b.onclick = () => {
    const [vid, i] = b.dataset.unstar.split(":");
    starred = starred.filter((s) => !(s.vid === vid && s.i === +i));
    saveStarred(); showHome();
  });
}

// ---------- 레슨 ----------
async function showLesson(course, idx) {
  const lesson = course.lessons[idx];
  const vid = lesson.videoId;
  $("#crumb").textContent = `${course.title} › ${idx + 1}. ${lesson.title}`;
  document.title = lesson.title;
  app.innerHTML = "";
  app.append($("#lesson-tpl").content.cloneNode(true));
  const root = $(".lesson");

  const subs = await fetch(`data/subs/${vid}.json`, { cache: "no-store" }).then((r) => r.json());
  const S = subs.sentences;
  $("#script-title").textContent = `스크립트 · ${S.length}문장`;

  // 스크립트 목록
  const list = $("#script");
  const isStar = (i) => starred.some((s) => s.vid === vid && s.i === i);
  list.innerHTML = S.map((s, i) => `<li data-i="${i}" class="${isStar(i) ? "starred-s" : ""}">
    <span class="tm">${fmt(s.s)}</span><div class="en">${esc(s.en)}</div>${s.ko ? `<div class="ko">${esc(s.ko)}</div>` : ""}</li>`).join("");
  const items = [...list.children];

  // 상태
  let cur = -1, repeat = false, autoPause = false, pausedAt = -1, player = null, timer = null;

  // 자막 모드
  const setMode = (m) => {
    settings.mode = m; saveSettings();
    root.classList.remove("m-both", "m-en", "m-ko", "m-hide");
    root.classList.add("m-" + m);
    $("#modes").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
  };
  setMode(settings.mode);
  $("#modes").onclick = (e) => e.target.dataset.mode && setMode(e.target.dataset.mode);

  const setRate = (r) => {
    settings.rate = r; saveSettings();
    player?.setPlaybackRate?.(r);
    $("#rates").querySelectorAll("button").forEach((b) => b.classList.toggle("on", +b.dataset.rate === r));
  };
  $("#rates").onclick = (e) => e.target.dataset.rate && setRate(+e.target.dataset.rate);

  $("#follow").checked = settings.follow;
  root.classList.toggle("following", settings.follow);
  $("#follow").onchange = (e) => {
    settings.follow = e.target.checked; saveSettings();
    root.classList.toggle("following", settings.follow);
    if (settings.follow && cur >= 0) follow(items[cur]);
  };

  const findIdx = (t) => {
    let lo = 0, hi = S.length - 1, ans = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (S[mid].s <= t + 0.05) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
    return ans;
  };

  const setStarBtn = (on) => { $("#star").innerHTML = on ? "<b>★</b><span>저장됨</span>" : "<b>☆</b><span>저장</span>"; };
  const setPlayBtn = (playing) => { $("#play").innerHTML = playing ? "<b>⏸</b><span>정지</span>" : "<b>▶</b><span>재생</span>"; };
  const isPhone = () => window.matchMedia("(max-width: 900px)").matches;
  const follow = (el) => {
    if (isPhone()) {
      // 위에 고정된 영상 영역 바로 아래로 현재 문장을 가져온다
      const top = el.getBoundingClientRect().top + window.scrollY - $(".stick").offsetHeight - 8;
      window.scrollTo({ top, behavior: "smooth" });
    } else {
      const box = $("#script");
      box.scrollTo({ top: el.offsetTop - box.clientHeight / 2 + el.offsetHeight / 2, behavior: "smooth" });
    }
  };

  const show = (i) => {
    if (i === cur) return;
    items[cur]?.classList.remove("active", "revealed");
    cur = i;
    $("#current").classList.remove("revealed");
    const s = S[i];
    $(".cur-en").textContent = s ? s.en : "";
    $(".cur-ko").textContent = s ? s.ko : "";
    setStarBtn(s && isStar(i));
    if (s) {
      items[i].classList.add("active");
      if (settings.follow) follow(items[i]);
    }
  };

  const seekTo = (i, play = true) => {
    i = Math.max(0, Math.min(S.length - 1, i));
    pausedAt = -1;
    player.seekTo(Math.max(0, S[i].s - 0.05), true);
    show(i);
    if (play) player.playVideo();
  };

  // 플레이어
  await ytReady;
  const startIdx = +(location.hash.match(/\?t=(\d+)/)?.[1] ?? -1);
  const resumeAt = startIdx >= 0 ? S[startIdx]?.s ?? 0 : (progress[vid]?.done ? 0 : progress[vid]?.pos || 0);
  player = new YT.Player("player", {
    videoId: vid,
    playerVars: { start: Math.floor(Math.max(0, resumeAt - 1)), rel: 0, modestbranding: 1, playsinline: 1, cc_load_policy: 0, iv_load_policy: 3 },
    events: {
      onReady: () => {
        setRate(settings.rate); show(findIdx(resumeAt));
        setTimeout(() => cur >= 0 && settings.follow && follow(items[cur]), 500); // 레이아웃이 잡힌 뒤 한 번 더
      },
      onStateChange: (e) => {
        // 유튜브 기본 자막은 끈다 (앱 자막과 겹치지 않게)
        if (e.data === YT.PlayerState.PLAYING) { try { player.unloadModule("captions"); player.unloadModule("cc"); } catch {} }
        setPlayBtn(e.data === YT.PlayerState.PLAYING || e.data === YT.PlayerState.BUFFERING);
        if (e.data === YT.PlayerState.ENDED) markDone(false);
      },
    },
  });

  window._et = { get player() { return player; }, get cur() { return cur; }, get repeat() { return repeat; }, S };
  timer = setInterval(() => {
    if (!player?.getCurrentTime) return;
    const t = player.getCurrentTime();
    const playing = player.getPlayerState?.() === YT.PlayerState.PLAYING;
    if (cur >= 0 && playing) {
      const s = S[cur];
      const end = Math.max(s.e, (S[cur + 1]?.s ?? s.e) - 0.05);
      if (repeat && t >= s.e + 0.2) { player.seekTo(s.s, true); return; }
      if (autoPause && !repeat && t >= end - 0.15 && pausedAt !== cur) { pausedAt = cur; player.pauseVideo(); return; }
    }
    if (repeat && cur >= 0) return; // 반복 중엔 문장 고정
    if (autoPause && pausedAt === cur && !playing) return; // 쉐도잉 멈춤 중엔 방금 문장 유지
    const i = findIdx(t);
    if (i !== cur) show(i);
    if (playing && t > 3) { progress[vid] = { ...(progress[vid] || {}), pos: t }; }
  }, 100);
  const saver = setInterval(saveProgress, 3000);

  // 버튼
  list.onclick = (e) => {
    const li = e.target.closest("li"); if (!li) return;
    li.classList.add("revealed");
    seekTo(+li.dataset.i);
  };
  $("#current").onclick = () => $("#current").classList.toggle("revealed");
  const togglePlay = () => {
    if (player.getPlayerState() === YT.PlayerState.PLAYING) player.pauseVideo();
    else { pausedAt = cur; player.playVideo(); }
  };
  $("#play").onclick = togglePlay;
  $("#prev").onclick = () => seekTo(cur - 1);
  $("#next").onclick = () => seekTo(cur + 1);
  $("#replay").onclick = () => seekTo(cur);
  const toggleRepeat = () => { repeat = !repeat; $("#repeat").classList.toggle("on", repeat); if (repeat && cur >= 0) seekTo(cur); };
  const toggleAuto = () => { autoPause = !autoPause; pausedAt = cur; $("#autopause").classList.toggle("on", autoPause); };
  $("#repeat").onclick = toggleRepeat;
  $("#autopause").onclick = toggleAuto;
  const toggleStar = () => {
    if (cur < 0) return;
    if (isStar(cur)) starred = starred.filter((s) => !(s.vid === vid && s.i === cur));
    else starred.push({ vid, i: cur, s: S[cur].s, en: S[cur].en, ko: S[cur].ko, title: lesson.title });
    saveStarred();
    items[cur].classList.toggle("starred-s", isStar(cur));
    setStarBtn(isStar(cur));
  };
  $("#star").onclick = toggleStar;

  const go = (i) => { location.hash = `#/c/${encodeURIComponent(course.id)}/${i}`; };
  function markDone(navigate = true) {
    progress[vid] = { ...(progress[vid] || {}), done: true, pos: 0 };
    saveProgress();
    if (navigate) idx + 1 < course.lessons.length ? go(idx + 1) : (location.hash = "#/");
  }
  $("#done").textContent = idx + 1 < course.lessons.length ? "완료하고 다음 레슨 →" : "완료 (코스 마지막)";
  $("#done").onclick = () => markDone(true);
  $("#prev-lesson").disabled = idx === 0;
  $("#prev-lesson").onclick = () => idx > 0 && go(idx - 1);

  const onKey = (e) => {
    if (e.target.matches?.("input, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (k === " ") { e.preventDefault(); togglePlay(); }
    else if (k === "ArrowLeft") { e.preventDefault(); seekTo(cur - 1); }
    else if (k === "ArrowRight") { e.preventDefault(); seekTo(cur + 1); }
    else if (k === "ArrowDown") { e.preventDefault(); seekTo(cur); }
    else if (k === "r" || k === "R") toggleRepeat();
    else if (k === "p" || k === "P") toggleAuto();
    else if (k === "s" || k === "S") toggleStar();
    else if (["1", "2", "3", "4"].includes(k)) setMode(["both", "en", "ko", "hide"][+k - 1]);
  };
  document.addEventListener("keydown", onKey);

  cleanup = () => {
    clearInterval(timer); clearInterval(saver); saveProgress();
    document.removeEventListener("keydown", onKey);
    try { player?.destroy(); } catch {}
  };
}

window.addEventListener("beforeunload", saveProgress);
const firstRoute = route();

// 오프라인 대비 (https 또는 localhost에서만 동작)
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("sw.js").then(async () => {
    const reg = await navigator.serviceWorker.ready;
    await firstRoute.catch(() => {});
    const urls = courses.flatMap((c) => c.lessons.map((l) => `data/subs/${l.videoId}.json`));
    reg.active?.postMessage({ type: "precache", urls });
  }).catch(() => {});
}
