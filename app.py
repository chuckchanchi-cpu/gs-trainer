#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
❓ 常識選擇題生成器 — 小六常識科 MCQ 訓練（獨立 app）

Chuck 要求（2026-09-29）：
  - 中文填充訓練做得好 → 常識科照同一模式做獨立選擇題 app
  - 揀主題（可多選）→ 每輪 10 題 → 自動批改 + 解釋

兩種模式：
  📖 教材原題 — 直接由教材題庫抽題（100% 教材、即時、唔使 API）
  ✨ AI 生成新題 — qwen3.8-flash 根據教材知識點生成全新選擇題（每輪新鮮）

題庫來源（2026-09-07 ~ 09-26 常識教材）：
  Unit 1 生物的分類（動物分類・特殊案例・植物分類・繁殖方式）
  Unit 2 植物與環境（根莖葉適應・植物自我保護）
  Unit 3 動物與環境（環境適應・保護色/偽裝/警戒/羣居・覓食）

部署：
  GitHub repo → Streamlit Cloud；Secrets 設定：
  OPENAI_API_KEY / SILRA_API_URL / MODEL_NAME
"""

import os
import json
import re
import random
import unicodedata
import requests
import streamlit as st

st.set_page_config(page_title="❓ 常識選擇題生成器", page_icon="❓", layout="wide")

# 將 Streamlit Secrets 注入環境變數（每個 page 獨立執行，要自己注入！）
if hasattr(st, "secrets") and len(st.secrets) > 0:
    for k, v in st.secrets.items():
        os.environ[k] = str(v)

# ===== API 配置（env-first，兼容 OPENAI_* / SILRA_* 舊設定名）=====
def get_api_config():
    base = os.environ.get("OPENAI_API_BASE", "").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("SILRA_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL_NAME", "") or os.environ.get("MODEL_NAME", "deepseek-chat")
    if not base:
        silra_url = os.environ.get("SILRA_API_URL", "")
        if silra_url:
            base = silra_url.replace("/chat/completions", "").rstrip("/")
    if not base:
        base = "https://api.deepseek.com"
    return base, key, model

# ===== AI JSON 解析（fence 清理 + LaTeX 符號轉換 + 雜質文字抽取）=====
def parse_ai_json(content):
    """將 AI 回覆轉成 Python object；失敗回傳 None"""
    if not content:
        return None
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    content = content.replace("\\\\", "\\")
    content = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1)/(\2)", content)
    for tok, rep in [("\\div", "÷"), ("\\times", "×"), ("\\cdot", "·"), ("\\pm", "±"),
                     ("\\le", "≤"), ("\\ge", "≥"), ("\
eq", "≠"), ("\\%", "%")]:
        content = content.replace(tok, rep)
    content = re.sub(r"\\(?!n|t|r|f|b|u[0-9a-fA-F]{4}|/|\"|\\\\|')[a-zA-Z]+", "", content)
    content = re.sub(r"\\([^nrtbfu/\"\\0-9])", r"\1", content)
    content = content.replace("\\ ", " ").replace("\\{", "{").replace("\\}", "}")
    content = content.replace("$", "")
    def _unwrap(obj):
        if isinstance(obj, dict):
            for k in ("questions", "question", "題目", "data", "quiz", "items", "results", "exercises"):
                v = obj.get(k)
                if isinstance(v, list):
                    return v
        return obj
    try:
        return _unwrap(json.loads(content))
    except json.JSONDecodeError:
        m = re.search(r'[\[{].*[\]}]', content, re.S)
        if not m:
            return None
        try:
            return _unwrap(json.loads(m.group(0)))
        except json.JSONDecodeError:
            return None

def _norm(s):
    """正規化文字：全形→半形、刪走空白同引號，用嚟做寬鬆比對"""
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s「」『』\"'“”’（）()]+", "", s)

def _match_answer(ans, opts):
    """AI 嘅 answer 可能加咗 A/B/C/D 前綴、淨係寫字母，或者寫多咗字 — 寬鬆比對返正確選項"""
    if not ans:
        return None
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
    m = re.match(r"^[a-dA-D][.、)）:：]\s*(.+)$", ans.strip())
    if m:
        cand = m.group(1).strip()
        for o in opts:
            if _norm(cand) == _norm(o):
                return o
        if cand in opts:
            return cand
    parts = [p.strip() for p in re.split(r"[和及或、，]", ans) if p.strip()]
    if len(parts) >= 2:
        nopts = {_norm(o): o for o in opts}
        if all(_norm(p) in nopts for p in parts):
            return None  # 一題多答案 → 唔合格
    return None

QUESTION_BANK = {
    'bio': {
        'name': '生物的分類（動物分類・特殊案例・植物分類）',
        'date': '2026-09-13',
        "questions": [
            ('青蛙的皮膚特徵是什麼？', ['濕潤無鱗', '乾燥有鱗片', '長有羽毛', '長有毛髮'], '濕潤無鱗', '兩棲類皮膚濕潤、無鱗片，用肺＋皮膚呼吸'),
            ('蛇的皮膚特徵是什麼？', ['乾燥有鱗片', '濕潤無鱗', '長有羽毛', '有毛髮'], '乾燥有鱗片', '爬行類皮膚乾燥、有鱗片，只用肺呼吸'),
            ('下列哪種動物屬於兩棲類？', ['青蛙', '蛇', '麻雀', '大猩猩'], '青蛙', '青蛙、蠑螈係兩棲類；蛇、烏龜係爬行類'),
            ('下列哪種動物屬於爬行類？', ['烏龜', '青蛙', '金魚', '麻雀'], '烏龜', '烏龜、蛇係爬行類；青蛙係兩棲類'),
            ('兩棲類和爬行類都用什麼器官呼吸？', ['肺', '鰓', '氣管', '皮膚'], '肺', '兩者都用肺呼吸；兩棲類仲用皮膚輔助'),
            ('下列哪種動物是脊椎動物？', ['麻雀', '螞蟻', '蝴蝶', '蚯蚓'], '麻雀', '脊椎動物有脊柱，包括魚類、兩棲類、爬行類、鳥類、哺乳類'),
            ('下列哪種動物是無脊椎動物？', ['螞蟻', '金魚', '青蛙', '蛇'], '螞蟻', '無脊椎動物冇脊柱，如昆蟲類（螞蟻、蝴蝶）'),
            ('脊椎動物共有幾個類別？', ['5個', '4個', '6個', '3個'], '5個', '魚類、兩棲類、爬行類、鳥類、哺乳類 = 5 個類別'),
            ('昆蟲類屬於哪種動物？', ['無脊椎動物', '脊椎動物', '兩棲類', '爬行類'], '無脊椎動物', '昆蟲類冇脊柱，屬於無脊椎動物'),
            ('百合屬於哪種植物？', ['有花植物', '無花植物', '水生植物', '苔蘚'], '有花植物', '有花植物會開花結果、以種子繁殖，如百合、水仙'),
            ('松樹屬於哪種植物？', ['無花植物', '有花植物', '水生植物', '苔蘚'], '無花植物', '無花植物唔會開花，如松樹、蕨類、苔蘚'),
            ('松樹以什麼方式繁殖？', ['以種子繁殖', '以孢子繁殖', '以根繁殖', '以莖繁殖'], '以種子繁殖', '松樹係裸子植物，以種子繁殖（唔係孢子）'),
            ('蕨類以什麼方式繁殖？', ['以孢子繁殖', '以種子繁殖', '以根繁殖', '以葉繁殖'], '以孢子繁殖', '蕨類、苔蘚都以孢子繁殖'),
            ('下列哪種植物是水生植物？', ['睡蓮', '鳳凰木', '百合', '松樹'], '睡蓮', '水生植物生長喺水中，如睡蓮、水葫蘆'),
            ('下列哪種植物是陸生植物？', ['鳳凰木', '睡蓮', '水葫蘆', '浮萍'], '鳳凰木', '陸生植物生長喺陸地，如鳳凰木、樹木'),
            ('企鵝雖然不會飛，但它屬於哪種類別？', ['鳥類', '哺乳類', '兩棲類', '爬行類'], '鳥類', '有羽毛＋卵生＝鳥類（即使唔識飛）'),
            ('鯨魚生活在海中，但它屬於哪種類別？', ['哺乳類', '魚類', '兩棲類', '爬行類'], '哺乳類', '胎生＋用肺呼吸＝哺乳類（唔係魚類）'),
            ('下列哪組全部是脊椎動物？', ['麻雀、金魚、青蛙', '螞蟻、蝴蝶、蚯蚓', '松樹、蕨類、百合', '睡蓮、鳳凰木、水葫蘆'], '麻雀、金魚、青蛙', '脊椎動物包括：魚類、兩棲類、爬行類、鳥類、哺乳類'),
            ('下列哪組全部是無脊椎動物？', ['螞蟻、蝴蝶、蚯蚓', '麻雀、蛇、青蛙', '金魚、烏龜、大猩猩', '百合、水仙、松樹'], '螞蟻、蝴蝶、蚯蚓', '無脊椎動物：昆蟲類、蠕蟲類等冇脊柱動物'),
            ('有花植物和無花植物的主要分別是什麼？', ['是否開花結果', '生長環境', '是否有葉子', '繁殖速度'], '是否開花結果', '核心分別：有花植物會開花結果；無花植物永不開花'),
            ('蝙蝠會飛，但牠屬於哪一類？', ['哺乳類', '鳥類', '昆蟲類', '爬行類'], '哺乳類', '蝙蝠有毛髮＋用母乳餵養幼兒＝哺乳類'),
            ('海豚住在海裏用鰭游動，但牠屬於哪一類？', ['哺乳類', '魚類', '兩棲類', '爬行類'], '哺乳類', '海豚用母乳餵養幼兒＋用肺呼吸＝哺乳類'),
            ('海龜住在海裏，但牠屬於哪一類？', ['爬行類', '魚類', '兩棲類', '哺乳類'], '爬行類', '海龜有殼＋皮膚乾燥有鱗片＋用肺呼吸＝爬行類'),
            ('判斷動物屬於邊一類，最有效先睇邊兩樣特徵？', ['皮膚同呼吸方式', '體形同顏色', '居住環境同食物', '腳嘅數量同尾巴'], '皮膚同呼吸方式', '記憶口訣：先睇「皮膚」同「呼吸方式」，再睇「繁殖同餵養」'),
            ('海豚被歸為哺乳類而非魚類的主要原因係？', ['用母乳餵養幼兒＋用肺呼吸', '住喺海裏', '用鰭游動', '身體有鱗片'], '用母乳餵養幼兒＋用肺呼吸', '哺乳類關鍵特徵：用母乳餵養幼兒＋用肺呼吸'),
        ],
    },
    'plant': {
        'name': '植物與環境（根莖葉適應・植物自我保護）',
        'date': '2026-09-17',
        "questions": [
            ('影響植物生長嘅兩個主要因素係？', ['氣溫同雨量', '土壤同風', '陽光同動物', '海拔同緯度'], '氣溫同雨量', '不同地方嘅氣溫同雨量不同，會影響植物生長'),
            ('沙漠植物嘅根深入泥土中，作用係？', ['吸收地下深處嘅水分', '散熱', '抓緊地面', '吸收陽光'], '吸收地下深處嘅水分', '沙漠乾旱缺水，根要長得深先吸到地下水'),
            ('紅樹林嘅根點解要伸出泥土？', ['泥土含氧量低，要喺空氣中吸取氧氣', '吸收更多陽光', '防止被潮水沖走', '炫耀特別外形'], '泥土含氧量低，要喺空氣中吸取氧氣', '濕地泥土缺氧，根要伸出地面呼吸'),
            ('板狀根（如熱帶雨林大樹）嘅作用係？', ['支持樹木長高，增加接觸陽光機會', '儲存水分', '減少水分流失', '吸取空氣中嘅氧氣'], '支持樹木長高，增加接觸陽光機會', '熱帶雨林樹木密集，板狀根支持樹木長高爭取陽光'),
            ('仙人掌嘅莖十分肥厚，作用係？', ['儲存水分，適應乾旱', '幫助呼吸', '支持樹木長高', '吸引昆蟲'], '儲存水分，適應乾旱', '沙漠乾旱，肥厚嘅莖儲存水分'),
            ('藤本植物點解要攀附大樹向上生長？', ['爭取接觸更多陽光', '避開動物', '吸收更多水分', '方便散熱'], '爭取接觸更多陽光', '熱帶雨林地面陽光不足，攀附大樹向上爭取陽光'),
            ('蓮藕（蓮嘅莖）長滿洞孔，作用係？', ['喺缺乏氧氣嘅泥土中吸取氧氣', '儲存水分', '增加重量', '方便排水'], '喺缺乏氧氣嘅泥土中吸取氧氣', '濕地泥土缺氧，洞孔有助吸取較多氧氣'),
            ('仙人掌嘅葉變成刺狀，作用係？', ['減少水分流失', '防止被動物食', '儲存水分', '吸收陽光'], '減少水分流失', '沙漠雨量極少，刺狀葉減少水分流失'),
            ('紅樹植物葉片表面有厚蠟質，作用係？', ['減少水分流失', '反射陽光', '防止水浸', '吸引昆蟲'], '減少水分流失', '濕地泥土含鹽量較高，厚蠟質減少水分流失'),
            ('熱帶雨林植物葉片闊大，作用係？', ['增加接觸陽光機會', '減少水分流失', '方便排水', '防止被食'], '增加接觸陽光機會', '雨林內部陰暗，闊大葉片幫助接觸更多陽光'),
            ('夾竹桃點樣保護自己？', ['整株有毒', '外形似石頭', '葉柄長滿刺', '葉片會合埋'], '整株有毒', '夾竹桃整株有毒，動物食咗會中毒'),
            ('生石花點樣保護自己？', ['外形似石頭，不易被動物發現', '整株有毒', '葉柄長滿刺', '散發臭味'], '外形似石頭，不易被動物發現', '生石花外形似石頭，係擬態保護'),
            ('含羞草點樣保護自己？', ['葉片被觸碰時會閉合', '整株有毒', '葉柄長滿刺', '散發特別氣味'], '葉片被觸碰時會閉合', '含羞草葉片受觸碰即閉合，嚇走／阻擋動物'),
            ('蠍子草點樣保護自己？', ['葉柄長滿刺', '整株有毒', '外形似石頭', '開花散發氣味'], '葉柄長滿刺', '蠍子草葉柄有刺，會刺傷進食嘅動物'),
            ('樟樹點樣保護自己？', ['開花時散發特別氣味', '葉柄長滿刺', '整株有毒', '葉片會合埋'], '開花時散發特別氣味', '樟樹開花散發特別氣味，驅趕動物'),
            ('沙漠嘅氣候特點係？', ['乾旱、晝夜溫差大、雨量少', '炎熱多雨', '長年冰雪覆蓋', '有乾濕季之分'], '乾旱、晝夜溫差大、雨量少', '沙漠晝夜溫差大、雨量少，植物稀少'),
            ('濕地（紅樹林）嘅泥土有咩特點？', ['含氧量低', '含氧量高', '又乾又鬆', '冇鹽分'], '含氧量低', '濕地泥土含氧量低，所以植物根要伸出泥土呼吸'),
            ('沙漠植物根部「淺而廣」嘅作用係？', ['迅速吸收較大範圍嘅水分', '散熱', '支持樹木長高', '吸取空氣中氧氣'], '迅速吸收較大範圍嘅水分', '淺而廣嘅根可喺落雨時快速吸收大範圍水分'),
        ],
    },
    'animal': {
        'name': '動物與環境（環境適應・保護・覓食）',
        'date': '2026-09-24',
        "questions": [
            ('北極熊點解唔怕凍？', ['有厚脂肪＋濃密毛＋細小耳朵', '因為佢大隻', '因為佢白色', '因為佢跑得快'], '有厚脂肪＋濃密毛＋細小耳朵', '厚脂肪儲存能量兼保溫，濃密毛減少熱量散失，細耳減少散熱'),
            ('駱駝嘅駝峰儲咩？', ['脂肪', '水', '食物', '空氣'], '脂肪', '駝峰儲脂肪（唔係儲水），令駱駝耐食耐渴'),
            ('竹節蟲用咩方法保護自己？', ['偽裝（形態似樹枝）', '保護色', '警戒色', '羣居'], '偽裝（形態似樹枝）', '偽裝＝形態似環境物體；竹節蟲似樹枝'),
            ('箭毒蛙鮮艷嘅顏色係咩？', ['警戒色', '保護色', '偽裝', '羣居訊號'], '警戒色', '警戒色用鮮艷顏色警告敵人「我有毒，唔好食我」'),
            ('以下邊種動物唔會冬眠？', ['金魚', '蛇', '松鼠', '青蛙'], '金魚', '金魚係水產，唔冬眠；蛇、松鼠、青蛙會冬眠'),
            ('「保護色」係指？', ['身體顏色與環境相似', '身體形態似環境物體', '鮮艷顏色警告敵人', '成群結隊活動'], '身體顏色與環境相似', '保護色＝顏色似環境，把自己隱藏'),
            ('「偽裝」係指？', ['身體形態似環境中嘅物體', '身體顏色與環境相似', '鮮艷顏色警告敵人', '成群結隊活動'], '身體形態似環境中嘅物體', '偽裝＝形態似物體（如枯葉蝶似枯葉）'),
            ('年幼海豹身體白色，屬於邊種保護方法？', ['保護色', '偽裝', '警戒色', '羣居'], '保護色', '白色海豹似雪地，係保護色'),
            ('枯葉蝶靜止時似一塊枯葉，屬於邊種保護方法？', ['偽裝', '保護色', '警戒色', '羣居'], '偽裝', '形態似枯葉，係偽裝（唔係顏色相似咁簡單）'),
            ('沙丁魚成群游動，屬於邊種保護方法？', ['羣居', '保護色', '偽裝', '警戒色'], '羣居', '羣居＝成群結隊活動，合力嚇走捕食者'),
            ('蜂鳥嘅喙尖而細長，方便佢？', ['吸取花朵深處嘅花蜜', '撕裂肉類', '捉魚', '啄木'], '吸取花朵深處嘅花蜜', '身體特徵配合覓食方式：尖長喙吸花蜜'),
            ('獅子鋒利嘅犬牙適合？', ['撕裂肉類', '磨碎植物', '吸取花蜜', '挖掘泥土'], '撕裂肉類', '食肉動物有鋒利犬牙，適合撕裂肉類'),
            ('食草動物嘅臼齒特徵係？', ['扁平，適合磨碎植物', '鋒利，適合撕裂肉類', '尖長，適合吸蜜', '冇牙齒'], '扁平，適合磨碎植物', '食草動物用扁平臼齒磨碎植物'),
            ('蝸牛喺乾燥天氣嘅對策係？', ['夏眠，用黏液封住殼口', '冬眠', '遷徙', '脫殼'], '夏眠，用黏液封住殼口', '乾旱時蝸牛夏眠，減少水分流失度過乾旱'),
            ('皇帝企鵝適應寒冷環境嘅特徵係？', ['短而濃密羽毛＋厚脂肪＋腳有蹼', '大耳朵', '夏眠', '長毛髮'], '短而濃密羽毛＋厚脂肪＋腳有蹼', '濃密羽毛保持體溫，厚脂肪保暖，腳有蹼方便游泳'),
            ('沙漠棉尾兔同北極兔比較，沙漠棉尾兔有咩特徵？', ['淺色＋大耳朵（散熱、偽裝）', '白色厚毛', '厚脂肪', '細小耳朵'], '淺色＋大耳朵（散熱、偽裝）', '沙漠炎熱，大耳散熱；淺色偽裝'),
            ('以下邊個係「保護色」嘅例子？', ['獅子金黃色身軀喺草原', '竹節蟲似樹枝', '箭毒蛙鮮艷顏色', '沙丁魚成群游動'], '獅子金黃色身軀喺草原', '獅子金黃色似草原顏色＝保護色；竹節蟲係偽裝；箭毒蛙係警戒色'),
        ],
    },
}

AI_TOPICS = {
    "bio": {
        "name": "生物的分類",
        "context": "教材知識點：動物分為脊椎動物（魚類、兩棲類、爬行類、鳥類、哺乳類，共 5 類）同無脊椎動物（如昆蟲類）。各類特徵：魚類皮膚濕潤有鱗片、用鰓呼吸；兩棲類皮膚濕潤無鱗片、用肺加皮膚呼吸（青蛙、蠑螈）；爬行類皮膚乾燥有鱗片、只用肺呼吸（蛇、烏龜、蜥蜴）；鳥類有羽毛有喙、卵生（企鵝即使唔識飛都係鳥類）；哺乳類有毛髮、用母乳餵養幼兒、用肺呼吸（蝙蝠、海豚、鯨魚都係哺乳類，海豚鯨魚唔係魚類）。昆蟲類有三對腳、身體分頭胸腹、有觸角。判斷動物類別先睇皮膚同呼吸方式。植物分有花植物（會開花結果、以種子繁殖，如百合、水仙、鳳凰木）同無花植物（永不開花：蕨類、苔蘚以孢子繁殖；松樹係裸子植物、以種子繁殖、種子生喺球果內）。植物亦可按生長環境分水生（睡蓮、水葫蘆）同陸生（鳳凰木）。",
        "concepts": [
            "脊椎動物有五類：魚類、兩棲類、爬行類、鳥類、哺乳類",
            "兩棲類皮膚濕潤無鱗片，用肺和皮膚呼吸，例子青蛙、蠑螈",
            "爬行類皮膚乾燥有鱗片，只用肺呼吸，例子蛇、烏龜、蜥蜴",
            "鳥類有羽毛有喙，卵生；企鵝不會飛也是鳥類",
            "哺乳類有毛髮、用母乳餵養幼兒、用肺呼吸",
            "蝙蝠、海豚、鯨魚都是哺乳類，不是鳥類或魚類",
            "昆蟲類無脊椎動物：三對腳、頭胸腹三部分、一對觸角",
            "有花植物會開花結果、以種子繁殖",
            "無花植物永不開花；蕨類苔蘚以孢子繁殖",
            "松樹是無花植物但以種子繁殖（種子生在球果內）",
            "水生植物例子睡蓮、水葫蘆；陸生植物例子鳳凰木",
        ],
    },
    "plant": {
        "name": "植物與環境",
        "context": "教材知識點：不同地方嘅氣溫同雨量影響植物生長。植物用根、莖、葉適應環境。沙漠（乾旱、晝夜溫差大）：根深入泥土或淺而廣（吸收水分）、仙人掌莖肥厚（儲水）、葉成刺狀（減少水分流失）。熱帶雨林（炎熱多雨、樹木密集陰暗）：板狀根（支持樹木長高、爭取陽光）、藤本植物攀附大樹向上（爭取陽光）、葉片闊大而光滑（多接觸陽光、避免雨水積存）。濕地紅樹林（泥土含氧量低、含鹽量較高、每天潮水漲退）：根直立伸出泥土（吸取空氣中氧氣）、蓮藕長滿洞孔（吸取氧氣）、葉片表面厚蠟質（減少水分流失）。植物自我保護：夾竹桃整株有毒、生石花外形似石頭、蠍子草葉柄有刺、含羞草葉片受觸碰閉合、樟樹開花散發特別氣味。人類要愛護樹木。",
        "concepts": [
            "氣溫和雨量影響植物生長",
            "沙漠植物根深入泥土，吸收地下深處水分",
            "紅樹林的根伸出泥土，吸取空氣中氧氣",
            "板狀根支持樹木長高，增加接觸陽光機會",
            "仙人掌的莖肥厚，儲存水分",
            "藤本植物攀附大樹向上生長，爭取陽光",
            "蓮藕長滿洞孔，在缺氧泥土中吸取氧氣",
            "仙人掌的葉成刺狀，減少水分流失",
            "紅樹植物葉面有厚蠟質，減少水分流失",
            "熱帶雨林植物葉片闊大，增加接觸陽光機會",
            "夾竹桃整株有毒；生石花似石頭；蠍子草有刺；含羞草葉片閉合；樟樹散發氣味",
        ],
    },
    "animal": {
        "name": "動物與環境",
        "context": "教材知識點：不同自然環境（熱帶雨林、沙漠、熱帶草原、極地）孕育不同動物。寒冷環境適應：北極熊厚脂肪＋濃密毛＋細小耳朵；皇帝企鵝短而濃密羽毛＋厚脂肪＋腳有蹼。乾旱環境適應：駱駝駝峰儲脂肪、排出很少水分；蝸牛乾燥天氣夏眠、用黏液封殼口；非洲陸龜厚鱗片硬殼減少水分蒸發。北極兔白色厚毛保暖偽裝；沙漠棉尾兔淺色大耳散熱偽裝。動物保護自己四大方法：保護色（顏色似環境，如年幼海豹白色、獅子金黃色、草蜢綠色）、偽裝（形態似物體，如葉海龍似海藻、竹節蟲似樹枝、枯葉蝶似枯葉、比目魚似沙石）、警戒（鮮艷顏色警告有毒，如箭毒蛙、豪豬尖刺）、羣居（成群活動合力嚇走捕食者，如沙丁魚、花鹿）。覓食與身體特徵：蜂鳥尖長喙吸花蜜、長頸鹿長頸食高處樹葉、獅子鋒利犬牙撕裂肉類、螳螂鐮刀狀前肢捉蟲、鷹鋒利喙爪捉獵物、鸕鶿大喉囊吞魚、鋸魚鋸刀狀吻部攻擊獵物；食肉動物鋒利犬牙、食草動物扁平臼齒。冬眠 vs 夏眠：蛇松鼠青蛙會冬眠；乾旱動物可能夏眠；金魚唔冬眠。",
        "concepts": [
            "北極熊：厚脂肪、濃密毛、細小耳朵，適應寒冷",
            "皇帝企鵝：短而濃密羽毛、厚脂肪、腳有蹼",
            "駱駝駝峰儲脂肪，不是儲水",
            "蝸牛乾燥天氣夏眠，用黏液封殼口",
            "保護色＝顏色與環境相似（海豹、獅子、草蜢）",
            "偽裝＝形態似環境物體（竹節蟲、枯葉蝶、葉海龍）",
            "警戒色＝鮮艷顏色警告有毒（箭毒蛙）",
            "羣居＝成群活動嚇走捕食者（沙丁魚、花鹿）",
            "蜂鳥尖長喙吸花蜜；獅子犬牙撕裂肉類",
            "食草動物扁平臼齒磨碎植物",
            "金魚不會冬眠；冬眠例子蛇、松鼠、青蛙",
        ],
    },
}

# ===== 頁面 =====
st.title("❓ 常識選擇題生成器")
st.caption("小六常識科 MCQ 訓練 — 揀主題 → 每輪出題 → 即場作答自動批改。題目 100% 嚟自教材！")

if "gs_questions" not in st.session_state:
    st.session_state.gs_questions = []
if "gs_checked" not in st.session_state:
    st.session_state.gs_checked = False

def options_for_mode(mode_is_ai):
    if mode_is_ai:
        return [k for k in AI_TOPICS]
    return list(QUESTION_BANK.keys())

def label_for(k, mode_is_ai):
    if mode_is_ai:
        return AI_TOPICS[k]["name"]
    else:
        data = QUESTION_BANK[k]
        date = data.get('date', '')
        return f"{data['name']} ({date})" if date else data['name']

def ai_generate(count, topics):
    api_base, api_key, model = get_api_config()
    if not api_key:
        st.error("⚠️ 未偵測到 API key — 請去 app 右上 ⋯ → Settings → Secrets 設定（OPENAI_API_KEY）")
        return []
    ctx_lines, pt_lines = [], []
    for t in topics:
        info = AI_TOPICS[t]
        ctx_lines.append(f"【{info['name']}】{info['context']}")
        for c in info["concepts"]:
            pt_lines.append(f"- {c}")
    system_prompt = f"""你係一位經驗豐富嘅小學六年級常識科老師，專責出「選擇題」練習。

