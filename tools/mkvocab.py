# -*- coding: utf-8 -*-
"""단어장 만들기: python tools/mkvocab.py <batch.json>

batch.json = { "<videoId>": [ [단어, 발음기호, 품사, 뜻, 예문EN, 예문KO, (찾을 정규식)], ... ], ... }
- 영상 자막에서 단어가 처음 나오는 문장을 찾아 "영상 속 문장"(i)으로 연결한다.
- 찾을 정규식을 생략하면 단어 그대로 찾는다 (대소문자 무시).
- 결과: data/vocab/<videoId>.json
"""
import json, os, re, sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
batch = json.load(open(sys.argv[1], encoding="utf-8"))
bad = 0
for vid, rows in batch.items():
    S = json.load(open(f"{APP}/data/subs/{vid}.json", encoding="utf-8"))["sentences"]
    words = []
    for r in rows:
        w, ipa, pos, ko, ex_en, ex_ko = r[:6]
        find = r[6] if len(r) > 6 and r[6] else re.escape(w)
        rx = re.compile(find, re.I)
        i = next((k for k, s in enumerate(S) if rx.search(s["en"])), None)
        if i is None:
            bad += 1
            print(f"  !! {vid}: '{w}' 자막에서 못 찾음 ({find})")
        if not rx.search(ex_en):
            print(f"  ~ {vid}: '{w}' 예문에 강조 안 됨")
        d = {"w": w, "ipa": ipa, "pos": pos, "ko": ko, "ex": [ex_en, ex_ko]}
        if find != re.escape(w):
            d["find"] = find
        if i is not None:
            d["i"] = i
        words.append(d)
    os.makedirs(f"{APP}/data/vocab", exist_ok=True)
    with open(f"{APP}/data/vocab/{vid}.json", "w", encoding="utf-8") as f:
        json.dump({"videoId": vid, "words": words}, f, ensure_ascii=False, indent=1)
    print(f"✓ {vid}: {len(words)}단어")
print("못 찾은 단어:", bad)
