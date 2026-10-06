# ass2ae

把 Aegisub 卡拉OK字幕（`.ass` 的 `\k`）轉成一支 After Effects 腳本（`.jsx`）。在 AE 執行後：

- 每行歌詞變成一個文字圖層
- 每個音節變成該圖層上的一個 layer marker：時間＝音節開始、duration＝音節長度、comment＝音節文字
- （預設）每個有 marker 的圖層加一個由 marker 驅動的變色 Text Animator，用來驗證時間

之後的特效可以全部用 expression 讀這些 marker 來做。

## 安裝

需要 Python 3.10 以上。

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[fonts]"
```

`fonts` 這個 extra 會裝 fontTools，用來找字型檔、換算字級。不裝也能跑，只是字級改用 `--font-scale` 估算。

開發時：

```bash
.venv\Scripts\python -m pip install -e ".[fonts,test]"
```

ES3 語法檢查需要 Node.js，並在 `tests/js` 裡裝 acorn：

```bash
npm install --prefix tests/js
```

## 用法

```bash
python -m ass2ae input.ass -o out.jsx
```

會在終端機印出報告：圖層數、marker 數、略過的事件、被移除的標籤統計、各樣式找到的字型，以及所有警告。

### CLI 選項

| 選項 | 預設 | 說明 |
|---|---|---|
| `-o, --output` | 與輸入同名的 `.jsx` | 輸出檔 |
| `--styles A,B` | 全部 | 只轉這些樣式，可重複指定 |
| `--fps` | `24000/1001` | 合成 fps。可寫分數或小數；`23.976`、`29.97`、`59.94` 會自動對應到 `x000/1001` |
| `--offset` | `0` | ASS 的 0 秒對應到合成的哪個時間點。可寫秒數（`12.5`）、時間碼（`1:02.50`）或影格（`48f`），可為負 |
| `--width` / `--height` | PlayResX / PlayResY | 新建合成時的尺寸 |
| `--comp-name` | 輸入檔名 | 新建合成的名稱 |
| `--style-mode` | `template` | `template`：複製合成裡的範本文字層；`ass`：依 ASS 樣式設定字型、顏色、描邊 |
| `--template` | `KARA_TEMPLATE` | 範本圖層名稱。會先找 `<名稱>_<樣式名>`（例如 `KARA_TEMPLATE_K1`），找不到再用 `<名稱>` |
| `--with-animator` / `--no-animator` | 開 | 是否加變色 Animator |
| `--sung-color` | 樣式的 PrimaryColour | 已唱色，`#RRGGBB` 或 `&HBBGGRR&` |
| `--newline-counts` | 關 | marker comment 是否包含換行字元（見下方「換行與 textIndex」） |
| `--font-map FILE` | — | 字型對照表，app.fonts 找不到時才用。JSON `{"ASS 字型名": "PostScriptName"}`，或每行 `ASS 字型名=PostScriptName` |
| `--font-scale` | `0.7` | 讀不到字型檔時，AE 字級 ÷ ASS 字級的比例 |
| `--font-dir DIR` | — | 額外的字型目錄，可重複指定（系統與使用者字型目錄一定會掃） |
| `--no-font-scan` | — | 不用 fontTools 找字型 |
| `--encoding` | `utf-8-sig` | 輸入檔編碼 |
| `--dump-json FILE` | — | 另外輸出嵌進 JSX 的資料（除錯用） |
| `-q, --quiet` | — | 只印錯誤 |

## 在 AE 執行

1. 在 AE 開啟專案。
   - 想加進既有合成：先在時間軸或專案面板選取那個合成。
   - 沒有選取合成時：會依 `--width/--height/--fps` 新建一個。
2. 執行 `File > Scripts > Run Script File...`，選擇產生的 `.jsx`。
3. 結束時會跳出摘要：圖層數、marker 數、被取代的舊圖層數，以及警告。

補充說明：

- **復原**：整個動作包在一個 undo group 裡，按一次 Ctrl+Z 就能全部還原。
- **重跑安全**：執行前會先刪掉上次產生的圖層。只認 `Layer.comment` 開頭的 `[ass2ae]` 標記，其他圖層一律不動。
- **fps 不一致**：選取的合成 fps 和 `--fps` 不同時會警告。
- **合成太短**：選取的合成比歌詞短時也會警告。
- **命令列執行**（Windows）：

  ```bash
  "C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\AfterFX.exe" -r C:\path\out.jsx
  ```

### template 模式（預設）