**教材知識點（只准用呢啲知識點出題，一個事實都唔可以超出教材；唔可以創作教材以外嘅新事實）：**
{chr(10).join(pt_lines)}

**課堂內容背景：**
{chr(10).join(ctx_lines)}

**題目要求：**
1. 每題一條完整選擇題（問題 + 4 個選項 A-D），正式書面語、繁體中文（學校測驗卷風格）
2. 4 個選項：1 個正確答案 + 3 個干擾選項，全部必須符合「教材知識點」範圍
3. 干擾選項要「似層層」：用教材入面容易混淆嘅概念（例如兩棲類 vs 爬行類、保護色 vs 偽裝、儲脂肪 vs 儲水）
4. 「answer」欄必須同「options」入面正確嗰個選項**字面完全一樣**（原字照寫，唔准加 A/B/C/D 前綴、唔准加括號、唔准寫多餘字），且答案內容必須同教材知識點完全一致
5. 唔好出超過教材範圍嘅題目
6. 每題附 hint：用書面語解釋點解揀呢個答案（引用教材知識點）

7. **單一答案鐵律**：每題必須只有一個正確答案。如果空位／問題可以有兩個或以上合理答案，你一定要改題目（加語境限制）令答案唯一。嚴禁出「哪兩個／哪些／多選」等多答案題目。
8. **出題後自我檢查**：答案係咪原字喺 options 入面？其餘三個選項係咪明顯錯？如果唔係，即刻改題目／選項。

