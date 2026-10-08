# 交接說明（2026-10-08）

給接手的 agent：規格在 [SPEC.md](SPEC.md)，使用與設計說明在 [README.md](README.md)。

## 已完成

- **Python 解析器**（`ass2ae/tags.py`、`karaoke.py`、`parser.py`、`timing.py`）：規則照 libass、Aegisub AssKaraoke、karaskel，SPEC 每條規則都有測試。
- **JSX 產生器**（`jsxgen.py` 加上 ES3 的 `runtime.jsx`）
  - 歌詞圖層、marker、setParameters、變色 animator、重跑安全、自我檢查。
  - template 模式與 ass 模式。
  - 用基線＋字型 metrics 做垂直對齊。
- **振假名圖層**
  - Python 端：`jsxgen.furi_groups`，每組帶 karaskel 的排版群組 `lg` 和 `<` 旗標 `spill`。
  - JSX 端：`createFuri`、`placeFuri`。照 karaskel 分組排版，`!`、`<` 旗標都有作用；重疊時把振假名往右推，不撐開主文字。
  - 振假名層的父層設為所屬的歌詞層。
- **檢視器切換**（`runtime.jsx` 的 `run()`、`hideViewer()`）
  - 先用 `targetComp()` 決定目標合成，再把檢視器切到 4×4 的暫時合成 `_ass2ae_redirect_`。建完後切回目標合成，再刪掉暫時合成。
  - 這段放在 undo group 裡面，所以按一次 Ctrl+Z 會全部復原。
  - 前一任 agent 版本的 bug：先切檢視器、才讀 `activeItem`，所以使用者對「目前的合成」執行時，歌詞會建進暫時合成裡，接著被刪掉。這一版已修正。
- **直接產生 AE 專案**（`project.py`）、**GUI**（`gui.py`）、**exe 打包**（`tools/build/`）。
  - 打包版的命令列輸出到 pipe 或檔案時改用 UTF-8，在 Git Bash 裡不再亂碼。
- **AE 實測工具**（`tools/ae/run_in_ae.py`）
  - `probe`：probe 的渲染已改用 `T.renderFrame`，已在 AE 跑過。
  - `fixtures`：第二次執行改走「檢視器裡的目前合成」路徑。會記錄每次執行的秒數，並檢查暫時合成沒有殘留、振假名沒有互相重疊。
  - `e2e`：在程式裡操作 GUI 產生專案，再重開 .aep，檢查 marker 參數和父層是否保留。
- **測試**：pytest 170 個全過。

## 進行中／未完成

1. **AE 實測結果**：這一版的 `e2e` 和 `fixtures` 正在跑，結果會補在下一個 commit。
   - 之前的 `e2e` 已經用 GUI 成功建好 snooze 專案（108 秒）。當時是測試腳本自己印結果時出錯（cp950），已修正。
2. **測試檔**：AE 實測請用 `ass_example/snooze_short.ass`，這是使用者剪短的版本。整首歌的 `kk_ass`、`snooze_full` 只有用 `--only` 指名時才跑。
3. **GUI 真人點擊**：`e2e` 走的是 GUI 本身的按鈕和流程，但還是建議請使用者用 exe 實際按一次。`dist/` 沒進 git，要先 build：`.venv\Scripts\python tools\build\build_exe.py`。

## 環境備註

- **AE 版本**：AE 2025（25.3）裝在 `C:\Program Files\Adobe\Adobe After Effects 2025`。偏好設定「Allow Scripts to Write Files and Access Network」已開。
- **ass_example/**：使用者自己的歌詞與影片，**不要 commit**。
- **快照**：改了 `runtime.jsx` 或 `jsxgen.py` 之後要更新：`set UPDATE_SNAPSHOTS=1 && .venv\Scripts\python -m pytest`。
- **ES3 檢查**：`node tests/js/check_es3.js <file>`，要先 `npm install --prefix tests/js`。檢查會擋 `.indexOf`（包括字串的），請改用 `substr` 比對。
- **溝通**：使用者用繁體中文；跑長時間的 AE 測試前，先說大概要多久。
