# 交接說明（2026-10-06）

給接手的 agent：規格在 [SPEC.md](SPEC.md)，使用與設計說明在 [README.md](README.md)。

## 已完成

- **Python 解析器**（`ass2ae/tags.py`、`karaoke.py`、`parser.py`、`timing.py`）：規則照 libass、Aegisub AssKaraoke、karaskel，SPEC 每條規則都有測試。
- **JSX 產生器**（`jsxgen.py` 加上 ES3 的 `runtime.jsx`）
  - 歌詞圖層、marker、setParameters、變色 animator、重跑安全、自我檢查。
  - template 模式與 ass 模式。
  - 用基線＋字型 metrics 做垂直對齊。
- **振假名圖層**（SPEC 原本列為「這階段不做」，使用者後來要求加上）
  - Python 端：`jsxgen.furi_groups`。
  - JSX 端：`createFuri`、`placeFuri`，用暫時的「尺規」文字層量字寬來定位。
  - 振假名層的父層設為所屬的歌詞層。
- **直接產生 AE 專案**（`project.py`）：產生驅動腳本，透過 AfterFX.exe -r 匯入影片、建合成、跑歌詞、存 .aep，用 status.json 或 .aep 的修改時間判斷完成。CLI 選項是 `--video/--aep/--afterfx`。
- **GUI**：`gui.py`，tkinter 中文介面，執行工作放在背景執行緒。
- **exe 打包**：`tools/build/build_exe.py`（PyInstaller，onefile），入口是 `tools/build/ass2ae_app.py`，不帶參數開 GUI、帶參數跑命令列。
  - 已實測：打包版的命令列輸出與 Python 版完全一致；exe 建 AE 專案的端到端流程成功（35 秒）；GUI 能正常開啟和關閉。
  - `dist/` 沒有進 git，要重新 build。
- **測試**：pytest 168 個全過。AE 實測工具在 `tools/ae/run_in_ae.py`（`probe`、`fixtures`）。

## 進行中／未完成

1. **完整 AE 回歸測試（加了振假名之後）**
   - 已跑完並驗證通過：jp_ass、jp_template、en_ass、furi_ass、kk_ass、snooze_template。templated_ass 只有一個預期內的警告：noK 樣式的字型 Noto Serif CJK JP Black 這台沒裝。
   - **snooze_ass 沒跑完**：runner 等了 900 秒逾時，之後 AE 也關了。要用 `python tools/ae/run_in_ae.py fixtures --only snooze_ass` 重跑。
   - kk_ass 一個案例就花了約 7 分鐘（兩次執行）。慢的是第二次重跑：合成已經開在檢視器裡，見下一項。
2. **效能：對「開在檢視器裡」的合成執行時非常慢**
   - 實測：snooze（有 60fps HEVC 影片）的合成開在檢視器裡時，跑 13 分鐘以上都沒完成，AE 吃到 10GB 記憶體。同樣內容用新專案、最後才打開合成的流程，只要約 30 秒。
   - 已改：runtime 新建合成時，改成全部建完才 `openInViewer()`。
   - **待做**：目標合成本來就開在檢視器時（例如使用者自己重跑、或 harness 的第二次執行），在 `run()` 開頭先建一個暫時的空合成並 `openInViewer()`，把檢視器切走；建完後切回目標合成，再刪掉暫時合成。
   - 改完後要量 kk_ass 的時間，並在 README「已知限制」更新說明。
3. **probe 腳本仍用 `saveFrameToPng`**：`tools/ae/probes/probe_api.jsx` 的 render 區段。這可能讓 AE 卡住無法關閉（實際發生過一次）。要改成用 `lib.jsx` 的 `T.renderFrame`（Render Queue，輸出 TIFF）。
4. **GUI 尚未用真人點擊做端到端測試**：只測過畫面截圖、exe 開關，以及同一套流程的命令列模式。建議請使用者用 exe 選 snooze.ass 加 snooze.mp4 實際按一次。
5. **小問題**
   - 打包版的命令列在 Git Bash 裡印日文警告會亂碼（主控台編碼 cp950 對 UTF-8）。GUI 不受影響。
   - 振假名排版沒有處理相鄰振假名的推擠，也沒處理 `<`、`!` 旗標（README 已列為限制）。
   - 還沒測 marker 參數在存檔、重開專案後是否保留。

## 環境備註

- **AE 版本**：AE 2025（25.3）裝在 `C:\Program Files\Adobe\Adobe After Effects 2025`。實測工具需要開啟偏好設定「Allow Scripts to Write Files and Access Network」（使用者已開）。
- **ass_example/**：使用者自己的實際歌詞檔與影片，**不要 commit**。`snooze_ass2ae.aep` 是給使用者看效果的專案，16:00 用新流程重建過，有振假名。
- **快照**：改了 `runtime.jsx` 或 `jsxgen.py` 之後要更新：`set UPDATE_SNAPSHOTS=1 && .venv\Scripts\python -m pytest`。
- **ES3 檢查**：`node tests/js/check_es3.js <file>`，需要先 `npm install --prefix tests/js`。
- **改 runtime.jsx 的方式**：用 Write 工具寫 Python 修補腳本再執行。在 Bash 的 heredoc 裡寫含反斜線或引號的程式碼曾經出錯。
- **溝通**：使用者用繁體中文溝通；跑長時間的 AE 測試前，請先告訴使用者大概要多久。