在合成裡放一個文字層，命名為 `KARA_TEMPLATE`。也可以每個樣式各放一個 `KARA_TEMPLATE_K1`、`KARA_TEMPLATE_K2`，找不到時才用 `KARA_TEMPLATE`。

- **複製時沿用的設定**：只改文字內容。字型、字級、顏色、描邊、段落設定、效果、既有的 animator 全部沿用。
- **未唱色**：範本的填色就是未唱色。
- **範本本身**：可以設成停用（關掉眼睛）。複製出來的圖層會自動啟用，並清掉範本上的 marker。
- **位置**：仍由 ASS 決定（`\an`、`\pos`、邊界）。
- **找不到範本時**：該樣式退回 ass 模式並警告。

### ass 模式

- **顏色**
  - SecondaryColour＝填色（未唱色）
  - OutlineColour＝描邊
  - PrimaryColour＝已唱色
  - 顏色的 alpha 不轉換，非 00 時會警告
- **描邊**：寬度＝Outline×2，並設成填色在描邊上方。描邊只在 `ScaledBorderAndShadow: yes` 時隨 PlayRes 縮放。
- **字型**：ASS 的字型名是 Windows（GDI）的 family 名，例如 `Gen Jyuu Gothic Bold`，可能是日文名。依序這樣解析：
  1. 用 fontTools 掃字型檔，換成 PostScript 名，再用 `app.fonts.getFontsByPostScriptName` 確認。
  2. 掃 `app.fonts.allFonts`，比對 familyName / fullName 及其 native 名稱。
     - 實測 `getFontsByFamilyNameAndStyleName` 只接受排版用的家族名＋樣式（`Gen Jyuu Gothic` + `Bold`），不接受 GDI 名，所以要靠掃描比對。
  3. 套用 `--font-map`，並發出警告。
  4. 都找不到就保留 AE 預設字型，並發出警告。
- **字級**：ASS 的 Fontsize 是 ascent+descent，libass 用 OS/2 的 usWinAscent+usWinDescent。所以 AE 字級＝Fontsize × unitsPerEm ÷ (winAscent+winDescent)。
  - 讀不到字型檔時，改用 Fontsize × `--font-scale`。
  - 行距設成 Fontsize，與 libass 一致。
- **其他樣式欄位**
  - ScaleX/ScaleY 對應到 horizontalScale/verticalScale，Spacing 對應到 tracking，Angle 對應到圖層旋轉。
  - Bold/Italic 在字型本身不是粗體或斜體時，改用仿粗體、仿斜體。
  - Underline/StrikeOut、BorderStyle 3、Shadow 不支援，會警告。

### 位置

依 `\an`（沒有就用樣式的 Alignment）、MarginL/R/V（事件的值不為 0 時優先）或 `\pos`，算出 libass 的對齊點，再從 PlayRes 等比縮放到合成尺寸。

圖層的錨點設在文字框的對齊點上：

- **水平**：用 `sourceRectAtTime` 量文字框，取左、中、右。
- **垂直**：用 `TextDocument.baselineLocs` 取第一條和最後一條基線，再加上字型 metrics 的 ascent/descent。這就是 libass 的行框，所以「ー」和「あ」這類字形高度不同的行，底線不會跳動。
  - metrics 來源依序是 Python 端 fontTools 讀到的值，以及 JSX 直接讀字型檔的 OS/2 表（template 模式用 `TextDocument.fontLocation`）。
  - 都拿不到時，退回 sourceRectAtTime 的上下緣。

## 產生的內容

### 圖層

- **名稱**：`KARA_0001_<前 8 個字>`，依檔案順序編號，KARA_0001 在最上面。
- **`Layer.comment`**：`[ass2ae] line=0001 event=14 style=K2`。`event` 是 Aegisub 字幕格的行號。
- **startTime**：固定為 0，所以圖層時間等於合成時間。
- **入出點**：只用入點、出點裁切。
  - 入點＝ceil(start×fps)/fps，出點＝ceil(end×fps)/fps，與 libass「start ≤ t < end 才顯示」一致。
  - 顯示不到一格的行會跳過並警告。
- **沒有 `\k` 的行**（例如翻譯行）：照樣建立圖層，但不建 marker。

### Marker

- **每個非空音節一個**：`time`＝音節開始，`duration`＝音節長度，`comment`＝音節的顯示文字。
- **comment 與圖層文字的對應**：所有 comment 依序串接後，等於圖層文字（不含換行）。空白也包含在內。
- **其他資訊**：用 `MarkerValue.setParameters()` 存，值一律是字串：

