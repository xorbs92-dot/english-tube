# -*- coding: utf-8 -*-
"""단어장 발음 파일 만들기 (Mac 전용): python tools/mkaudio.py

data/vocab/*.json 의 단어(w)와 예문(ex[0])을 Mac의 미국식·영국식 음성으로 읽어
data/audio/<해시>.m4a 로 저장하고, 단어장 JSON에 파일명을 적는다.
  미국식(기본): "a"(단어), "xa"(예문) · 영국식: "ab", "xab"
이미 있는 파일은 다시 만들지 않는다. 휴대폰에서는 이 파일을 재생한다
(아이폰 기기 음성은 무음 모드·홈 화면 앱에서 소리가 안 나는 경우가 많아서).
"""
import glob, hashlib, json, os, re, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

VOICES = {"": os.environ.get("TUBE_VOICE_US", "Ava (Premium)"), "b": os.environ.get("TUBE_VOICE_UK", "Jamie (Premium)")}
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{APP}/data/audio"
os.makedirs(OUT, exist_ok=True)


def speakable(t):
    t = t.replace(" / ", ", ").replace("...", " ").replace("…", " ")
    return re.sub(r"\s+", " ", t).strip(" ,")


def name_for(voice, text):
    return hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:12] + ".m4a"


def render(job):
    voice, text, fn = job
    dst = f"{OUT}/{fn}"
    if os.path.exists(dst):
        return 0
    with tempfile.TemporaryDirectory() as td:
        aiff = f"{td}/a.aiff"
        subprocess.run(["say", "-v", voice, "-o", aiff, text], check=True)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "32000", "-c", "1", aiff, dst], check=True)
    return 1


jobs, files = {}, []
for p in sorted(glob.glob(f"{APP}/data/vocab/*.json")):
    d = json.load(open(p, encoding="utf-8"))
    for w in d["words"]:
        for suf, voice in VOICES.items():
            t = speakable(w.get("say") or w["w"])
            w["a" + suf] = fn = name_for(voice, t); jobs[fn] = (voice, t)
            if w.get("ex"):
                t = speakable(w["ex"][0])
                w["xa" + suf] = fn = name_for(voice, t); jobs[fn] = (voice, t)
    files.append((p, d))

with ThreadPoolExecutor(8) as ex:
    made = sum(ex.map(render, [(v, t, fn) for fn, (v, t) in jobs.items()]))
for p, d in files:
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)

used = set(jobs)
stale = [f for f in os.listdir(OUT) if f.endswith(".m4a") and f not in used]
for f in stale:
    os.remove(f"{OUT}/{f}")
print(f"발음 파일 {len(jobs)}개 (새로 만듦 {made}, 지운 옛 파일 {len(stale)})")
