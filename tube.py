#!/usr/bin/env python3
"""English Tube — 유튜브 영상/재생목록을 공부용 코스로 만드는 도구 (개인 공부용).

사용법:
  ./tube add "코스 이름" <유튜브 URL> [URL ...]   # 영상, 재생목록, 채널 URL 모두 가능
  ./tube add "코스 이름" <재생목록 URL> --limit=10 # 앞의 10개만
  ./tube list                                     # 코스 목록 보기
  ./tube refresh <videoId>                        # 자막 다시 받기
  ./tube remove "코스 이름"                        # 코스 삭제 (자막 파일은 남김)
  ./tube missing                                  # 한글 자막이 빈 영상 목록
  ./tube setko <videoId> <번역.txt>               # '번호<TAB>번역' 파일로 한글 채우기

한글 자막 우선순위:
  1) 영상에 사람이 만든 한국어 자막이 있으면 사용
  2) 유튜브 자동번역 (가끔 막힘)
  3) 환경변수 ANTHROPIC_API_KEY 가 있으면 Claude로 번역
  4) 없으면 영어만 저장 (앱에서 영어만 표시)
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import warnings

warnings.filterwarnings("ignore")

from youtube_transcript_api import YouTubeTranscriptApi  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
SUBS = os.path.join(DATA, "subs")
COURSES = os.path.join(DATA, "courses.json")

api = YouTubeTranscriptApi()
LIMIT = None  # --limit=N : 재생목록에서 앞의 N개만


# ---------- storage ----------
def load_courses():
    if os.path.exists(COURSES):
        with open(COURSES, encoding="utf-8") as f:
            return json.load(f)
    return {"courses": []}


def save_courses(d):
    os.makedirs(DATA, exist_ok=True)
    with open(COURSES, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def slug(name):
    s = re.sub(r"[^\w가-힣]+", "-", name).strip("-").lower()
    return s or "course"


# ---------- url → videos ----------
def video_id_of(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[\w-]{11}", url):
        return url
    return None


def oembed(vid):
    q = urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
    try:
        with urllib.request.urlopen(f"https://www.youtube.com/oembed?{q}", timeout=15) as r:
            d = json.load(r)
            return d.get("title", vid), d.get("author_name", "")
    except Exception:
        return vid, ""


def expand(url):
    """URL 하나를 [(videoId, title, channel, duration)] 목록으로."""
    if "list=" not in url and video_id_of(url):
        vid = video_id_of(url)
        t, c = oembed(vid)
        return [(vid, t, c, None)]
    import yt_dlp

    with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True, "no_warnings": True}) as y:
        info = y.extract_info(url, download=False)
    out = []

    def walk(node):
        for e in node.get("entries") or []:
            if e.get("_type") == "playlist" or (e.get("entries")):
                walk(e)
            elif e.get("id") and len(e["id"]) == 11:
                out.append((e["id"], e.get("title") or e["id"],
                            e.get("channel") or e.get("uploader") or info.get("channel") or "",
                            e.get("duration")))

    walk(info)
    return out[:LIMIT] if LIMIT else out


# ---------- subtitles ----------
NOISE = re.compile(r"^[\[(][^\])]*[\])]$")  # [Music], (Laughter)
END = re.compile(r"[.?!…][\"')\]]*$")


def clean(t):
    t = t.replace("\n", " ").replace("&amp;", "&").replace("&#39;", "'")
    return re.sub(r"\s+", " ", t).strip()


def to_sentences(snips, generated):
    """자막 조각들을 문장 단위로 합친다."""
    items = [(s.start, s.duration, clean(s.text)) for s in snips]
    items = [i for i in items if i[2] and not NOISE.match(i[2])]
    max_len = 9.0 if generated else 14.0
    out, cur = [], []
    for idx, (st, du, tx) in enumerate(items):
        cur.append((st, du, tx))
        nxt = items[idx + 1][0] if idx + 1 < len(items) else None
        span = st + du - cur[0][0]
        gap = (nxt - (st + du)) if nxt is not None else 99
        if END.search(tx) or span >= max_len or gap > 1.2 or nxt is None:
            end = st + du if nxt is None else min(st + du, nxt)
            out.append({"s": round(cur[0][0], 2), "e": round(max(end, cur[0][0] + 0.5), 2),
                        "en": " ".join(c[2] for c in cur), "ko": ""})
            cur = []
    return out


def attach_ko(sents, ko_snips):
    """한국어 자막 조각을 시간 기준으로 영어 문장에 붙인다."""
    if not sents:
        return
    starts = [x["s"] for x in sents]
    for s in ko_snips:
        tx = clean(s.text)
        if not tx or NOISE.match(tx):
            continue
        mid = s.start + s.duration / 2
        if mid < starts[0] - 0.5:
            continue  # 번역자 크레딧 등
        i = max(j for j, st in enumerate(starts) if st <= mid + 0.3) if mid + 0.3 >= starts[0] else 0
        sents[i]["ko"] = (sents[i]["ko"] + " " + tx).strip()


def claude_translate(sents):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return False
    model = os.environ.get("TUBE_MODEL", "claude-sonnet-5-5")
    for b in range(0, len(sents), 60):
        chunk = sents[b:b + 60]
        lines = "\n".join(f"{i+1}\t{x['en']}" for i, x in enumerate(chunk))
        prompt = (
            "다음은 영어 회화 영상의 자막 문장들이야. 각 줄을 자연스러운 한국어 구어체로 번역해줘. "
            "앞뒤 문맥을 참고하되 줄 수와 번호는 반드시 그대로 유지하고, '번호<TAB>번역' 형식으로만 출력해.\n\n"
            + lines
        )
        body = json.dumps({"model": model, "max_tokens": 8000,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            text = "".join(c.get("text", "") for c in json.load(r)["content"])
        for line in text.splitlines():
            m = re.match(r"\s*(\d+)\s*\t\s*(.+)", line)
            if m and 0 < int(m.group(1)) <= len(chunk):
                chunk[int(m.group(1)) - 1]["ko"] = m.group(2).strip()
        print(f"    Claude 번역 {min(b + 60, len(sents))}/{len(sents)}")
    return True


def fetch_subs(vid, title="", channel="", force=False):
    path = os.path.join(SUBS, f"{vid}.json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    tl = api.list(vid)
    en = None
    try:
        en = tl.find_manually_created_transcript(["en", "en-US", "en-GB", "en-CA", "en-AU"])
    except Exception:
        try:
            en = tl.find_generated_transcript(["en", "en-US", "en-GB"])
        except Exception:
            pass
    if en is None:
        raise RuntimeError("영어 자막이 없는 영상")
    sents = to_sentences(en.fetch(), en.is_generated)

    ko_src = "none"
    try:
        ko = tl.find_manually_created_transcript(["ko"])
        attach_ko(sents, ko.fetch())
        ko_src = "youtube-ko"
    except Exception:
        try:
            attach_ko(sents, en.translate("ko").fetch())
            ko_src = "youtube-auto-translate"
        except Exception:
            try:
                if claude_translate(sents):
                    ko_src = "claude"
            except Exception as ex:
                print(f"    Claude 번역 실패: {ex}")

    d = {"videoId": vid, "title": title, "channel": channel,
         "enSource": "auto" if en.is_generated else "manual", "koSource": ko_src,
         "sentences": sents}
    os.makedirs(SUBS, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return d


# ---------- commands ----------
def cmd_add(name, urls):
    db = load_courses()
    course = next((c for c in db["courses"] if c["title"] == name), None)
    if course is None:
        course = {"id": slug(name), "title": name, "lessons": []}
        db["courses"].append(course)
    have = {l["videoId"] for l in course["lessons"]}
    for url in urls:
        print(f"▶ {url}")
        vids = expand(url)
        print(f"  영상 {len(vids)}개")
        for n, (vid, title, ch, dur) in enumerate(vids, 1):
            if vid in have:
                print(f"  [{n}] 이미 있음: {title}")
                continue
            try:
                time.sleep(1.0)  # 유튜브가 막지 않게 천천히
                d = fetch_subs(vid, title, ch)
                course["lessons"].append({"videoId": vid, "title": title, "channel": ch, "duration": dur,
                                          "sentences": len(d["sentences"]), "ko": d["koSource"]})
                have.add(vid)
                print(f"  [{n}] ✓ {title}  (문장 {len(d['sentences'])}, 한글: {d['koSource']})")
            except Exception as ex:
                print(f"  [{n}] ✗ {title}: {type(ex).__name__} {str(ex).splitlines()[0][:100]}")
            save_courses(db)
    save_courses(db)
    print(f"\n완료: '{name}' 레슨 {len(course['lessons'])}개")


def cmd_list():
    for c in load_courses()["courses"]:
        print(f"■ {c['title']}  ({len(c['lessons'])}개)")
        for i, l in enumerate(c["lessons"], 1):
            print(f"   {i:>2}. {l['title']}  [{l['videoId']}] 한글:{l.get('ko')}")


def cmd_refresh(vid):
    db = load_courses()
    for c in db["courses"]:
        for l in c["lessons"]:
            if l["videoId"] == vid:
                d = fetch_subs(vid, l["title"], l["channel"], force=True)
                l["sentences"], l["ko"] = len(d["sentences"]), d["koSource"]
                print(f"✓ {l['title']} (한글: {d['koSource']})")
    save_courses(db)


def cmd_missing():
    """한글이 비어 있는 영상 목록."""
    for c in load_courses()["courses"]:
        for l in c["lessons"]:
            p = os.path.join(SUBS, f"{l['videoId']}.json")
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                s = json.load(f)["sentences"]
            empty = sum(1 for x in s if not x["ko"])
            if empty:
                print(f"{l['videoId']}\t한글 없음 {empty}/{len(s)}\t{c['title']} › {l['title']}")


def cmd_setko(vid, txt):
    """'번호<TAB>번역' 형식 파일로 한글 자막을 채운다 (번호는 0부터)."""
    p = os.path.join(SUBS, f"{vid}.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    n = 0
    with open(txt, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*(\d+)\t(.+)", line)
            if m and int(m.group(1)) < len(d["sentences"]):
                d["sentences"][int(m.group(1))]["ko"] = m.group(2).strip()
                n += 1
    d["koSource"] = "claude"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    db = load_courses()
    for c in db["courses"]:
        for l in c["lessons"]:
            if l["videoId"] == vid:
                l["ko"] = "claude"
    save_courses(db)
    print(f"✓ {vid}: {n}/{len(d['sentences'])}문장 한글 입력")


def cmd_remove(name):
    db = load_courses()
    db["courses"] = [c for c in db["courses"] if c["title"] != name]
    save_courses(db)
    print("삭제됨")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "add":
        lim = [x for x in a if x.startswith("--limit=")]
        LIMIT = int(lim[0].split("=")[1]) if lim else None
        cmd_add(a[1], [x for x in a[2:] if not x.startswith("--")])
    elif a[:1] == ["list"]:
        cmd_list()
    elif len(a) == 2 and a[0] == "refresh":
        cmd_refresh(a[1])
    elif a[:1] == ["missing"]:
        cmd_missing()
    elif len(a) == 3 and a[0] == "setko":
        cmd_setko(a[1], a[2])
    elif len(a) == 2 and a[0] == "remove":
        cmd_remove(a[1])
    else:
        print(__doc__)
