# TW Stock MVP 進度摘要

## 專案目標
建立一個台股觀察與分析 MVP，先以「趨勢觀察 + 風險提示」為主，協助使用者快速判斷股票偏多、中性或偏空的狀態，而不是直接宣稱精準預測未來漲跌。

## 目前已完成

### 1. 基礎架構
- 已建立 Python 專案入口：[app.py](/Users/shushu/Development/Vibe/twstock/app.py:1)
- 已拆出資料抓取、正規化、評分、觀察清單與 Web UI 模組
- 目前不依賴外部套件，使用 Python 標準函式庫即可執行

### 2. 已串接的資料來源
- TWSE OpenAPI:
  - `/exchangeReport/BWIBBU_ALL`
  - `/exchangeReport/STOCK_DAY_AVG_ALL`
  - `/opendata/t187ap04_L`
  - `/Announcement/BFZFZU_T`
  - `/exchangeReport/MI_MARGN`
  - `/exchangeReport/MI_5MINS`
- TWSE 報表 API:
  - `/exchangeReport/STOCK_DAY?response=json&date=YYYYMMDD&stockNo=股票代號`
  - `/exchangeReport/BWIBBU_d?response=json&date=YYYYMMDD&selectType=ALL`

### 3. 資料與分析能力
- 已完成股票快照整併
- 已完成趨勢分數計算
- 已完成偏多 / 中性 / 偏空分類
- 已加入重大訊息、異常推介、融資融券、委買委賣量等評分依據
- 個股頁的本益比、殖利率、股價淨值比已改成優先使用 `BWIBBU_d` 依日期查詢
- `BWIBBU_d` 在 live 模式下支援近 7 日往前回找可用交易日

### 4. Web MVP 功能
- 已有首頁自選股觀察表
- 可在頁面上直接輸入股票代號更新觀察清單
- 可切換 `sample` / `live` 資料來源
- 可進入單一股票分析頁

### 5. 個股分析頁
- 顯示收盤價、月均價、本益比、殖利率、股價淨值比
- 顯示趨勢分數與關鍵原因
- 顯示近期重大訊息
- 顯示籌碼觀察
- 已補上融資 / 融券增減的判讀說明與進出場意義

### 6. 技術走勢
- 已串接 `STOCK_DAY`
- 個股頁已顯示近 3 個月收盤技術線
- 已加入 `5 日均線`
- 已加入 `20 日均線`
- 首頁自選股表已新增近 2 週每日漲跌圖示與漲跌金額

## 已驗證狀態

### 1. 語法與執行
- `python3 -m py_compile app.py twstock_mvp/*.py` 已通過
- `python3 app.py --serve` 可啟動 Web UI
- `python3 app.py --offline-sample --serve` 可啟動示範資料版 UI

### 2. API 驗證
- `STOCK_DAY` 已實測成功，可收到 `2330` 的歷史日資料 response
- `BWIBBU_d` 已實測成功，可收到 live response
- 其餘 API 已整合進 live 資料流程使用

### 3. 畫面驗證
- 首頁已確認出現 `近 2 週漲跌` 欄位
- 個股頁已確認出現 `近 3 月收盤技術線`
- 個股頁已確認出現 `5 日均線`、`20 日均線`
- 個股頁已確認使用 `BWIBBU_d` 估值資料

## 目前主要檔案
- 入口：[app.py](/Users/shushu/Development/Vibe/twstock/app.py:1)
- 資料抓取：[twstock_mvp/data.py](/Users/shushu/Development/Vibe/twstock/twstock_mvp/data.py:1)
- 範例資料：[twstock_mvp/sample_data.py](/Users/shushu/Development/Vibe/twstock/twstock_mvp/sample_data.py:1)
- 資料正規化：[twstock_mvp/normalize.py](/Users/shushu/Development/Vibe/twstock/twstock_mvp/normalize.py:1)
- 評分邏輯：[twstock_mvp/scoring.py](/Users/shushu/Development/Vibe/twstock/twstock_mvp/scoring.py:1)
- 自選股分析：[twstock_mvp/watchlist.py](/Users/shushu/Development/Vibe/twstock/twstock_mvp/watchlist.py:1)
- Web UI：[twstock_mvp/web.py](/Users/shushu/Development/Vibe/twstock/twstock_mvp/web.py:1)
- 規格草案：[readme.txt](/Users/shushu/Development/Vibe/twstock/readme.txt:1)

