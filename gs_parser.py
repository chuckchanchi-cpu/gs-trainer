# -*- coding: utf-8 -*-
"""gs_parser.py — 常識教材解析器（最終版）
從 .md 教材提取：主題(unit/topic)、題目(mcq/fill_blank/true_false/short_answer)、
配對題(matching)、溫習知識點(knowledge)。
"""
import os, re, glob, random

CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12}
def cn_num(s):
    s = str(s).strip()
    if s in CN: return str(CN[s])
    if s.isdigit(): return str(int(s))
    return s

# 主題關鍵字 → (unit, topic 顯示名)
TOPIC_RULES = [
    (['生態平衡','相互關係','大自然的平衡','生態'], '4', '大自然的平衡'),
    (['植物'], '2', '植物與環境'),
    (['動物'], '3', '動物與環境'),
    (['生物的分類','生物分類','生物多樣性'], '1', '生物的分類'),
]

def detect_unit_topic(content, filename):
    """依 H1 標題 + 主題關鍵字，回傳 (unit, topic)。topic 為權威分組。"""
    title = ''
    for L in content.split('\n'):
        L = L.strip()
        if L.startswith('# '):
            title = L.lstrip('#').strip(); break
    RULES = [
        (['生態','平衡','相互關係'], '4', '大自然的平衡'),
        (['生物的分類','生物分類'], '1', '生物的分類'),
        (['植物'], '2', '植物與環境'),
        (['動物'], '3', '動物與環境'),
    ]
    unit = None; topic = ''
    for kws, u, t in RULES:
        if any(k in title for k in kws):
            topic = t; unit = u; break
    if not topic:
        for kws, u, t in RULES:
            if any(k in content for k in kws):
                topic = t; unit = u; break
    if not topic:
        m3 = re.search(r'(?:單元\s*[一二三四五六七八九十\d]+|Unit\s*[一二三四五六七八九十\d]+)\s*[：:《]?\s*([^\n《》]+)', content)
        if m3: topic = m3.group(1).strip().lstrip('：:').strip()
    if unit is None:
        m = re.search(r'(?:第\s*([一二三四五六七八九十\d]+)\s*單元|單元\s*([一二三四五六七八九十\d]+)|Unit\s*([一二三四五六七八九十\d]+))', content)
        if m:
            raw = next((g for g in m.groups() if g), None); unit = cn_num(raw)
        else:
            m2 = re.search(r'Unit[_\s]*([一二三四五六七八九十\d]+)', filename)
            if m2: unit = cn_num(m2.group(1))
    return unit, topic

def parse_answer_section(content):
    """{練習名: [答案...]}"""
    ans = {}
    m = re.search(r'##?\s*答案', content)
    if not m: return ans
    section = content[m.start():]
    for mm in re.finditer(r'\*\*(練習[一二三四五六七八九十\d]+)[：:]*\*\*\s*([^\n]+)', section):
        name = mm.group(1); line = mm.group(2).strip()
        answers = []
        for p in re.split(r'　+', line):
            pm = re.match(r'^(\d+)[.、]\s*(.+)$', p)
            if pm: answers.append(pm.group(2).strip())
        if answers: ans[name] = answers
    return ans

def _clean(s):
    return re.sub(r'[✅❌]\s*$','',s).strip().rstrip('*').strip()

def extract_mcq(content):
    """選擇題：### N. q + - A/B/C/D + ✅/❌ + 解釋"""
    qs = []
    lines = content.split('\n'); i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = re.match(r'^#{2,4}\s*(\d+)[.、]\s*(.+)$', s)
        if m:
            qtext = m.group(2).strip()
            j = i + 1; options = []; answer_text = None; explanation = ''
            while j < len(lines):
                os_ = lines[j].strip()
                if not os_: j += 1; continue
                om = re.match(r'^[-*•]\s*(.+)$', os_)
                if om:
                    opt = om.group(1)
                    lm = re.match(r'^(\*\*)?([A-Da-d])[.、)]\s*(.+)$', opt)
                    if lm:
                        txt = _clean(lm.group(3))
                        options.append(txt)
                        if '✅' in opt: answer_text = txt
                    j += 1; continue
                if '解釋' in os_:
                    em = re.match(r'^[*\s]*💡?\s*解釋[:：]\s*(.+)$', os_)
                    if em: explanation = em.group(1).strip().lstrip('*').strip()
                    j += 1; continue
                if re.match(r'^#{1,4}\s', os_): break
                j += 1
            if len(options) >= 2 and answer_text:
                qs.append({'type':'mcq','question':qtext,'options':options,'answer':answer_text,'explanation':explanation})
                i = j; continue
        i += 1
    return qs

