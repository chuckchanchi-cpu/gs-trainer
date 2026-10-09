# -*- coding: utf-8 -*-
"""Smoke test：語法 + gs_parser 解析 + AI 答案比對 + JSON 抽取"""
import py_compile, sys, json, re, unicodedata, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")
py_compile.compile("app.py", doraise=True)
py_compile.compile("gs_parser.py", doraise=True)
print("✅ syntax OK")

sys.path.insert(0, ".")
import gs_parser
data = gs_parser.load_all(".")
qs = data["questions"]
print(f"✅ parser: {len(qs)} 題 / {len(data['topics'])} 主題")

# 所有題目嘅 answer 必須喺 options 入面（批改正確性嘅前提）
bad = [q for q in qs if q["answer"] not in q["options"]]
print(f"✅ answer∈options: {len(qs)-len(bad)}/{len(qs)}" + (f" ❌ {len(bad)} 條有問題" if bad else ""))

# ===== 複製 app.py 入面嘅 _norm/_match_answer/_extract_json_array 邏輯做測試 =====
def _norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s「」『』\"'“”’（）()]+", "", s)

def _match_answer(ans, opts):
    if not ans:
        return None
    ans = str(ans).strip()
    if ans in opts:
        return ans
    na = _norm(ans)
    if not na:
        return None
    for o in opts:
        if _norm(o) == na:
            return o
    m = re.fullmatch(r"[a-dA-D]", na)
    if m:
        idx = ord(m.group(0).upper()) - ord("A")
        if idx < len(opts):
            return opts[idx]
    m = re.match(r"^[a-dA-D][.、)）:：]\s*(.+)$", ans)
    if m:
        cand = m.group(1).strip()
        for o in opts:
            if _norm(cand) == _norm(o):
                return o
        if cand in opts:
            return cand
    hits = [o for o in opts if _norm(o) and _norm(o) in na]
    if len(hits) == 1:
        return hits[0]
    return None

def _extract_json_array(text):
    if not text:
        return None
    t = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
    if m:
        t = m.group(1).strip()
    dec = json.JSONDecoder()
    for cand in (t, re.sub(r",\s*([\]}])", r"\1", t.replace("，", ",").replace("、", ","))):
        idx = cand.find("[")
        while idx != -1:
            try:
                arr, _ = dec.raw_decode(cand, idx)
                if isinstance(arr, list):
                    return arr
            except json.JSONDecodeError:
                pass
            idx = cand.find("[", idx + 1)
    return None

opts = ["濕潤無鱗", "乾燥有鱗片", "長有羽毛", "長有毛髮"]
cases = [
    ("濕潤無鱗", "濕潤無鱗"),
    ("A. 濕潤無鱗", "濕潤無鱗"),
    ("A、濕潤無鱗", "濕潤無鱗"),
    ("B", "乾燥有鱗片"),
    ("濕潤無鱗（兩棲類特徵）", "濕潤無鱗"),
    ("　濕潤無鱗　", "濕潤無鱗"),
    ("亂噏廿四", None),
    ("", None),
]
for ans, expect in cases:
    got = _match_answer(ans, opts)
    flag = "✅" if got == expect else "❌"
    print(f"{flag} _match_answer({ans!r}) = {got!r} (expect {expect!r})")

# JSON 抽取：正常 / code fence / trailing comma / 前後有多餘文字 / 截斷
good = '[{"question":"Q","options":["A","B","C","D"],"answer":"A","explanation":"E"}]'
fenced = "以下係題目：\n```json\n" + good + "\n```\n完"
trailing = '[{"question":"Q","options":["A","B",],"answer":"A","explanation":"E",}]'
extra = "結果如下：" + good + " 希望啱用"
truncated = good[:60]  # 模擬 max_tokens 截斷
for name, blob, expect_ok in [("normal", good, True), ("fenced", fenced, True),
                               ("trailing-comma", trailing, True), ("extra-text", extra, True),
                               ("truncated", truncated, False)]:
    arr = _extract_json_array(blob)
    ok = (arr is not None and len(arr) == 1)
    flag = "✅" if ok == expect_ok else "❌"
    print(f"{flag} extract[{name}] -> {'ok' if arr else 'None'}")

print("done")