## 目前可直接使用的指令

### Web UI
```bash
python3 app.py --serve
```

### 離線示範資料版
```bash
python3 app.py --offline-sample --serve
```

### 歷史日資料測試
```bash
python3 app.py --stock-day --stock-no 2330 --date 20250101
```

## 下一步可做
- 技術圖加入成交量
- 加入更多均線與技術指標
- 加入股票名稱搜尋與自動補全
- 加入歷史回測
- 加入通知與警示
- 加入新聞情緒分析

## 最新進度更新（2026-04-12）

### 1. UI 與版型改版
- 已改為看盤軟體風格（黑底高對比，台股色系：漲紅跌綠）
- 版面已改為「上半 1 區 + 下半 3 區」
- 畫面已調整為滿版顯示（移除左右預留空間）
- 字級已整體放大，提升可讀性

### 2. 上半總覽功能強化
- 自選股欄位已包含：代號/名稱、評分、最新價(日期)、成長預估、近 7 日股價與量、近 7 日融資融券增減
- `近 7 日融資融券增減` 已加入 `?` 說明（點選展開）
- 自選股代碼已支援 Cookie 記憶（`watch_codes`，30 天）
- 第一列固定顯示大盤資料

### 3. 大盤資料來源與近 7 日
- 大盤即時資料改為 `MI_INDEX`（`/exchangeReport/MI_INDEX`）
- 已支援 `寶島股價指數` 欄位格式（含 `漲跌` + `漲跌點數` + `漲跌百分比`）
- 大盤近 7 日資料改為 `MI_5MINS_HIST`（`/indicesReport/MI_5MINS_HIST`）
- 近 7 日增減以 `ClosingIndex` 與前一日相減計算

### 4. 下半三區功能
- 左區：30 天技術線圖含成交量，加入日期刻度、股價軸（1 元級距）、成交量最大/最小值，並支援滑鼠 hover 顯示當日收盤價
- 中區：新聞改用 `news/newsList`，預設過濾近三天資料；同區新增 `BWIBBU_d` 估值資訊（本益比、殖利率、股價淨值比，含日期）
- 右區：關聯股邏輯已改
  - 若所選為 ETF：顯示前五大成分股（含權重）
  - 若所選為單一股票：顯示同產業最相關前五檔（以流動性排序）

### 5. 評分可解釋性
- 評分模型仍為規則式（非 API 直接給分）
- 已新增「評分加減分明細」顯示每條規則的分數影響，便於追蹤分數來源

### 6. 資料與模組更新
- `DatasetBundle` 已擴充：`industry_info`、`market_index`、`market_hist`
- sample 資料已補齊：產業資料、ETF 關聯示例、大盤即時與歷史資料
- 主要更新檔案：
  - `twstock_mvp/web.py`
  - `twstock_mvp/data.py`
  - `twstock_mvp/sample_data.py`
  - `twstock_mvp/scoring.py`

## 最新進度更新（2026-04-13）

### 1. 執行驗證
- 已再次執行語法檢查：`python3 -m py_compile app.py twstock_mvp/*.py` 通過
- 已啟動 `python3 app.py --offline-sample --serve`，確認 Web UI 可正常啟動（`http://127.0.0.1:8000`）

### 2. 新聞區評分資訊強化
- 已將新聞區「評分加減分明細」升級為「評分完整計算數據」
- 新增完整計算流程欄位：`步驟 / 前分 / 變動 / 後分 / 規則`
- 新增分數說明：`基準分`、`原始最終分`、封頂/封底後分數提示
- 新增輸入數據摘要（收盤價、月均價、委買賣量、本益比、殖利率、PB、融資融券增減、重大訊息筆數、異常推介）

### 3. 近 7 日融資融券資料策略調整
- 已確認 live 模式資料來源為 TWSE API：`/exchangeReport/MI_MARGN`
- 依需求調整：live 模式若抓不到融資融券資料，不再回退預估序列
- 現在抓不到資料時，欄位直接顯示 `--`

### 4. 本次主要更新檔案
- `twstock_mvp/web.py`
