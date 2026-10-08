# 交接說明（2026-10-08）

給接手的 agent：規格在 [SPEC.md](SPEC.md)，使用與設計說明在 [README.md](README.md)。

## 已完成

- **Python 解析器**（`ass2ae/tags.py`、`karaoke.py`、`parser.py`、`timing.py`）：規則照 libass、Aegisub AssKaraoke、karaskel，SPEC 每條規則都有測試。
- **JSX 產生器**（`jsxgen.py` 加上 ES3 的 `runtime.jsx`）
  - 歌詞圖層、marker、setParameters、變色 animator、重跑安全、自我檢查。
  - template 模式與 ass 模式。
  - 用基線＋字型 metrics 做垂直對齊。
- **振假名圖層**：照 karaskel 的排版群組（`lg`）處理 `!`、`<`。重疊時把振假名往右推，不撐開主文字。父層設為所屬的歌詞層。
- **檢視器**（`runtime.jsx` 的 `run()`）
  - **對目前的合成執行時**：先決定目標，再切到同尺寸的暫時合成 `_ass2ae_redirect_`。建完刪掉它，全部包在 undo group 裡。
  - **新合成、產生專案時**：不切換。合成用 `app.scheduleTask` 在腳本結束後才打開。如果在同一個腳本裡、剛加完文字圖層就打開新的檢視器，AE 會跳出「internal verification failure {no current context}」（已用二分法在 AE 實測確認）。
- **直接產生 AE 專案**（`project.py`）
  - **啟動 AE**：AE 沒開時，先不帶腳本把 AE 開起來，等主視窗出現後才送 `-r`。用 `-r` 直接冷啟動 AE，跑完腳本 AE 就會自己結束（已實測），使用者也就看不到專案。
  - **啟動選項**：AE 以 `CREATE_BREAKAWAY_FROM_JOB` 啟動，避免呼叫它的程式結束時被一起關掉。
  - **等不到主視窗**：最多等 15 分鐘，然後回報錯誤，不會把腳本盲目送出（腳本會被丟掉）。
- **GUI**（`gui.py`）、**exe 打包**（`tools/build/`）。打包版的命令列輸出到 pipe 或檔案時用 UTF-8。
- **AE 實測工具**（`tools/ae/`）
  - `run_in_ae.py fixtures`：分兩個腳本執行。第一次指定目標，第二次對開在檢視器的合成重跑。會印出每次的秒數。
  - `run_in_ae.py e2e`：在程式裡操作 GUI 建專案，再重開 .aep，檢查 marker 參數、時間、父層。
  - `dialogs.py`：自動關掉 AE 的訊息框並記錄，算成失敗，避免一個錯誤擋住後面所有腳本。
  - 實測檔用 `ass_example/snooze_short.ass`。整首歌的 `kk_ass`、`snooze_full` 要用 `--only` 指名才跑。
- **測試**：pytest 174 個全過。2026-10-08 在 AE 實測：
  - `e2e`：OK，38 秒，AE 留著，重開後 20 層、68 個 marker 都正確。
  - `fixtures`：7 個案例全 OK，每次執行 0～8 秒。
  - 兩者都沒有出現任何 AE 訊息框。

## 未完成／注意

1. **GUI 真人點擊**：`e2e` 走的是 GUI 本身的按鈕和流程，但還是建議請使用者用 exe 實際按一次。`dist/` 沒進 git，要先 build：`.venv\Scripts\python tools\build\build_exe.py`。
2. **AE 磁碟快取**：反覆用影片（`snooze.mp4`，60fps HEVC）建專案時，AE 快取 `%LOCALAPPDATA%\Temp\Adobe\After Effects` 曾經把 C 槽塞滿（38.8 GB）。
   - 跑有影片的測試前，先看 C 槽剩餘空間。
   - 不要自己刪快取或改 AE 偏好設定，要先問使用者。
3. **強制結束 AE 的後果**：下次啟動會跳出「Crash Repair Options」，要請使用者按「Continue」。
   - 要關測試用的 AE，先用腳本 `app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES)`（大專案要等二十幾秒），再用不帶 `/F` 的 `taskkill` 關掉。

## 環境備註

- **AE 版本**：AE 2025（25.3）裝在 `C:\Program Files\Adobe\Adobe After Effects 2025`。偏好設定「Allow Scripts to Write Files and Access Network」已開。
- **ass_example/**：使用者自己的歌詞與影片。`snooze_short.ass` 是使用者自己 commit 的，其他檔案不要 commit。
- **快照**：改了 `runtime.jsx` 或 `jsxgen.py` 之後要更新：`set UPDATE_SNAPSHOTS=1 && .venv\Scripts\python -m pytest`。
- **ES3 檢查**：`node tests/js/check_es3.js <file>`。檢查會擋 `.indexOf`（包括字串的），請改用 `substr` 比對。
- **溝通**：使用者用繁體中文；跑長時間的 AE 測試前，先說大概要多久。
