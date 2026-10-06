# 任務：把 Aegisub 卡拉OK字幕（.ass 的 \k）轉成 After Effects 文字圖層＋音節 marker

## 目標
寫一個 Python 工具，讀入 .ass 後產生一支 .jsx。在 AE 執行這支 JSX 後：
- 每行歌詞變成一個文字圖層
- 每個音節變成該圖層上的一個 layer marker（時間＝音節開始、duration＝音節長度、comment＝音節文字）
之後的特效全部用 expression 讀這些 marker 來驅動，所以 marker 的正確性是第一優先。

## 我的環境
- After Effects 版本：2025
- 作業系統：Windows
- 素材：日文歌詞為主（漢字＋假名，可能有振假名），可能有中文翻譯行，影片多為 23.976 / 30.00 fps

## 架構
- Python 3.10+，依賴盡量只用 pysubs2、pytest（字級換算可選用 fontTools）
- CLI：python -m ass2ae input.ass -o out.jsx [選項]
- 資料用 json.dumps(..., ensure_ascii=True) 嵌進 JSX，當作物件字面量。這樣所有非 ASCII 字元都會變成 \uXXXX，可以避開 ExtendScript 的檔案編碼問題；JSX 也不需要讀外部檔或解析 JSON

## 解析規則
- 要處理的行：
  - 所有 Dialogue 行，但 Effect 欄為 fx 的跳過（那是 templater 的產物）
  - Comment 行中 Effect 為 karaoke 的也要處理（那是 templater 註解掉的原始行）
- --styles 可篩選樣式。沒有 \k 的行（例如翻譯行）照樣建立文字層，但不建 marker
- 用 {...} 切出 override block
- \k、\K、\kf、\ko 各開一個新音節。單位是百分之一秒，\K 等同 \kf
- 同一個 {} 裡連續兩個 \k 時，前一個就是空音節
- 第一個 \k 之前的文字，視為 duration 0 的音節
- 音節開始時間＝行開始時間＋前面所有 \k 值的累加
- 其他標籤（\pos、\c、\fad、\t…）從顯示文字中移除，統計後列在報告裡
- 第一個 block 的 \pos、\an 用來決定位置
- 沒有反斜線的 {註解} 直接忽略
- 特殊字元：\N → 換行；\h → U+00A0；\n 在 WrapStyle 2 時換行，其他情況比照 libass 處理（請查證）
- 振假名：
  - 音節文字含 | 時，| 前面是顯示文字、後面是振假名（存進資料，不顯示）
  - 顯示文字為 # 的續音節，時間併入前一個音節，振假名保留各自的時間
- duration 為 0 但有文字的音節：文字併入下一個音節（若是最後一個就併入前一個），避免同一時間點出現兩個 marker
- 沒有顯示文字的音節不建 marker（時間是絕對值，不影響後面的音節）
- 音節超出行結束時間時，截斷並發出警告
- 不變式（測試要斷言）：
  - 同一行的音節顯示文字依序串接後，等於該行的顯示文字
  - marker 時間嚴格遞增

## 時間
- 全程用 fractions.Fraction 計算
- --fps 預設 24000/1001；輸入 23.976 時自動對應到 24000/1001
- 圖層入點＝ceil(start×fps)/fps，出點＝ceil(end×fps)/fps，跟 libass「start ≤ t < end 才顯示」的規則一致
- marker 用精確秒數，不必對齊影格
- --offset：指定 ASS 的 0 秒對應到合成的哪個時間點

## AE 端（產生的 JSX）
- 語法必須是 ES3：
  - 不能用 let/const、箭頭函式、template literal、forEach/map、JSON 物件
  - 整支包在 IIFE 裡
  - 用 app.beginUndoGroup/endUndoGroup 包住，一次 Ctrl+Z 就能整批還原
- 目標合成：
  - 執行時若目前選中的是合成就用它（fps 不一致要警告）
  - 否則依參數新建合成，尺寸預設用 PlayRes，或由 --width/--height 指定
- 圖層：
  - 每行一個文字圖層，名稱格式為 KARA_0001_<前幾個字>
  - Layer.comment 寫入標記與行號
  - startTime 固定為 0，讓圖層時間＝合成時間（之後的 expression 依賴這點），只用 inPoint/outPoint 裁切
