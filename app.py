#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
❓ 常識選擇題生成器 — 小六常識科 MCQ 訓練（獨立 app）

Chuck 要求（2026-10-09）：
  - 使用 General_Studies/ 資料夾的最新教材文件
  - 讀取所有 Unit 1-4 的 .md 文件
  - 自動提取題目和答案
  - 提供 MCQ 訓練模式

題庫來源：General_Studies/ 下的所有 .md 文件
  - Unit_1_BiologicalClassification_Chinese.md
  - Unit_2_Plants_and_Environment_20260917.md
  - Unit_3_Animals_and_Environment_20260924.md
  - 2026-10-09_常識_生物的相互關係與生態平衡.md
"""

import os
import json
import re
import random
import streamlit as st

st.set_page_config(page_title="❓ 常識選擇題生成器", page_icon="❓", layout="wide")

# ===== 教材路徑 =====
def material_dir():
    """從工作目錄尋找 General_Studies 資料夾"""
    base = os.path.dirname(os.path.abspath(__file__))
    paths = [
        os.path.join(base, "General_Studies"),
        os.path.join(base, "..", "openedujustan", "General_Studies"),
        os.path.join("/home/fring1117/.openclaw/workspace/openedujustan", "General_Studies"),
    ]
    for p in paths:
        if os.path.isdir(p):
            return os.path.normpath(p)
    return None

MAT_DIR = material_dir()

if MAT_DIR:
    md_files = sorted([f for f in os.listdir(MAT_DIR) if f.endswith(".md") and not f.startswith(".")])
else:
    md_files = []

# ===== 解析 Markdown 題目 =====
def parse_questions_from_md(filepath):
    """從 Markdown 文件提取問答對"""
    questions = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 檢測單元名稱
        unit_match = re.search(r'(?:單元|Unit)\s*(\d+)', content)
        unit_num = unit_match.group(1) if unit_match else "?"
        
        # 提取問題和答案的模式
        # 模式1: 題目 + 選項 A-D + 答案標記
        # 模式2: 填空題 → **答案** ✅
        # 模式3: 判斷題 ✓/✗
        
        lines = content.split('\n')
        current_q = ""
        options = []
        answer = ""
        
        for line in lines:
            line = line.strip()
            
            # 檢測問題行
            if re.match(r'^\d+\.', line) or (line.startswith('**') and '?' in line):
                if current_q and answer:
                    questions.append({
                        "unit": unit_num,
                        "question": current_q,
                        "options": options[:4] if len(options) >= 2 else ["A", "B", "C", "D"],
                        "answer": answer,
                        "hint": ""
                    })
                current_q = line.replace('**', '').replace('?', '').strip()
                options = []
                answer = ""
            
            # 檢測選項
            elif re.match(r'^[A-Da-d][.、)]', line):
                options.append(line[2:].strip())
            
            # 檢測答案
            elif '**' in line and ('✅' in line or '✓' in line):
                answer_match = re.search(r'\*\*(.+?)\*\*', line)
                if answer_match:
                    answer = answer_match.group(1)
            
            # 檢測填空答案
            elif '→ **' in line:
                answer = line.split('→ **')[1].split('**')[0]
            
            # 檢測判斷題答案
            elif '→ ✗' in line or '→ ✓' in line:
                answer = '✓' if '✓' in line else '✗'
        
        # 添加最後一個問題
        if current_q and answer:
            questions.append({
                "unit": unit_num,
                "question": current_q,
                "options": options[:4] if len(options) >= 2 else ["A", "B", "C", "D"],
                "answer": answer,
                "hint": ""
            })
    
    except Exception as e:
        st.error(f"❌ 讀取文件失敗：{e}")
    
    return questions

# ===== 載入所有題目 =====
all_questions = []
unit_names = {}

if MAT_DIR:
    for md_file in md_files:
        filepath = os.path.join(MAT_DIR, md_file)
        questions = parse_questions_from_md(filepath)
        all_questions.extend(questions)
        
        # 提取單元名稱
        unit_match = re.search(r'(?:單元|Unit)\s*(\d+)\s*[：:]\s*(.+?)(?:\n|$)', open(filepath, 'r', encoding='utf-8').read())
        if unit_match:
            unit_names[unit_match.group(1)] = unit_match.group(2).strip()
else:
    st.warning("⚠️ 未找到 General_Studies 資料夾！")

# ===== 頁面 =====
st.title("❓ 常識選擇題生成器")
st.caption("小六常識科 MCQ 訓練 — 揀主題 → 每輪出題 → 即場作答自動批改。題目 100% 嚟自教材！")

if "gs_questions" not in st.session_state:
    st.session_state.gs_questions = []
if "gs_checked" not in st.session_state:
    st.session_state.gs_checked = False

# ===== Sidebar =====
with st.sidebar:
    st.header("⚙️ 設定")
    
    if all_questions:
        units = sorted(set(q["unit"] for q in all_questions))
        unit_options = [u for u in units]
        
        selected_units = st.multiselect(
            "揀單元（可多選）",
            unit_options,
            format_func=lambda u: f"Unit {u}: {unit_names.get(u, '')}",
            key="gs_units",
        )
        
        count = st.slider("每輪題數", 5, min(len(all_questions), 20), 10, key="gs_count")
        
        if st.button("🎲 生成題目", type="primary", use_container_width=True):
            if not selected_units:
                st.warning("⚠️ 請先揀至少一個單元")
            else:
                pool = [q for q in all_questions if q["unit"] in selected_units]
                random.shuffle(pool)
                qs = pool[:count]
                if qs:
                    st.session_state.gs_questions = qs
                    st.session_state.gs_checked = False
                    st.rerun()
                else:
                    st.error("❌ 揀選嘅單元冇題目！")
        
        with st.expander("📚 題庫資訊"):
            st.markdown(f"**總題目數：** {len(all_questions)}")
            for u in units:
                name = unit_names.get(u, "")
                count_u = sum(1 for q in all_questions if q["unit"] == u)
                st.markdown(f"- Unit {u}: {name} ({count_u} 題)")
    else:
        st.warning("⚠️ 未找到任何題目！請檢查 General_Studies 資料夾。")

st.divider()

# ===== 出題 =====
if not st.session_state.gs_questions:
    st.info("👈 左邊 sidebar：揀單元（可多選）→ 㩒「🎲 生成題目」開始！")
    st.stop()

qs = st.session_state.gs_questions
st.subheader(f"📝 今輪 {len(qs)} 題")
for i, item in enumerate(qs):
    st.radio(f"**{i + 1}.** {item['q']}", item["options"], key=f"gs_a{i}", index=None)

c1, c2 = st.columns([1, 1])
if not st.session_state.gs_checked:
    if c1.button("✅ 檢查答案", type="primary"):
        st.session_state.gs_checked = True
        st.rerun()
else:
    results = []
    for i, item in enumerate(qs):
        user = st.session_state.get(f"gs_a{i}")
        results.append((i, user, user == item["answer"]))
    correct = sum(1 for _, _, ok in results if ok)
    st.metric("🏆 得分", f"{correct} / {len(qs)}")
    for i, user, ok in results:
        item = qs[i]
        if ok:
            st.success(f"**✅ 第 {i + 1} 題**（你揀咗「{user}」）")
        else:
            st.error(f"**❌ 第 {i + 1} 題**　你揀咗：「{user or '（未作答）'}」　正確答案：**{item['answer']}**")
        st.caption("💡 " + item["hint"])
    st.markdown("---")

if c2.button("🔄 再嚟一輪", use_container_width=True):
    selected_units = st.session_state.gs_units
    count = st.session_state.gs_count
    if selected_units:
        pool = [q for q in all_questions if q["unit"] in selected_units]
        random.shuffle(pool)
        qs = pool[:count]
        if qs:
            st.session_state.gs_questions = qs
            st.session_state.gs_checked = False
            st.rerun()
