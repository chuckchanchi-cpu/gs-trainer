#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
❓ 常識選擇題生成器 — 小六常識科 MCQ 訓練（獨立 app）

Chuck 要求（2026-10-09）：
  - 使用 General_Studies/ 資料夾的最新教材文件
  - 讀取所有 Unit 1-4 的 .md 文件
  - 自動提取題目和答案
  - 提供 MCQ 訓練模式

題庫來源：本目錄下的所有 .md 文件（已內嵌於倉庫）
"""

import os
import json
import re
import random
import streamlit as st

st.set_page_config(page_title="❓ 常識選擇題生成器", page_icon="❓", layout="wide")

# ===== 教材路徑 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_md_files():
    """獲取本目錄下所有 .md 文件（排除 README.md）"""
    files = []
    for f in os.listdir(BASE_DIR):
        if f.endswith(".md") and not f.startswith(".") and f != "README.md":
            files.append(os.path.join(BASE_DIR, f))
    return sorted(files)

MD_FILES = get_md_files()

# ===== 中文數字轉阿拉伯數字 =====
CHINESE_NUMBERS = {
    '零': 0, '一': 1, '壹': 1, '二': 2, '貳': 2, '兩': 2, '三': 3, '叁': 3,
    '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陸': 6, '七': 7, '柒': 7,
    '八': 8, '捌': 8, '九': 9, '玖': 9, '十': 10, '拾': 10,
    '廿': 20, '卅': 30, '卌': 40
}

def chinese_to_number(text):
    """將中文數字轉換為阿拉伯數字"""
    text = text.strip()
    if text in CHINESE_NUMBERS:
        return str(CHINESE_NUMBERS[text])
    
    # 處理複合數字如 "十一", "十二"
    result = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char in CHINESE_NUMBERS:
            num = CHINESE_NUMBERS[char]
            if num == 10 and i + 1 < len(text) and text[i+1] in CHINESE_NUMBERS:
                next_num = CHINESE_NUMBERS[text[i+1]]
                if next_num <= 10:
                    result += 10 + next_num
                    i += 2
                    continue
            elif num == 10:
                result += 10
            else:
                result += num
        i += 1
    
    return str(result) if result > 0 else text

# ===== 解析 Markdown 題目 =====
def parse_questions_from_md(filepath):
    """從 Markdown 文件提取問答對"""
    questions = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 檢測單元名稱（支持中英文數字）
        unit_match = re.search(r'(?:單元|Unit)\s*([一二三四五六七八九十\d]+)', content)
        unit_num = "?"
        if unit_match:
            raw_num = unit_match.group(1)
            unit_num = chinese_to_number(raw_num)
        
        lines = content.split('\n')
        current_q = ""
        options = []
        answer = ""
        q_number = None
        
        for line in lines:
            stripped = line.strip()
            
            # 檢測問題行（數字開頭 + 標點）
            q_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
            if q_match:
                # 保存上一個問題
                if current_q and answer:
                    questions.append({
                        "unit": unit_num,
                        "question": current_q,
                        "options": options[:4] if len(options) >= 2 else ["A", "B", "C", "D"],
                        "answer": answer,
                        "hint": ""
                    })
                q_number = int(q_match.group(1))
                current_q = q_match.group(2).replace('**', '').strip()
                options = []
                answer = ""
            
            # 檢測選項 [A-D]
            elif re.match(r'^[A-Da-d][.、)]\s*', stripped):
                opt_text = re.sub(r'^[A-Da-d][.、)]\s*', '', stripped)
                if opt_text:
                    options.append(opt_text)
            
            # 檢測答案標記 **答案** ✅
            elif '**✅' in stripped or '✅ **' in stripped:
                ans_match = re.search(r'\*\*(.+?)\*\*', stripped)
                if ans_match:
                    answer = ans_match.group(1)
            
            # 檢測填空答案 → **答案**
            elif '→ **' in stripped:
                answer = stripped.split('→ **')[1].split('**')[0]
            
            # 檢測判斷題 ✓/✗
            elif '→ ✗' in stripped:
                answer = '✗'
            elif '→ ✓' in stripped:
                answer = '✓'
            
            # 檢測表格中的答案欄位
            elif stripped.startswith('|') and ('✅' in stripped or '✓' in stripped):
                cells = [c.strip() for c in stripped.split('|') if c.strip()]
                for cell in cells:
                    if '✅' in cell or '✓' in cell:
                        clean = cell.replace('✅', '').replace('✓', '').strip()
                        if clean and len(clean) < 50:
                            answer = clean
            
            # 檢測定義式答案
            elif re.match(r'^→\s*.*$', stripped):
                ans_part = stripped.split('→')[1].strip().lstrip('*').rstrip('*')
                if ans_part and len(ans_part) < 50:
                    answer = ans_part
        
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
        st.error(f"❌ 讀取文件失敗：{filepath} — {e}")
    
    return questions

# ===== 載入所有題目 =====
all_questions = []
unit_names = {}

if MD_FILES:
    for md_file in MD_FILES:
        filename = os.path.basename(md_file)
        questions = parse_questions_from_md(md_file)
        all_questions.extend(questions)
        
        # 提取單元名稱
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            unit_match = re.search(r'(?:單元|Unit)\s*([一二三四五六七八九十\d]+)\s*[：:]\s*(.+?)(?:\n|$)', content)
            if unit_match:
                raw_num = unit_match.group(1)
                unit_num = chinese_to_number(raw_num)
                unit_name = unit_match.group(2).strip()
                unit_names[unit_num] = unit_name
        except:
            pass
    
    # 去重：移除重複的問題（相同 question text）
    seen = set()
    unique_questions = []
    for q in all_questions:
        key = (q["unit"], q["question"])
        if key not in seen:
            seen.add(key)
            unique_questions.append(q)
    all_questions = unique_questions
else:
    st.warning("⚠️ 未找到任何 .md 文件！")

# ===== 頁面 =====
st.title("❓ 常識選擇題生成器")
st.caption("小六常識科 MCQ 訓練 — 揀單元 → 每輪出題 → 即場作答自動批改。題目 100% 嚟自教材！")

if "gs_questions" not in st.session_state:
    st.session_state.gs_questions = []
if "gs_checked" not in st.session_state:
    st.session_state.gs_checked = False

# ===== Sidebar =====
with st.sidebar:
    st.header("⚙️ 設定")
    
    if all_questions:
        units = sorted(set(q["unit"] for q in all_questions))
        unit_options = units
        
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
            st.markdown(f"**文件數量：** {len(MD_FILES)}")
            for u in units:
                name = unit_names.get(u, "")
                count_u = sum(1 for q in all_questions if q["unit"] == u)
                st.markdown(f"- Unit {u}: {name} ({count_u} 題)")
    else:
        st.warning("⚠️ 未找到任何題目！")

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
