#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
❓ 常識選擇題生成器 — 小六常識科 MCQ 訓練

流程：
  1. 從 GitHub repo 拉最新教材（.md）
  2. 解析出主題（Unit 1-4）＋題目（填空/判斷/選擇）
  3. 揀主題 → 每輪出題 → 作答 → 自動批改

AI 生成／AI 批改解釋：由你在 Streamlit 端接（見下方 generate_ai_questions / explain_answer）
"""

import os
import random
import tempfile
import streamlit as st
import gs_parser

st.set_page_config(page_title="❓ 常識選擇題生成器", page_icon="❓", layout="wide")

REPO = "chuckchanchi-cpu/gs-trainer"
BRANCH = "main"


# ================= 教材拉取 =================
@st.cache_data(ttl=600, show_spinner="🔄 從 GitHub 拉取最新教材…")
def fetch_materials_from_github():
    """從 GitHub repo 拉所有 .md 教材（排除 README）。失敗時回傳 None。"""
    try:
        import requests
        url = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
        r = requests.get(url, timeout=25)
        r.raise_for_status()
        tree = r.json().get("tree", [])
        md_paths = [
            t["path"] for t in tree
            if t.get("type") == "blob"
            and t["path"].endswith(".md")
            and not t["path"].startswith(".")
            and "README" not in t["path"]
        ]
        contents = {}
        for path in md_paths:
            raw = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{path}"
            rr = requests.get(raw, timeout=25)
            if rr.status_code == 200:
                contents[path] = rr.text
        return contents if contents else None
    except Exception:
        return None


def load_local_materials():
    """後備：讀取 app 同目錄下的 .md 檔案"""
    base = os.path.dirname(os.path.abspath(__file__))
    files = [f for f in os.listdir(base) if f.endswith(".md") and "README" not in f]
    return {f: open(os.path.join(base, f), encoding="utf-8").read() for f in files}


def parse_contents(contents):
    """把 dict{檔名: 內容} 寫到暫存目錄，交給 gs_parser 解析"""
    tmp = tempfile.mkdtemp(prefix="gs_materials_")
    for path, text in contents.items():
        fname = os.path.basename(path)
        with open(os.path.join(tmp, fname), "w", encoding="utf-8") as f:
            f.write(text)
    return gs_parser.load_all(tmp)


def build_topic_label(unit, topic):
    return f"Unit {unit}：{topic}" if unit else topic


# ================= 教材載入 =================
contents = fetch_materials_from_github() or load_local_materials()
data = parse_contents(contents)
topics = data["topics"]          # {topic: unit}
all_questions = data["questions"]
knowledge_blocks = data["knowledge"]

# 依 unit 排序主題
topic_items = sorted(topics.items(), key=lambda kv: int(kv[1]) if str(kv[1]).isdigit() else 99)


# ================= AI 掛鉤（由你在 Streamlit 接） =================
def generate_ai_questions(topic, count):
    """✨ AI 生成新題 —— 由你接 qwen3.8-flash 等模型。
    可參考 secrets：st.secrets["OPENAI_API_KEY"] / ["SILRA_API_URL"] / ["MODEL_NAME"]"""
    st.warning("AI 生成功能尚未接上，請在 Streamlit 端自行接入（secrets 已備）。")
    return []


def explain_answer(question):
    """💡 AI 解釋答案 —— 由你接。教材原題模式可用教材自帶的解釋。"""
    return question.get("explanation", "")


# ================= 頁面 =================
st.title("❓ 常識選擇題生成器")
st.caption("小六常識科 MCQ 訓練 — 揀主題 → 每輪出題 → 即場作答自動批改。教材每日由 GitHub 更新。")

if "gs_questions" not in st.session_state:
    st.session_state.gs_questions = []
if "gs_checked" not in st.session_state:
    st.session_state.gs_checked = False

with st.sidebar:
    st.header("⚙️ 設定")

    if all_questions:
        # 主題多選
        topic_labels = [build_topic_label(u, t) for t, u in topic_items]
        label_to_topic = {build_topic_label(u, t): t for t, u in topic_items}
        selected = st.multiselect("揀主題（可多選）", topic_labels, key="gs_topics")

        # 每輪題數
        max_count = max(1, min(len(all_questions), 20))
        count = st.slider("每輪題數", 5, max_count, min(10, max_count), key="gs_count")

        # 生成模式（AI 由你接）
        mode = st.radio("生成模式", ["📖 教材原題", "✨ AI 生成（待接）"], key="gs_mode")

        if st.button("🎲 生成題目", type="primary", use_container_width=True):
            if not selected:
                st.warning("⚠️ 請先揀至少一個主題")
            else:
                chosen_topics = [label_to_topic[x] for x in selected]
                if mode.startswith("✨"):
                    # AI 模式
                    pool = []
                    for t in chosen_topics:
                        pool += generate_ai_questions(t, count)
                    qs = pool[:count]
                else:
                    pool = [q for q in all_questions if q["topic"] in chosen_topics]
                    random.shuffle(pool)
                    qs = pool[:count]
                if qs:
                    st.session_state.gs_questions = qs
                    st.session_state.gs_checked = False
                    st.rerun()
                else:
                    st.error("❌ 揀選嘅主題冇題目！")

        # 題庫資訊
        with st.expander("📚 題庫資訊"):
            st.markdown(f"**總題目數：** {len(all_questions)}")
            for t, u in topic_items:
                c = sum(1 for q in all_questions if q["topic"] == t)
                st.markdown(f"- Unit {u}：{t}（{c} 題）")

        # 知識點溫習
        if knowledge_blocks:
            with st.expander("🧠 教材知識點溫習"):
                for kb in knowledge_blocks:
                    u = kb["unit"] or ""
                    label = f"Unit {u}：{kb['topic']}" if u else kb["topic"]
                    with st.expander(label):
                        st.markdown(kb["content"])
    else:
        st.warning("⚠️ 未找到任何題目！請檢查 repo 內是否有 .md 教材檔案。")

st.divider()

# ================= 出題 =================
if not st.session_state.gs_questions:
    st.info("👈 左邊 sidebar：揀主題（可多選）→ 㩒「🎲 生成題目」開始！")
    st.stop()

qs = st.session_state.gs_questions
st.subheader(f"📝 今輪 {len(qs)} 題")

# 顯示題目 + 選項
for i, q in enumerate(qs):
    opts = q["options"]
    st.radio(
        f"**{i + 1}.** {q['question']}",
        opts,
        key=f"gs_a{i}",
        index=None,
    )

c1, c2 = st.columns([1, 1])
if not st.session_state.gs_checked:
    if c1.button("✅ 檢查答案", type="primary"):
        st.session_state.gs_checked = True
        st.rerun()
else:
    results = []
    for i, q in enumerate(qs):
        user = st.session_state.get(f"gs_a{i}")
        results.append((i, user, user == q["answer"]))
    correct = sum(1 for _, _, ok in results if ok)
    st.metric("🏆 得分", f"{correct} / {len(qs)}")
    for i, user, ok in results:
        q = qs[i]
        if ok:
            st.success(f"**✅ 第 {i + 1} 題**（你揀咗「{user}」）")
        else:
            st.error(f"**❌ 第 {i + 1} 題**　你揀咗：「{user or '（未作答）'}」　正確答案：**{q['answer']}**")
        expl = explain_answer(q)
        if expl:
            st.caption("💡 " + expl)
    st.markdown("---")

if c2.button("🔄 再嚟一輪", use_container_width=True):
    # 用相同設定重新抽題
    if st.session_state.get("gs_topics"):
        from collections import OrderedDict
        label_to_topic = {build_topic_label(u, t): t for t, u in topic_items}
        chosen_topics = [label_to_topic[x] for x in st.session_state.gs_topics]
        count = st.session_state.gs_count
        pool = [q for q in all_questions if q["topic"] in chosen_topics]
        random.shuffle(pool)
        qs = pool[:count]
        if qs:
            st.session_state.gs_questions = qs
            st.session_state.gs_checked = False
            st.rerun()