- 重跑安全：先刪掉上次產生的圖層（只認 comment 裡的標記），絕不動其他圖層
- 樣式（--style-mode）：
  - template（預設）：複製合成裡名為 KARA_TEMPLATE 的文字層，只改文字內容，字型、字級、顏色、描邊、段落設定都沿用，它的填色就當作未唱色。找不到這個圖層時，退回 ass 模式並警告
  - ass：從 ASS Style 映射，規則如下：
    - 顏色：SecondaryColour＝填色（未唱色），OutlineColour＝描邊。ASS 顏色格式是 &HAABBGGRR，alpha 00 為不透明
    - 描邊：寬度＝Outline×2，並設成填色在描邊上方
    - 字型：family 名要轉成 PostScript 名，用 app.fonts 查詢（方法名請查官方文件）；查不到就用 --font-map 對照表並警告
    - 字級：ASS 的 Fontsize 是行高（ascent+descent），AE 是 em。能讀到字型檔就用 fontTools 依 metrics 換算，否則用 --font-scale
- 位置：
  - 依 \an（或 Style 的 Alignment）、MarginL/R/V 或 \pos 決定，從 PlayRes 等比縮放到合成尺寸
  - 段落對齊照 alignment 設定，再用 sourceRectAtTime 量文字框、調整錨點，讓對齊點正確（例如 \an2 是底部置中）

## Marker 規格（最重要）
- 每個非空音節一個 layer marker：時間＝音節開始、duration＝音節長度、comment＝音節顯示文字
- comment 必須和圖層文字中對應的子字串完全一致（含空白），因為 expression 會用 comment.length 去對應 textIndex
- 其他資訊（\k 種類、原始 cs 值、振假名與其時間、行號）用 MarkerValue.setParameters() 儲存；如果這個 API 不可靠，改成輸出同名的 .kara.json
- 含 \N 的行：我不確定 AE 的 textIndex 會不會把換行算成一個字。請做成選項 --newline-counts（預設 false），並在 README 寫出實測方法
- 含 BMP 以外字元（emoji 等）的行要發出警告，因為 JS 的 length 和 AE 的字數可能對不上
- JSX 結尾要自我檢查：每層的 marker comment 串接後是否等於圖層文字，不符就列入警告；最後用 alert 顯示摘要（圖層數、marker 數、警告）

## 預設 Animator（--with-animator，預設開啟，用來驗證時間）
每個有 marker 的圖層加一個 Text Animator：
- Fill Color＝已唱色：用 --sung-color 指定，沒給就用 ASS 的 PrimaryColour
- selector 用 Expression Selector，Based On＝Characters
- Amount 用下面這段：

    var acc = 0, amt = 0;
    for (var k = 1; k <= marker.numKeys; k++) {
      var m = marker.key(k), n = m.comment.length;
      if (textIndex <= acc + n) {
        var s = m.time + m.duration * (textIndex - acc - 1) / n;
        amt = linear(time, s, s + m.duration / n, 0, 100);
        break;
      }
      acc += n;
    }
    amt;

注意事項：
- matchName 請查證後再用
- 用腳本新增的 Animator 會不會自帶 Range Selector，也請確認；最後要只有 Expression Selector 生效

## 測試
- pytest 要涵蓋：上面每條解析規則、23.976 fps 下的入出點（用 Fraction 比對）、不變式
- fixtures/ 放幾個小 .ass：
  - 日文漢字＋假名
  - 英文含空白
  - 含振假名與 #
  - 跑過 templater 的檔案
- JSX 產生器做快照測試
- 若有 node，用 acorn（ecmaVersion: 3）解析產出的 JSX，確保沒用到 ES3 以外的語法

## 這階段不要做
閃光層、特效 precomp 蓋章、像素級遮罩填色、振假名圖層、音節座標量測。
但資料結構要預留：\k 種類、振假名和它們的時間都要保存。

## 工作方式
1. 先讀完這份規格，回覆以下內容，等我確認再開始寫：
   - 實作計畫與檔案結構
   - 你不確定的 AE API 清單（matchName、app.fonts、setParameters、textIndex 與換行…）
   - 打算怎麼驗證
2. 先完成並測好 Python 解析，再寫 JSX 產生器
3. 如果這台電腦裝有 AE，可以用 AfterFX.exe -r（Windows）或 osascript 的 DoScriptFile（macOS）實際跑 fixtures 驗證；不行的話，把需要我在 AE 實測的步驟列成清單
4. README 要寫清楚：安裝方式、CLI 選項、在 AE 執行的方法、已知限制