def extract_numbered(content, answer_map):
    """N. 題目（填空/判斷/簡答）。答案優先取內聯「→ **答案** ✅」，其次答案段落。"""
    qs = []; lines = content.split('\n'); cur = None; i = 0
    while i < len(lines):
        s = lines[i].strip()
        hm = re.match(r'^#{2,4}\s*(練習[一二三四五六七八九十\d]+)[：:]?\s*(.+)', s)
        if hm: cur = hm.group(1); i += 1; continue
        if re.match(r'^#{1,4}\s*答案', s): break
        qm = re.match(r'^(\d+)[.、]\s*(.+)$', s)
        if qm:
            num = qm.group(1); qtext = qm.group(2).strip()
            if re.match(r'^[A-Fa-f][.、)]\s', s): i += 1; continue
            qtype = 'short_answer'
            if '＿＿' in qtext or '____' in qtext: qtype = 'fill_blank'
            elif re.search(r'（\s*）', qtext) or re.search(r'\(\s*\)', qtext): qtype = 'true_false'
            elif '？' in qtext or '?' in qtext: qtype = 'short_answer'
            answer = None
            # 內聯答案：緊接的下一行「→ **答案** ✅」
            j = i + 1
            while j < len(lines):
                ns = lines[j].strip()
                if not ns: j += 1; continue
                am = re.match(r'^[→➜]\s*(.+)$', ns)
                if am and ('**' in ns or '✅' in ns):
                    answer = re.sub(r'[✅❌]\s*$','',am.group(1)).strip().rstrip('*').lstrip('*').strip()
                    if len(answer) > 40: answer = None
                    break
                break
            if answer is None and cur and cur in answer_map:
                idx = int(num) - 1
                if 0 <= idx < len(answer_map[cur]): answer = answer_map[cur][idx]
            qs.append({'type':qtype,'question':qtext,'answer':answer,'number':int(num),'exercise':cur})
            i += 1; continue
        i += 1
    return qs

def extract_matching(content):
    """配對題：選項表(字母→類別) + 答案表(動物→字母/類別)"""
    qs = []
    # 找選項表：| A | 類別 |
    options = {}
    for m in re.finditer(r'\|\s*([A-Fa-f])\s*\|\s*([^|\n]+)\s*\|', content):
        letter = m.group(1).upper(); cat = m.group(2).strip()
        if cat and not re.match(r'^[-:\s]+$', cat):
            options[letter] = cat
    if not options: return qs
    # 找答案表：| 動物 | ... | **A** | 類別 | 或 | 動物 | 答案 | 類別 |
    for line in content.split('\n'):
        cells = [c.strip() for c in line.split('|') if c.strip()]
        if len(cells) >= 3:
            animal = cells[0]
            if re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩\d]+$', animal) or animal in ('圖號','圖片編號','動物'): continue
            letter = None; cat = None
            for c in cells[1:]:
                lm = re.match(r'^(\*\*)?([A-Fa-f])([.、)]|\*\*)?$', c)
                if lm: letter = lm.group(2).upper()
            # 答案類別 = options[letter] 或 cells 最後一欄
            if letter and letter in options: cat = options[letter]
            else:
                for c in cells[1:]:
                    if c in options.values(): cat = c
            if animal and (cat or letter):
                qs.append({'type':'matching','question':f'{animal} 屬於哪一類？','answer':cat or letter,
                           'animal':animal,'letter':letter,'category':cat})
    return qs