**輸出格式（只輸出 JSON array，唔好有其他文字）：**
[{{"question": "...", "options": ["...", "...", "...", "..."], "answer": "...", "hint": "..."}}]"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"請根據教材知識點生成 {count} 條常識選擇題（4 個選項、附 hint；answer 必須原字照寫 options 入面正確嗰個選項，唔准加 A/B/C/D 前綴）。"},
        ],
        "max_tokens": 6000,
        "temperature": 0.8,
        "enable_thinking": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        r = requests.post(f"{api_base}/chat/completions", json=payload, headers=headers, timeout=180)
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 連唔到 API：{e}")
        return []
    if r.status_code != 200:
        st.error(f"❌ AI 生成失敗（錯誤碼 {r.status_code}）：{r.text[:200]}")
        return []
    content = r.json()["choices"][0]["message"]["content"]
    data = parse_ai_json(content)
    if not isinstance(data, list):
        st.error("❌ AI 回覆格式唔啱，再試一次？")
        return []
    valid = []
    for item in data:
        q = (item.get("question") or "").strip()
        opts = item.get("options") or []
        ans = (item.get("answer") or "").strip()
        hint = (item.get("hint") or "").strip()
        if re.search(r"哪兩個|邊兩個|哪幾|哪些|多選|兩項|兩個答案|邊幾|which two|select all|all that apply", q):
            continue
        if not q or not isinstance(opts, list) or len(opts) != 4:
            continue
        clean_opts = [o.strip() for o in opts]
        matched = _match_answer(ans, clean_opts)
        if matched is None:
            continue
        valid.append({"q": q, "options": clean_opts, "answer": matched, "hint": hint})
    if not valid:
        st.error("❌ AI 生成嘅題目全部唔合格（答案唔喺選項入面）— 再試一次？")
    return valid[:count]

