#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
❓ 常識選擇題生成器 — 小六常識科 MCQ 訓練
流程：讀 repo 內最新教材(.md) → 解析主題/題目 → 揀主題出題 → 批改（教材原題）／AI 生成新題
AI（qwen3.8-flash）設定來自 Streamlit Secrets：OPENAI_API_KEY / SILRA_API_URL / MODEL_NAME
"""
import os, json, random, re, unicodedata
import streamlit as st
import gs_parser

st.set_page_config(page_title="❓ 常識選擇題生成器", page_icon="❓", layout="wide")

REPO = "chuckchanchi-cpu/gs-trainer"
BRANCH = "main"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_local_materials():
    files = [f for f in os.listdir(BASE_DIR) if f.endswith(".md") and "README" not in f]
    return {f: open(os.path.join(BASE_DIR, f), encoding="utf-8").read() for f in files}

def fetch_materials_from_github():
    try:
        import requests
        url = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
        r = requests.get(url, timeout=15); r.raise_for_status()
        tree = r.json().get("tree", [])
        md_paths = [t["path"] for t in tree if t.get("type") == "blob"
                    and t["path"].endswith(".md") and not t["path"].startswith(".")
                    and "README" not in t["path"]]
        contents = {}
        for path in md_paths:
            raw = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{path}"
            rr = requests.get(raw, timeout=15)
            if rr.status_code == 200: contents[path] = rr.text
        return contents or None
    except Exception as e:
        st.error(f"⚠️ 從 GitHub 更新失敗：{e}")
        return None

@st.cache_data(show_spinner=False)
def parse_all(contents_dict):
    import tempfile
    tmp = tempfile.mkdtemp(prefix="gs_")
    for path, text in contents_dict.items():
        with open(os.path.join(tmp, os.path.basename(path)), "w", encoding="utf-8") as f:
            f.write(text)
    return gs_parser.load_all(tmp)

def build_topic_label(unit, topic):
    return f"Unit {unit}：{topic}" if unit else topic

# ================= AI（SILRA / qwen3.8-flash） =================
def _silra_chat(messages, max_tokens=2048):
    import requests
    url = st.secrets.get("SILRA_API_URL", "https://api.silra.cn/v1/chat/completions")
    key = st.secrets.get("OPENAI_API_KEY", "")
    model = st.secrets.get("MODEL_NAME", "qwen3.8-flash")
    if not key:
        st.error("🔑 未設定 OPENAI_API_KEY。請在 Streamlit Settings → Secrets 加入。")
        return None
    try:
        r = requests.post(url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens,
                  "enable_thinking": False}, timeout=90)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        st.error(f"⚠️ AI 呼叫失敗：{e}")
        return None

def _topic_material(topic):
    parts = [kb["content"] for kb in knowledge_blocks if kb["topic"] == topic]
    parts += [q["question"] + " → " + q["answer"] for q in all_questions if q["topic"] == topic]
    return "\n\n".join(parts)

def _norm(s):
    """正規化文字：全形→半形、刪空白同括號引號，用嚟做寬鬆比對"""
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s「」『』\"'“”’（）()]+", "", s)


def _match_answer(ans, opts):
    """AI 嘅 answer 可能加咗 A/B/C/D 前綴、寫多咗字 — 嚴格地解析返去原選項字面。
    解析唔到就回傳 None（題目作廢），絕不亂配，避免批改錯判。"""
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
    # 唯一包含匹配（qwen 成日寫多字）；多過一個選項命中 → 視為模糊，作廢
    hits = [o for o in opts if _norm(o) and _norm(o) in na]
    if len(hits) == 1:
        return hits[0]
    return None


def _extract_json_array(text):
    """穩陣抽取 JSON 陣列：去 code fence → raw_decode → 修復 trailing comma／全形逗號再試"""
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


def generate_ai_questions(topic, count):
    mat = _topic_material(topic)
    prompt = (
        f"你是小六常識科出題老師。根據以下教材知識點，生成 {count} 條選擇題。"
        f"每題必須：4 個選項、1 個正確答案、1 句書面語解釋。只准用教材知識點，唔可以作新事實。"
        f"\n\n鐵律：\n"
        f"1.「answer」必須同其中一個「options」字面完全一樣（原字照抄），唔准加 A/B/C/D 前綴、唔准加括號或多餘字。\n"
        f"2. 嚴格只輸出 JSON 陣列：唔好加 markdown、註解、尾隨逗號；每一行都要係合法 JSON。\n"
        f"3. 每個字都要喺 JSON 字串入面，唔好中途斷行破壞結構。\n\n"
        f"格式：[{{\"question\":\"...\",\"options\":[\"...\",\"...\",\"...\",\"...\"],\"answer\":\"正確選項原字\",\"explanation\":\"...\"}}]\n\n教材：\n{mat[:4000]}"
    )
    out = _silra_chat([{"role": "user", "content": prompt}], max_tokens=8000)
    if not out:
        return []
    arr = _extract_json_array(out)
    if not isinstance(arr, list):
        st.error("⚠️ AI 回傳格式無法解析 — 試多一次？（如果經常出現，可減少每輪題數）")
        st.code(out[:3000])
        return []
    qs = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        qtext = (item.get("question") or "").strip()
        opts = [str(o).strip() for o in (item.get("options") or []) if str(o).strip()]
        if not qtext or len(opts) < 2:
            continue
        matched = _match_answer(item.get("answer", ""), opts)
        if matched is None:
            continue  # 答案對唔返選項 → 題目作廢（嚴格，避免批改錯判）
        qs.append({"unit": None, "topic": topic, "file": "AI", "type": "ai",
                   "question": qtext, "options": opts, "answer": matched,
                   "answer_index": opts.index(matched),
                   "explanation": (item.get("explanation") or "").strip()})
    return qs[:count]

def explain_answer(q, user_answer):
    if q.get("explanation"): return q["explanation"]
    if not st.secrets.get("OPENAI_API_KEY", ""): return ""
    prompt = (f"題目：{q['question']}\n選項：{'、'.join(q['options'])}\n正確答案：{q['answer']}\n"
              f"請用書面語、簡短（2-3 句）解釋為何正確答案係「{q['answer']}」。")
    out = _silra_chat([{"role": "user", "content": prompt}], max_tokens=400)
    return out or ""

# ================= 載入 =================
contents = load_local_materials()
data = parse_all(contents)
topics = data["topics"]
all_questions = data["questions"]
knowledge_blocks = data["knowledge"]
topic_items = sorted(topics.items(), key=lambda kv: int(kv[1]) if str(kv[1]).isdigit() else 99)

st.title("❓ 常識選擇題生成器")
st.caption("小六常識科 MCQ 訓練 — 揀主題 → 每輪出題 → 即場作答批改。教材隨 repo 每日更新。")

if "gs_questions" not in st.session_state: st.session_state.gs_questions = []
if "gs_checked" not in st.session_state: st.session_state.gs_checked = False

def set_round(qs):
    """換新一輪題目：清走上一輪嘅作答狀態（gs_a0/gs_a1/...），避免殘留答案影響批改"""
    for k in list(st.session_state.keys()):
        if re.fullmatch(r"gs_a\d+", str(k)):
            del st.session_state[k]
    st.session_state.gs_questions = qs
    st.session_state.gs_checked = False

with st.sidebar:
    st.header("⚙️ 設定")
    if st.button("🔄 從 GitHub 更新教材", use_container_width=True):
        fresh = fetch_materials_from_github()
        if fresh:
            parse_all.clear()
            data = parse_all(fresh)
            set_round([])
            st.rerun()
    if all_questions:
        topic_labels = [build_topic_label(u, t) for t, u in topic_items]
        label_to_topic = {build_topic_label(u, t): t for t, u in topic_items}
        selected = st.multiselect("揀主題（可多選）", topic_labels, key="gs_topics")
        max_count = max(1, min(len(all_questions), 20))
        count = st.slider("每輪題數", 5, max_count, min(10, max_count), key="gs_count")
        mode = st.radio("生成模式", ["📖 教材原題", "✨ AI 生成新題"], key="gs_mode")
        if st.button("🎲 生成題目", type="primary", use_container_width=True):
            if not selected:
                st.warning("⚠️ 請先揀至少一個主題")
            else:
                chosen_topics = [label_to_topic[x] for x in selected]
                if mode.startswith("✨"):
                    with st.spinner("✨ AI 生成緊題目，請稍候…"):
                        pool = []
                        for t in chosen_topics: pool += generate_ai_questions(t, count)
                    qs = pool[:count]
                else:
                    pool = [q for q in all_questions if q["topic"] in chosen_topics]
                    random.shuffle(pool); qs = pool[:count]
                if qs:
                    set_round(qs)
                    st.rerun()
                else:
                    st.error("❌ 冇題目！請檢查 AI 設定或所選主題。")
        with st.expander("📚 題庫資訊"):
            st.markdown(f"**總題目數：** {len(all_questions)}")
            for t, u in topic_items:
                c = sum(1 for q in all_questions if q["topic"] == t)
                st.markdown(f"- Unit {u}：{t}（{c} 題）")
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

if not st.session_state.gs_questions:
    st.info("👈 左邊 sidebar：揀主題（可多選）→ 㩒「🎲 生成題目」開始！")
    st.stop()

qs = st.session_state.gs_questions
st.subheader(f"📝 今輪 {len(qs)} 題")
for i, q in enumerate(qs):
    st.radio(f"**{i + 1}.** {q['question']}", q["options"], key=f"gs_a{i}", index=None)

c1, c2 = st.columns([1, 1])
if not st.session_state.gs_checked:
    if c1.button("✅ 檢查答案", type="primary"):
        st.session_state.gs_checked = True
        st.rerun()
else:
    results = []
    for i, q in enumerate(qs):
        user = st.session_state.get(f"gs_a{i}")
        ok = user is not None and _norm(user) == _norm(q["answer"])
        results.append((i, user, ok))
    correct = sum(1 for _, _, ok in results if ok)
    st.metric("🏆 得分", f"{correct} / {len(qs)}")
    for i, user, ok in results:
        q = qs[i]
        if ok:
            st.success(f"**✅ 第 {i + 1} 題**（你揀咗「{user}」）")
        else:
            st.error(f"**❌ 第 {i + 1} 題**　你揀咗：「{user or '（未作答）'}」　正確答案：**{q['answer']}**")
        expl = explain_answer(q, user)
        if expl: st.caption("💡 " + expl)
    st.markdown("---")

if c2.button("🔄 再嚟一輪", use_container_width=True):
    if st.session_state.get("gs_topics"):
        label_to_topic = {build_topic_label(u, t): t for t, u in topic_items}
        chosen_topics = [label_to_topic[x] for x in st.session_state.gs_topics]
        cnt = st.session_state.gs_count
        if st.session_state.get("gs_mode", "").startswith("✨"):
            with st.spinner("✨ AI 生成緊題目，請稍候…"):
                pool = []
                for t in chosen_topics: pool += generate_ai_questions(t, cnt)
            qs2 = pool[:cnt]
        else:
            pool = [q for q in all_questions if q["topic"] in chosen_topics]
            random.shuffle(pool)
            qs2 = pool[:cnt]
        if qs2:
            set_round(qs2)
            st.rerun()
        else:
            st.error("❌ 冇題目！請檢查 AI 設定或所選主題。")

