# ❓ 常識選擇題生成器（gs-trainer）

小六常識科 MCQ 訓練 app — 揀主題 → 每輪出題 → 即場作答自動批改。

## 功能
- **揀主題（可多選）**：生物的分類（Unit 1）／植物與環境（Unit 2）／動物與環境（Unit 3）
- **兩種生成模式**：
  - 📖 **教材原題**：直接由 60 條教材題庫抽題（100% 教材、即時、唔使 API）
  - ✨ **AI 生成新題**：qwen3.8-flash 根據教材知識點生成全新選擇題（每輪新鮮；只准用教材知識點，唔可以作新事實）
- 每輪 5–20 題（預設 10 題）、4 個選項、自動批改 + 書面語解釋
- 側欄可展開教材知識點溫習

## 題庫來源
60 條教材原題，由 2026-09-07～09-26 常識科教材整理：
- Unit 1《生物的分類》：動物六大類特徵、特殊案例（蝙蝠／海豚／鯨魚／企鵝／海龜）、脊椎 vs 無脊椎、植物分類與繁殖
- Unit 2《植物與環境》：根／莖／葉適應（沙漠、熱帶雨林、濕地）、植物自我保護五例
- Unit 3《動物與環境》：寒冷／乾旱適應、保護色 vs 偽裝 vs 警戒 vs 羣居、覓食與身體特徵

## 部署（Streamlit Cloud）
1. GitHub 開新 repo（`gs-trainer`）→ 上傳呢 5 個項目
2. share.streamlit.io → New app → 揀 repo → main file `app.py` → Deploy
3. App ⋯ → Settings → Secrets 加三行：
   ```
   OPENAI_API_KEY = "sk-你條key"
   SILRA_API_URL = "https://api.silra.cn/v1/chat/completions"
   MODEL_NAME = "qwen3.8-flash"
   ```
4. Save → Rerun → 完成

## 本地執行
```bash
pip install -r requirements.txt
streamlit run app.py
```