def build_round(mode_is_ai, topics, count):
    """生成一輪題目；成功回 True，失敗（例如 AI 出錯）回 False — 失敗時唔 rerun，等錯誤訊息留喺畫面"""
    if mode_is_ai:
        with st.spinner("✨ AI 生成緊題目，請稍候…（約 10–30 秒）"):
            qs = ai_generate(count, topics)
    else:
        pool = [q for t in topics for q in QUESTION_BANK[t]["questions"]]
        random.shuffle(pool)
        qs = []
        for q, choices, ans, hint in pool[:count]:
            opts = list(choices)
            random.shuffle(opts)
            qs.append({"q": q, "options": opts, "answer": ans, "hint": hint})
    if not qs:
        return False
    st.session_state.gs_questions = qs
    st.session_state.gs_checked = False
    return True

# ===== Sidebar =====
with st.sidebar:
    st.header("⚙️ 設定")
    mode_is_ai = st.radio("生成模式", ["📖 教材原題（即時・100% 教材）", "✨ AI 生成新題（qwen3.8-flash）"], key="gs_mode") == "✨ AI 生成新題（qwen3.8-flash）"
    all_opts = options_for_mode(mode_is_ai)
    topics = st.multiselect(
        "揀主題（可多選）",
        all_opts,
        format_func=lambda k: label_for(k, mode_is_ai),
        key="gs_topics",
    )
    count = st.slider("每輪題數", 5, 20, 10, key="gs_count")
    if st.button("🎲 生成題目", type="primary", use_container_width=True):
        if not topics:
            st.warning("⚠️ 請先揀至少一個主題")
        else:
            try:
                if build_round(mode_is_ai, topics, count):
                    st.rerun()
            except Exception as e:
                st.error(f"❌ 出錯：{e}")
    if topics:
        with st.expander("📚 知識點"):
            if mode_is_ai:
                for t in topics:
                    st.markdown(f"**{AI_TOPICS[t]['name']}**（{len(AI_TOPICS[t]['concepts'])} 點）")
                    for c in AI_TOPICS[t]["concepts"]:
                        st.markdown(f"- {c}")
            else:
                for t in topics:
                    st.markdown(f"**{QUESTION_BANK[t]['name']}**（{len(QUESTION_BANK[t]['questions'])} 題）")

st.divider()

# ===== 出題 =====
if not st.session_state.gs_questions:
    st.info("👈 左邊 sidebar：揀生成模式 → 揀主題（可多選）→ 㩒「🎲 生成題目」開始！")
    bank_total = sum(len(v["questions"]) for v in QUESTION_BANK.values())
    st.markdown(f"📚 **題庫規模：** 共 {bank_total} 條教材原題，涵蓋 Unit 1 生物的分類・Unit 2 植物與環境・Unit 3 動物與環境。")
    st.stop()

qs = st.session_state.gs_questions
st.subheader(f"📝 今輪 {len(qs)} 題")
for i, item in enumerate(qs):
    st.radio(f"**{i + 1}.** {item['q']}", item["options"], key=f"gs_a{i}", index=None)

c1, c2, c3 = st.columns([1, 1, 3])
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
    mode_is_ai = st.session_state.gs_mode == "✨ AI 生成新題（qwen3.8-flash）"
    topics = st.session_state.gs_topics
    count = st.session_state.gs_count
    if topics:
        try:
            if build_round(mode_is_ai, topics, count):
                st.rerun()
        except Exception as e:
            st.error(f"❌ 出錯：{e}")
# Updated at Fri Oct  9 10:51:58 CST 2026
