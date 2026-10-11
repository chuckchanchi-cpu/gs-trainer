# -*- coding: utf-8 -*-
"""語法檢查 + 資料題過濾器測試"""
import py_compile, os, sys, re
os.chdir(os.path.dirname(os.path.abspath(__file__)))
py_compile.compile("app.py", doraise=True)
print("✅ syntax OK")

data_q_re = re.compile(r"根據(以下|下列|資料|這|该|短文|文章)|閱讀(以下|下列|資料)|下文|上文|資料顯示|以下資料|下列資料|短文中|文章中|段落中|看資料|原文")
cases = [
    ("根據以下資料，回答第 8-11 題：某濕地每天潮水漲退……", True),
    ("閱讀下列短文，選出正確答案。", True),
    ("下文的「他」指的是誰？", True),
    ("資料顯示紅樹林面積減少。", True),
    ("紅樹林嘅根點解要伸出泥土？", False),
    ("下列哪種動物屬於兩棲類？", False),
    ("下列哪項是植物自我保護的方法？", False),
]
for q, expect in cases:
    got = bool(data_q_re.search(q) or len(q) > 120)
    flag = "✅" if got == expect else "❌"
    print(f"{flag} {'資料題' if got else '知識題'}：{q[:30]}…")

# 教材題庫入面有冇資料題殘留？
sys.path.insert(0, ".")
import gs_parser
data = gs_parser.load_all(".")
bad = [q["question"] for q in data["questions"] if data_q_re.search(q["question"])]
print(f"✅ 教材題庫 {len(data['questions'])} 題，資料題殘留 {len(bad)} 條" + (f"：{bad}" if bad else ""))
print("done")
