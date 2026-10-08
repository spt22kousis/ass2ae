"""Windows GUI: pick an .ass file and a video, get an After Effects project.

    python -m ass2ae.gui
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
import traceback
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__, project
from .cli import read_font_map
from .fonts import build_index
from .jsxgen import Options
from .layout import get_style, parse_color
from .parser import load, select_reason
from .timing import parse_offset

DEFAULT_SUNG = "#0076FF"
FONT = ("Microsoft JhengHei UI", 10)


def _hex(c) -> str:
    return f"#{c.r:02X}{c.g:02X}{c.b:02X}"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"ass2ae {__version__} － 卡拉OK字幕轉 After Effects 專案")
        self.option_add("*Font", FONT)
        try:
            ttk.Style(self).theme_use("vista")
        except tk.TclError:
            pass
        self.minsize(720, 560)

        self.ass = tk.StringVar()
        self.video = tk.StringVar()
        self.aep = tk.StringVar()
        self.sung = tk.StringVar(value=DEFAULT_SUNG)
        self.use_style_colour = tk.BooleanVar(value=False)
        self.furigana = tk.BooleanVar(value=True)
        self.animator = tk.BooleanVar(value=True)
        self.offset = tk.StringVar(value="0")
        self.font_map = tk.StringVar()
        self.font_scale = tk.StringVar(value="0.7")
        self.afterfx = tk.StringVar()
        self.style_vars: dict[str, tk.BooleanVar] = {}
        self.aep_edited = False
        self.events: queue.Queue = queue.Queue()
        self.running = False

        self._build()
        found = project.find_afterfx()
        self.afterfx_box["values"] = [str(p) for p in found]
        if found:
            self.afterfx.set(str(found[0]))
        self.after(100, self._pump)

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(root, text="ASS 字幕檔").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(root, textvariable=self.ass).grid(row=r, column=1, sticky="ew", padx=6)
        ttk.Button(root, text="選擇…", command=self._pick_ass).grid(row=r, column=2)
        r += 1
        ttk.Label(root, text="影片").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(root, textvariable=self.video).grid(row=r, column=1, sticky="ew", padx=6)
        ttk.Button(root, text="選擇…", command=self._pick_video).grid(row=r, column=2)
        r += 1
        ttk.Label(root, text="輸出專案 (.aep)").grid(row=r, column=0, sticky="w", pady=4)
        aep_entry = ttk.Entry(root, textvariable=self.aep)
        aep_entry.grid(row=r, column=1, sticky="ew", padx=6)
        aep_entry.bind("<Key>", lambda _e: setattr(self, "aep_edited", True))
        ttk.Button(root, text="另存為…", command=self._pick_aep).grid(row=r, column=2)

        r += 1
        colour = ttk.Frame(root)
        colour.grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 4))
        ttk.Label(colour, text="唱到時的顏色").pack(side="left")
        self.swatch = tk.Label(colour, width=4, relief="solid", borderwidth=1, background=self.sung.get(),
                               cursor="hand2")
        self.swatch.pack(side="left", padx=8)
        self.swatch.bind("<Button-1>", lambda _e: self._pick_colour())
        ttk.Button(colour, text="選顏色…", command=self._pick_colour).pack(side="left")
        ttk.Checkbutton(colour, text="改用字幕樣式裡的顏色 (PrimaryColour)", variable=self.use_style_colour,
                        command=self._sync_swatch).pack(side="left", padx=12)

        r += 1
        ttk.Checkbutton(root, text="加上振假名（標音），需要字幕裡有「漢字|かな」的寫法",
                        variable=self.furigana).grid(row=r, column=0, columnspan=3, sticky="w", pady=4)

        r += 1
        self.adv_button = ttk.Button(root, text="▸ 進階設定", command=self._toggle_advanced)
        self.adv_button.grid(row=r, column=0, sticky="w", pady=(8, 0))
        r += 1
        self.adv = ttk.Frame(root, padding=(16, 6, 0, 0))
        self.adv.grid(row=r, column=0, columnspan=3, sticky="ew")
        self.adv.columnconfigure(1, weight=1)
        self._build_advanced(self.adv)
        self.adv.grid_remove()

        r += 1
        run = ttk.Frame(root)
        run.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(14, 6))
        run.columnconfigure(1, weight=1)
        self.run_button = ttk.Button(run, text="產生 AE 專案", command=self._start)
        self.run_button.grid(row=0, column=0, ipadx=12, ipady=4)
        self.progress = ttk.Progressbar(run, mode="determinate", value=0)
        self.progress.grid(row=0, column=1, sticky="ew", padx=10)
        self.status = ttk.Label(root, text="選好 ASS 字幕檔和影片後，按「產生 AE 專案」。")
        r += 1
        self.status.grid(row=r, column=0, columnspan=3, sticky="w")
        r += 1
        self.log = ScrolledText(root, height=12, wrap="word", state="disabled")
        self.log.grid(row=r, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        root.rowconfigure(r, weight=1)

    def _build_advanced(self, f: ttk.Frame) -> None:
        r = 0
        ttk.Label(f, text="要轉換的樣式").grid(row=r, column=0, sticky="nw", pady=4)
        self.styles_frame = ttk.Frame(f)
        self.styles_frame.grid(row=r, column=1, columnspan=2, sticky="w")
        ttk.Label(self.styles_frame, text="（選擇字幕檔後顯示）").pack(side="left")
        r += 1
        ttk.Label(f, text="時間偏移（秒）").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.offset, width=10).grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        ttk.Checkbutton(f, text="加上依 marker 變色的效果（Text Animator）",
                        variable=self.animator).grid(row=r, column=0, columnspan=3, sticky="w", pady=4)
        r += 1
        ttk.Label(f, text="字型對照表（選填）").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.font_map).grid(row=r, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="選擇…", command=self._pick_font_map).grid(row=r, column=2)
        r += 1
        ttk.Label(f, text="找不到字型檔時的大小比例").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Spinbox(f, textvariable=self.font_scale, from_=0.3, to=1.5, increment=0.05,
                    width=8).grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        ttk.Label(f, text="After Effects 位置").grid(row=r, column=0, sticky="w", pady=4)
        self.afterfx_box = ttk.Combobox(f, textvariable=self.afterfx)
        self.afterfx_box.grid(row=r, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="選擇…", command=self._pick_afterfx).grid(row=r, column=2)

    # ----------------------------------------------------------------- pickers

    def _pick_ass(self) -> None:
        path = filedialog.askopenfilename(title="選擇 ASS 字幕檔", filetypes=[("ASS 字幕", "*.ass"), ("所有檔案", "*.*")])
        if path:
            self.ass.set(path)
            self._load_styles(Path(path))
            self._suggest_aep()

    def _pick_video(self) -> None:
        path = filedialog.askopenfilename(
            title="選擇影片",
            filetypes=[("影片", "*.mp4 *.mov *.mkv *.avi *.m4v *.mxf *.webm"), ("所有檔案", "*.*")])
        if path:
            self.video.set(path)
            self._suggest_aep()

    def _pick_aep(self) -> None:
        start = Path(self.aep.get() or self.video.get() or ".")
        path = filedialog.asksaveasfilename(title="儲存 AE 專案", defaultextension=".aep",
                                            initialdir=str(start.parent), initialfile=start.name if start.suffix else "",
                                            filetypes=[("After Effects 專案", "*.aep")])
        if path:
            self.aep.set(path)
            self.aep_edited = True

    def _pick_font_map(self) -> None:
        path = filedialog.askopenfilename(title="選擇字型對照表", filetypes=[("JSON / 文字", "*.json *.txt"), ("所有檔案", "*.*")])
        if path:
            self.font_map.set(path)

    def _pick_afterfx(self) -> None:
        path = filedialog.askopenfilename(title="選擇 AfterFX.exe", filetypes=[("AfterFX.exe", "AfterFX.exe")])
        if path:
            self.afterfx.set(path)

    def _pick_colour(self) -> None:
        _rgb, hexa = colorchooser.askcolor(color=self.sung.get(), title="唱到時的顏色")
        if hexa:
            self.sung.set(hexa.upper())
            self.use_style_colour.set(False)
            self._sync_swatch()

    def _sync_swatch(self) -> None:
        self.swatch.configure(background="#DDDDDD" if self.use_style_colour.get() else self.sung.get())

    def _toggle_advanced(self) -> None:
        if self.adv.winfo_ismapped():
            self.adv.grid_remove()
            self.adv_button.configure(text="▸ 進階設定")
        else:
            self.adv.grid()
            self.adv_button.configure(text="▾ 進階設定")

    def _suggest_aep(self) -> None:
        if self.aep_edited or not self.ass.get():
            return
        folder = Path(self.video.get()).parent if self.video.get() else Path(self.ass.get()).parent
        self.aep.set(str(folder / (Path(self.ass.get()).stem + ".aep")))

    def _load_styles(self, path: Path) -> None:
        for w in self.styles_frame.winfo_children():
            w.destroy()
        self.style_vars = {}
        try:
            subs = load(str(path))
        except Exception as e:  # noqa: BLE001 - show any parse problem to the user
            ttk.Label(self.styles_frame, text=f"無法讀取：{e}").pack(side="left")
            return
        counts = Counter(ev.style for ev in subs.events if select_reason(ev) is None)
        for name, n in counts.items():
            var = tk.BooleanVar(value=True)
            self.style_vars[name] = var
            ttk.Checkbutton(self.styles_frame, text=f"{name}（{n} 行）", variable=var).pack(side="left", padx=(0, 10))
        if not counts:
            ttk.Label(self.styles_frame, text="這個檔案裡沒有可轉換的行").pack(side="left")
        # karaoke styles whose sung and unsung colours are the same would show no colour change
        styles = [get_style(subs, s) for s in counts]
        if styles and all(st.primarycolor == st.secondarycolor for st in styles):
            self.use_style_colour.set(False)
        elif styles:
            self.use_style_colour.set(True)
            self.sung.set(_hex(styles[0].primarycolor))
        self._sync_swatch()
        self._say(f"已讀取 {path.name}：{sum(counts.values())} 行可轉換。")

    # --------------------------------------------------------------------- run

    def _say(self, text: str) -> None:
        self.status.configure(text=text)

    def _write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _options(self) -> tuple[Options, list[str] | None]:
        opts = Options(
            style_mode="ass",
            with_animator=self.animator.get(),
            sung_color=None if self.use_style_colour.get() else parse_color(self.sung.get()),
            font_scale=float(self.font_scale.get()),
            font_map=read_font_map(self.font_map.get()) if self.font_map.get().strip() else {},
            furigana=self.furigana.get(),
        )
        opts.offset = parse_offset(self.offset.get() or "0", opts.fps)
        chosen = [name for name, var in self.style_vars.items() if var.get()]
        styles = chosen if self.style_vars and len(chosen) < len(self.style_vars) else None
        return opts, styles

    def _start(self) -> None:
        if self.running:
            return
        ass, video, aep, exe = (Path(self.ass.get().strip()), Path(self.video.get().strip()),
                                self.aep.get().strip(), self.afterfx.get().strip())
        if not ass.is_file():
            messagebox.showwarning("ass2ae", "請先選擇 ASS 字幕檔。")
            return
        if not video.is_file():
            messagebox.showwarning("ass2ae", "請先選擇影片。")
            return
        if not aep:
            messagebox.showwarning("ass2ae", "請指定輸出專案的位置。")
            return
        if not exe or not Path(exe).is_file():
            messagebox.showwarning("ass2ae", "找不到 After Effects。請在「進階設定」指定 AfterFX.exe 的位置。")
            return
        if self.style_vars and not any(v.get() for v in self.style_vars.values()):
            messagebox.showwarning("ass2ae", "請至少勾選一個樣式。")
            return
        try:
            opts, styles = self._options()
        except (ValueError, OSError) as e:
            messagebox.showwarning("ass2ae", f"設定有誤：{e}")
            return
        if project.afterfx_running() and not messagebox.askokcancel(
                "ass2ae", "After Effects 已經開著。\n\n接下來會在 AE 裡開一個新專案；如果目前的專案有未存的變更，"
                          "AE 會先問你要不要存檔。\n\n要繼續嗎？"):
            return
        self.running = True
        self.run_button.state(["disabled"])
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        threading.Thread(target=self._work, args=(ass, video, Path(aep), exe, opts, styles), daemon=True).start()

    def _work(self, ass, video, aep, exe, opts, styles) -> None:
        post = self.events.put
        try:
            post(("status", "正在尋找字型…"))
            fonts = build_index()
            post(("status", "正在轉換字幕…"))
            job = project.prepare(ass, video, aep, opts, styles, fonts)
            lines = job.data["lines"]
            post(("log", f"字幕：{len(lines)} 行、{sum(len(l['markers']) for l in lines)} 個音節、"
                         f"{sum(len(l['furi']) for l in lines)} 組振假名"))
            for name, st in job.data["styles"].items():
                ps = st["fonts"][0]["ps"] if st["fonts"] else "（AE 會再找一次）"
                post(("log", f"樣式 {name}：字型 {st['family']} → {ps}"))
            post(("status", "正在啟動 After Effects…（如果 AE 跳出詢問視窗，請先回答；之後處理中請不要操作 AE）"))
            project.launch(job, exe)
            res = project.wait(job, on_tick=lambda s: post(
                ("status", f"After Effects 處理中…已經過 {int(s) // 60} 分 {int(s) % 60:02d} 秒")))
            post(("done", res, job))
        except Exception as e:  # noqa: BLE001 - report everything to the user
            logging.exception("build failed")
            post(("error", f"{e}\n\n{traceback.format_exc()}"))

    def _pump(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "status":
                    self._say(ev[1])
                elif kind == "log":
                    self._write(ev[1])
                elif kind == "done":
                    self._finish(ev[1], ev[2])
                elif kind == "error":
                    self._finish_error(ev[1])
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _stop(self) -> None:
        self.running = False
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.run_button.state(["!disabled"])

    def _finish(self, res: project.BuildResult, job: project.Job) -> None:
        self._stop()
        if not res.ok:
            self._say("失敗了。")
            self._write(f"\n錯誤（{res.stage}）：{res.error}")
            messagebox.showerror("ass2ae", f"沒有完成：{res.error}")
            return
        self._say(f"完成！已存成 {job.aep}")
        if res.summary:
            s = res.summary
            self._write(f"\n完成：{s.get('layers')} 個歌詞圖層、{s.get('furigana')} 個振假名圖層、"
                        f"{s.get('markers')} 個 marker。")
        if res.video:
            v = res.video
            self._write(f"影片：{v.get('width')}×{v.get('height')}，{v.get('fps'):.3f} fps")
        if not res.status_written:
            self._write("（AE 不允許腳本寫檔，詳細結果顯示在 AE 的對話框裡）")
        if res.warnings:
            self._write(f"\n注意事項（{len(res.warnings)}）：")
            for w in res.warnings:
                self._write(f"・{w}")
        self._write(f"\n專案已在 After Effects 開啟：{job.aep}")

    def _finish_error(self, text: str) -> None:
        self._stop()
        self._say("發生錯誤。")
        self._write(text)
        messagebox.showerror("ass2ae", text.split("\n")[0])


def main() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001 - older Windows
            pass
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    App().mainloop()


if __name__ == "__main__":
    main()