| key | 內容 | 例 |
|---|---|---|
| `kind` | 每段 `\k` 的種類（`\K` 視為 `kf`；第一個 `\k` 前的文字為空字串） | `k,k` |
| `tag` | 原始標籤名 | `k,K` |
| `cs` | 原始值（百分之一秒） | `8,12` |
| `furi` | 振假名 JSON：`[文字, 開始秒（合成時間）, 長度秒, 旗標]`，旗標 `<` 為 spillback、`!` 為 break | `[["ぞ",18.2,0.08,"<"],["う",18.28,0.08,"<"]]` |
| `event` | 事件行號 | `14` |
| `fx` | karaskel 的 inline-fx（`\-A`） | `A` |

expression 可以直接讀這些值。AE 2025 的 JavaScript 引擎有 `JSON`：

```js
var p = thisLayer.marker.key(1).parameters;
JSON.parse(p.furi)[0][0];   // 第一個振假名
```

### 預設 Animator

每個有 marker 的圖層會加一個「ass2ae karaoke」Text Animator：

- **Fill Color**：已唱色。
- **Selector**：只有一個 Expression Selector，Based On＝Characters。
- **Amount expression**：照 SPEC。在 selector 裡可以直接用 `marker`。

### 自我檢查

JSX 結束前會逐層檢查以下三項，不符的都列入警告：

- marker 數量
- marker 時間是否嚴格遞增
- comment 串接後是否等於圖層文字

## 解析規則

- **處理哪些行**
  - 所有 Dialogue 行，但 Effect 為 `fx` 的跳過（templater 的產物）。
  - Comment 行中，Effect 為 `karaoke` 的也處理（templater 註解掉的原始行）。
- **切 `{…}` 區塊**：規則照 libass。
  - 沒有反斜線的 `{註解}` 直接忽略。
  - 沒有右括號的 `{` 當作一般文字。
  - `\t(...)` 裡的標籤不會被當成 `\k`。
- **切音節**：照 Aegisub 的 AssKaraoke。
  - `\k`、`\K`、`\kf`、`\ko` 各開一個新音節，單位是百分之一秒，可以有小數。
  - 缺值或負值當 0，並發出警告。
  - 同一個 `{}` 裡連續兩個 `\k` 時，前一個是空音節。
  - 第一個 `\k` 前的文字是長度 0 的音節。
  - 音節開始時間＝行開始＋前面所有 `\k` 的累加。
- **位置標籤**：`\pos`、`\an`（`\a`）各取第一次出現的值。不在第一個區塊時會警告。`\move` 不支援，會警告。
- **其他標籤**：從顯示文字中移除，並在報告中統計次數。`\kt` 會另外警告。
- **特殊字元**：照 libass 的 `ass_get_next_char`。
  - `\N` 轉成換行。
  - `\n` 在 WrapStyle 2 時換行，其他情況變成一個空白（VSFilter 是刪除）。WrapStyle 會被行內的 `\q` 覆寫。
  - `\h` 轉成 U+00A0。
  - `\{`、`\}` 是字面上的大括號。
  - Tab 轉成空白。
- **振假名**：照 karaskel-auto4.lua。
  - **基本寫法**：`顯示文字|振假名`，全形的 `｜` 也算。
  - **前綴**：振假名開頭的 `<`、`!`（含全形）是排版前綴，會剝掉並記成旗標。
  - **續音節**：去掉前後空白後以 `#` 或 `＃` 開頭的音節是續音節。
    - 它的時間併入前一個音節，振假名各自保留自己的時間。
    - 它本身的其他文字不顯示，這是 karaskel 的行為，會發出警告。
  - **行首的 `#`**：如果整行第一個音節就是 `#`，當作一般文字。
  - **inline-fx**：`\-X` 會一直沿用到下一個 `\-` 為止。出現在音節文字之後的 `\-` 屬於該音節。
- **長度 0 的音節**：有文字的話，文字併入下一個有長度的音節；如果是最後一個，就併入前一個。
- **沒有顯示文字的音節**：不建 marker，其他音節的時間不受影響。
- **超出行尾的音節**：截斷，並發出警告。
- **不變式**（測試會斷言）：音節文字依序串接等於行文字；marker 時間嚴格遞增；每個 marker 的 duration 都大於 0。
- **字元警告**：含 BMP 以外的字元、組合字元或異體字選擇符時會警告。

## 換行與 textIndex（`--newline-counts`）

實測 AE 25.3 的結果：

- **換行不計入 textIndex**。`"AB\rCD"` 的 `textIndex == 3` 是 C，`textTotal` 是 4。所以預設 `--newline-counts` 是關的。
- **腳本寫入的 `\n` 會被 AE 換成 `\r`**。