def extract_knowledge(content, filename):
    """提取溫習/筆記部分（訓練/練習/答案之前的內容）作為知識點"""
    lines = content.split('\n')
    # 找到第一個「訓練/練習/作業/答案」標題的位置
    cut = len(lines)
    for i, L in enumerate(lines):
        if re.match(r'^#{1,4}\s*(第一部分|第二部分|訓練|練習|作業|答案)', L.strip()):
            cut = i; break
    head = '\n'.join(lines[:cut]).strip()
    # 去掉檔案標題行（# 開頭的第一行 + 日期/姓名）
    hlines = head.split('\n')
    if hlines and hlines[0].startswith('#'): hlines = hlines[1:]
    body = '\n'.join(hlines).strip()
    # 只保留有實質內容的（表格/列表/段落）
    if len(body) > 60 and ('|' in body or '**' in body or '：' in body):
        return body
    return ''

def normalize(qs, unit, topic, filename):
    """把題目正規化成 MCQ 形式（question + options + answer_index + explanation）"""
    out = []
    # 先收集各 exercise 的答案池（作 distractor 用）
    pool_by_ex = {}
    for q in qs:
        if q['type'] in ('fill_blank',) and q.get('answer'):
            pool_by_ex.setdefault(q.get('exercise'), set()).add(q['answer'])
    for q in qs:
        t = q['type']
        if t == 'mcq':
            opts = q['options']; ans = q['answer']
        elif t == 'true_false':
            opts = ['正確（✓）','錯誤（✗）']
            a = (q['answer'] or '').strip()
            ans = '正確（✓）' if a.startswith('✓') else ('錯誤（✗）' if a.startswith('✗') else None)
        elif t == 'fill_blank':
            ans = q['answer']
            if not ans: continue
            pool = pool_by_ex.get(q.get('exercise'), set())
            distractors = [x for x in pool if x != ans]
            if len(distractors) >= 3:
                opts = [ans] + random.sample(distractors, 3)
            else:
                opts = [ans] + distractors
            random.shuffle(opts)
        elif t == 'matching':
            ans = q.get('category') or q.get('answer')
            if not ans: continue
            # 選項 = 所有類別
            all_cats = q.get('_all_categories') or []
            if not all_cats: continue
            opts = [ans] + [c for c in all_cats if c != ans][:3]
        else:
            continue  # short_answer 不進 MCQ 題庫
        if ans not in opts:
            opts = [ans] + opts[:3]
        out.append({
            'unit': unit, 'topic': topic, 'file': filename,
            'type': t, 'question': q['question'],
            'options': opts, 'answer': ans,
            'answer_index': opts.index(ans) if ans in opts else 0,
            'explanation': q.get('explanation',''),
        })
    return out

def parse_file(filepath):
    content = open(filepath, encoding='utf-8').read()
    filename = os.path.basename(filepath)
    unit, topic = detect_unit_topic(content, filename)
    answer_map = parse_answer_section(content)
    raw = extract_mcq(content) + extract_numbered(content, answer_map) + extract_matching(content)
    # 給 matching 附上全部類別選項
    all_cats = sorted(set(q.get('category') for q in raw if q['type']=='matching' and q.get('category')))
    for q in raw:
        if q['type']=='matching': q['_all_categories'] = all_cats
    questions = normalize(raw, unit, topic, filename)
    knowledge = extract_knowledge(content, filename)
    return {'unit':unit,'topic':topic,'questions':questions,'knowledge':knowledge}

def load_all(base_dir):
    """載入所有 .md，回傳 {topics:[], questions:[], knowledge:[]}"""
    files = [f for f in glob.glob(os.path.join(base_dir,'*.md')) if 'README' not in os.path.basename(f)]
    topics = {}; questions = []; knowledge = []
    for f in sorted(files):
        r = parse_file(f)
        if r['topic']:
            topics.setdefault(r['topic'], r['unit'])
        questions += r['questions']
        if r['knowledge']:
            knowledge.append({'unit':r['unit'],'topic':r['topic'],'content':r['knowledge'],'file':os.path.basename(f)})
    return {'topics':topics,'questions':questions,'knowledge':knowledge}