自己重測的方法（AE 改版時建議做一次）：

1. 新增文字層，內容打 `AB`、Enter、`CD`。
2. `Animate > Fill Color > RGB`，填色設成紅色。
3. 刪掉 Range Selector，改加 `Add > Selector > Expression`，Based On 設為 Characters。
4. Amount 填 `textIndex == 3 ? 100 : 0`：
   - C 變紅：換行不算字，用預設即可。
   - 都沒變紅：換行算一個字，請加 `--newline-counts`。
5. 也可以用 `textTotal == 5 ? 100 : 0` 交叉確認：全部變紅就代表換行有算進去。

## 時間

- **計算方式**：全程用 `fractions.Fraction`。marker 用精確秒數，不對齊影格。
- **AE 的 23.976**：AE 把 23.976 合成當成剛好 23.976 fps（`frameDuration` = 1/23.976），不是 24000/1001。
  - JSX 依合成自己的 `frameDuration` 設入出點（影格號由 Python 依 `--fps` 算好），所以一定落在 AE 的影格線上。
  - 與真正 24000/1001 的差距每格約 4×10⁻⁸ 秒，實務上沒有影響。
- **AE 的時間精度**：AE 以 1/(1000×fps) 秒為單位存時間（23.976 時約 0.04ms），marker 時間會被四捨五入到這個精度。

## 已知限制

- **emoji 等 BMP 以外的字元**：AE 算 1 個字，JS 的 `length` 是 2，comment.length 會對不上。會發出警告。
- **組合字元**：例如 か＋U+3099，AE 合起來算 1 個字，JS 算 2 個，同樣會對不上。會發出警告。
- **行內標籤**：`\fs`、`\c`、`\fn` 這類行內樣式不會套用到圖層，只會統計；`\move`、`\t`、`\fad`、`\clip` 等動畫標籤同樣不轉換。
- **水平對齊**：用的是字形外框，與 libass 用字寬（advance）算的框，左右可能差幾個像素。
- **字型 fallback**：template 模式時，範本字型缺字的部分由 AE 自動換字，此時讀到的字型（`TextDocument.font`）是第一個字實際用的字型。
- **ass 模式不轉換的樣式欄位**：陰影、底線、刪除線、不透明框（BorderStyle 3）。
- **這階段不做**：閃光層、特效 precomp、遮罩填色、振假名圖層、音節座標量測。資料已預留：`\k` 種類、振假名及其時間都存在 marker 參數裡。

## 開發

```bash
.venv\Scripts\python -m pytest              # 全部測試
set UPDATE_SNAPSHOTS=1 && .venv\Scripts\python -m pytest tests/test_jsxgen.py   # 更新快照
```

- `tests/fixtures/`：日文漢字＋假名、英文含空白、振假名與 `#`、跑過 templater 的檔案。
- `tests/test_parser.py`：如果存在 `ass_example/`，會對裡面的實際檔案檢查不變式。
- `tests/test_jsxgen.py`：JSX 快照測試（`tests/snapshots/`）。
- `tests/test_es3.py`：用 acorn（ecmaVersion 3）解析產出的 JSX，並擋掉 ES5 才有的 API。ExtendScript 沒有 `Array#indexOf`、`String#trim`、`JSON` 等。

### 在 AE 實測

先在 AE 開啟 `Preferences > Scripting & Expressions > Allow Scripts to Write Files and Access Network`，然後：

```bash
.venv\Scripts\python tools\ae\run_in_ae.py probe
```

```bash
.venv\Scripts\python tools\ae\run_in_ae.py fixtures
```

- **`probe`**：查證 API，結果寫到 `tools/ae/out/probe_api.json`，另外輸出一張判讀 textIndex 用的 `probe_textindex.png`。
- **`fixtures`**：把 fixtures（以及 `ass_example/` 裡的檔案）轉好，在 AE 各跑兩次。接著逐層比對以下項目：
  - 圖層名稱、comment、startTime、入出點
  - 文字、marker 時間、comment、參數
  - selector 與 expression 錯誤
  - 重跑安全
- **渲染圖**：fixtures 也會嘗試輸出 `<案例>_<n>.png`。但 `CompItem.saveFrameToPng` 是非同步的，用 `-r` 執行時不一定寫得出來，所以目視檢查請直接在 AE 開 `ass2ae_test_*` 合成。
- **注意**：AE 沒在執行時會被啟動（之後不會自動關閉）。腳本只會新增或刪除名稱以 `ass2ae_test_`、`ass2ae_probe` 開頭的合成，不會存檔或關閉專案。
