import glob
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

# ---------------------------------------------------------------------------
# Preferences persistence
# ---------------------------------------------------------------------------
PREFS_PATH = Path.home() / "Library" / "Application Support" / "Comic Enhancer" / "prefs.json"


def load_prefs() -> dict:
    try:
        if PREFS_PATH.exists():
            return json.loads(PREFS_PATH.read_text())
    except Exception:
        pass
    return {}


def save_prefs(data: dict) -> None:
    try:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Device presets
# ---------------------------------------------------------------------------
DEVICES = [
    {
        "label": "Kobo Libra Colour ⭐ — 1264×1680",
        "width": 1264, "height": 1680,
        "gamma": 1.20, "brightness": 105, "saturation": 170,
        "contrast": 3.5, "midpoint": 48,
        "unsharp": "0x0.9+0.9+0.005",
        "colorspace": "sRGB",
        "color": True,
    },
    {
        "label": "Kindle Colorsoft — 1272×1696",
        "width": 1272, "height": 1696,
        "gamma": 1.18, "brightness": 105, "saturation": 165,
        "contrast": 3.5, "midpoint": 48,
        "unsharp": "0x0.9+0.9+0.005",
        "colorspace": "sRGB",
        "color": True,
    },
    {
        "label": "Kindle Scribe — 1860×2480",
        "width": 1860, "height": 2480,
        "gamma": 1.10, "brightness": 100, "saturation": 100,
        "contrast": 3.5, "midpoint": 50,
        "unsharp": "0x1.0+1.0+0.005",
        "colorspace": "Gray",
        "color": False,
    },
    {
        "label": "reMarkable Paper Pro — 1620×2160",
        "width": 1620, "height": 2160,
        "gamma": 1.08, "brightness": 100, "saturation": 100,
        "contrast": 3.0, "midpoint": 50,
        "unsharp": "0x1.0+1.0+0.005",
        "colorspace": "Gray",
        "color": False,
    },
    {
        "label": "Kobo (greyscale) — 1072×1448",
        "width": 1072, "height": 1448,
        "gamma": 1.08, "brightness": 100, "saturation": 100,
        "contrast": 3.0, "midpoint": 50,
        "unsharp": "0x0.8+0.8+0.008",
        "colorspace": "Gray",
        "color": False,
    },
    {
        "label": "Kindle (greyscale) — 1264×1680",
        "width": 1264, "height": 1680,
        "gamma": 1.08, "brightness": 100, "saturation": 100,
        "contrast": 3.0, "midpoint": 50,
        "unsharp": "0x0.8+0.8+0.008",
        "colorspace": "Gray",
        "color": False,
    },
    {
        "label": "reMarkable 1/2 — 1404×1872",
        "width": 1404, "height": 1872,
        "gamma": 1.08, "brightness": 100, "saturation": 100,
        "contrast": 3.0, "midpoint": 50,
        "unsharp": "0x0.8+0.8+0.008",
        "colorspace": "Gray",
        "color": False,
    },
]

DEVICE_LABELS = [d["label"] for d in DEVICES]
DEFAULT_DEVICE_INDEX = 0


# ---------------------------------------------------------------------------
# Processing (runs in a background thread)
# ---------------------------------------------------------------------------
def process_files(input_dir, output_dir, preset, sliders, q):
    files = list(set(glob.glob(os.path.join(input_dir, "*.epub"))))
    files = [f for f in files if not os.path.basename(f).startswith("._")]

    if not files:
        q.put(("error", "No .epub or .kepub.epub files found in input folder.", ""))
        return

    total = len(files)
    width, height = preset["width"], preset["height"]
    colorspace = preset["colorspace"]
    unsharp = preset["unsharp"]

    gamma = sliders["gamma"]
    brightness = int(sliders["brightness"])
    saturation = int(sliders["saturation"])
    contrast = sliders["contrast"]
    midpoint = preset["midpoint"]
    sharpness = sliders["sharpness"]

    unsharp_parts = unsharp.split("+")
    unsharp_cmd = f"{unsharp_parts[0]}+{sharpness:.1f}+{unsharp_parts[2]}"

    for i, file_path in enumerate(files, 1):
        filename = os.path.basename(file_path)
        q.put((i, total, filename))

        temp_dir = tempfile.mkdtemp()
        try:
            subprocess.run(["unzip", "-q", file_path, "-d", temp_dir], check=True)

            img_files = []
            for root, _, fnames in os.walk(temp_dir):
                for f in fnames:
                    if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        img_files.append(os.path.join(root, f))

            if img_files:
                chunk_size = 100
                for c in range(0, len(img_files), chunk_size):
                    chunk = img_files[c: c + chunk_size]
                    cmd = [
                        "/opt/homebrew/bin/magick", "mogrify",
                        "-colorspace", colorspace,
                        "-resize", f"{width}x{height}>",
                        "-gamma", str(gamma),
                        "-modulate", f"{brightness},{saturation},100",
                        "-sigmoidal-contrast", f"{contrast}x{midpoint}%",
                        "-unsharp", unsharp_cmd,
                    ] + chunk
                    subprocess.run(cmd, check=True)

            out_path = os.path.join(output_dir, filename)
            if os.path.exists(out_path):
                os.remove(out_path)

            mimetype_file = os.path.join(temp_dir, "mimetype")
            if os.path.exists(mimetype_file):
                subprocess.run(
                    ["zip", "-q", "-X0", out_path, "mimetype"],
                    cwd=temp_dir, check=True
                )
                subprocess.run(
                    ["zip", "-q", "-rg", out_path, ".", "-x", "*.DS_Store", "mimetype"],
                    cwd=temp_dir, check=True
                )
            else:
                subprocess.run(
                    ["zip", "-q", "-r", out_path, ".", "-x", "*.DS_Store"],
                    cwd=temp_dir, check=True
                )

        except Exception as e:
            q.put(("error", f"Failed on {filename}: {e}", ""))
            return
        finally:
            shutil.rmtree(temp_dir)

    q.put(("done", total, ""))


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
F_TITLE   = ("Helvetica Neue", 22, "bold")
F_SECTION = ("Helvetica Neue", 10, "bold")
F_BODY    = ("Helvetica Neue", 13)
F_BOLD    = ("Helvetica Neue", 13, "bold")
F_SMALL   = ("Helvetica Neue", 11)
F_MONO    = ("Menlo", 11)

C_MUTED   = "#888888"
C_LABEL   = "#444444"
C_PATH    = "#999999"
C_SECTION = "#AAAAAA"


def _section_label(parent, text):
    """Small all-caps style section header."""
    ttk.Label(parent, text=text, font=F_SECTION, foreground=C_SECTION).pack(
        anchor="w", pady=(0, 6)
    )


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("InkReady")
        self.resizable(True, True)
        self.minsize(600, 0)
        self.geometry("720x720")
        self._prefs = load_prefs()
        self._build_ui()
        self._load_saved_state()

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=24, pady=20)

        # Header
        ttk.Label(outer, text="InkReady", font=F_TITLE).pack(anchor="w")
        ttk.Label(
            outer, text="Batch-optimize EPUBs for your e-reader",
            font=F_SMALL, foreground=C_MUTED
        ).pack(anchor="w", pady=(2, 16))

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=(0, 16))

        # Folders
        _section_label(outer, "FOLDERS")
        self._build_folder_row(outer, "Input",  "input")
        ttk.Frame(outer, height=8).pack()
        self._build_folder_row(outer, "Output", "output")

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=16)

        # Device
        _section_label(outer, "DEVICE")
        self.device_var = tk.StringVar(value=DEVICE_LABELS[DEFAULT_DEVICE_INDEX])
        device_combo = ttk.Combobox(
            outer, textvariable=self.device_var,
            values=DEVICE_LABELS, state="readonly", width=50,
        )
        device_combo.pack(anchor="w")
        device_combo.bind("<<ComboboxSelected>>", lambda _: self._on_device_change())

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=16)

        # Fine-tune sliders
        tune_header = ttk.Frame(outer)
        tune_header.pack(fill="x", pady=(0, 8))
        _section_label(tune_header, "FINE-TUNE")
        ttk.Button(tune_header, text="Reset", command=self._reset_sliders).pack(
            side="right", pady=(0, 6)
        )

        self._sliders = {}
        slider_defs = [
            ("gamma",      "Gamma",      0.80, 1.50, 0.01, ".2f"),
            ("brightness", "Brightness", 80,   130,  1,    "d"),
            ("saturation", "Saturation", 80,   220,  1,    "d"),
            ("contrast",   "Contrast",   1.0,  6.0,  0.1,  ".1f"),
            ("sharpness",  "Sharpness",  0.1,  2.0,  0.1,  ".1f"),
        ]
        slider_frame = ttk.Frame(outer)
        slider_frame.pack(fill="x")

        for row, (key, label, lo, hi, res, fmt) in enumerate(slider_defs):
            ttk.Label(
                slider_frame, text=label, font=F_BODY,
                foreground=C_LABEL, width=12, anchor="w"
            ).grid(row=row, column=0, padx=(0, 4), pady=4, sticky="w")

            var = tk.DoubleVar()
            val_label = ttk.Label(slider_frame, text="", font=F_BOLD, width=6, anchor="e")

            slider = ttk.Scale(
                slider_frame, from_=lo, to=hi, orient="horizontal",
                variable=var, length=300,
                command=lambda v, vl=val_label, f=fmt: vl.config(
                    text=f"%{f}" % float(v)
                ),
            )
            slider.grid(row=row, column=1, padx=4, pady=4)
            val_label.grid(row=row, column=2, padx=(4, 0))
            self._sliders[key] = (var, slider, val_label, fmt)

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=16)

        # Action: Process button + progress
        action = ttk.Frame(outer)
        action.pack(fill="x")

        self.process_btn = ttk.Button(
            action, text="▶  Process", command=self._start_processing,
        )
        self.process_btn.pack(side="left")

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            action, variable=self.progress_var,
            maximum=100, length=340, mode="determinate",
        )
        self.progress_bar.pack(side="left", padx=(14, 0))

        self.status_var = tk.StringVar(value="")
        ttk.Label(
            outer, textvariable=self.status_var,
            font=F_SMALL, foreground=C_MUTED, anchor="w",
        ).pack(fill="x", pady=(8, 0))

        # Apply device defaults and disable process btn until folders chosen
        self._on_device_change()
        self.process_btn.config(state="disabled")

    def _build_folder_row(self, parent, label, key):
        row = ttk.Frame(parent)
        row.pack(fill="x")

        ttk.Label(row, text=label, font=F_BODY, foreground=C_LABEL, width=8, anchor="w").pack(
            side="left"
        )

        info = ttk.Frame(row)
        info.pack(side="left", fill="x", expand=True, padx=(4, 12))

        name_var = tk.StringVar(value="No folder selected")
        path_var = tk.StringVar(value="")

        ttk.Label(info, textvariable=name_var, font=F_BOLD, anchor="w").pack(anchor="w")
        ttk.Label(info, textvariable=path_var, font=F_SMALL, foreground=C_PATH, anchor="w").pack(
            anchor="w"
        )

        if key == "input":
            self._input_name_var = name_var
            self._input_path_var = path_var
            self._input_dir = ""
            cmd = self._browse_input
        else:
            self._output_name_var = name_var
            self._output_path_var = path_var
            self._output_dir = ""
            cmd = self._browse_output

        ttk.Button(row, text="Choose…", command=cmd).pack(side="right")

    # ── State helpers ─────────────────────────────────────────────────────────

    def _set_input(self, path: str):
        self._input_dir = path
        self._input_name_var.set(os.path.basename(path) or path)
        self._input_path_var.set(path)

    def _set_output(self, path: str):
        self._output_dir = path
        self._output_name_var.set(os.path.basename(path) or path)
        self._output_path_var.set(path)

    def _load_saved_state(self):
        inp = self._prefs.get("input_dir", "")
        out = self._prefs.get("output_dir", "")
        dev = self._prefs.get("device", "")

        if inp and os.path.isdir(inp):
            self._set_input(inp)
        if out and os.path.isdir(out):
            self._set_output(out)
        if dev in DEVICE_LABELS:
            self._prefs_loading = True
            self.device_var.set(dev)
            self._on_device_change()
            self._prefs_loading = False

        self._update_process_btn()

    def _save_state(self):
        save_prefs({
            "input_dir":  self._input_dir,
            "output_dir": self._output_dir,
            "device":     self.device_var.get(),
        })

    # ── Device / slider helpers ───────────────────────────────────────────────

    def _current_preset(self):
        label = self.device_var.get()
        for d in DEVICES:
            if d["label"] == label:
                return d
        return DEVICES[DEFAULT_DEVICE_INDEX]

    def _on_device_change(self):
        preset = self._current_preset()
        self._apply_preset(preset)
        sat_slider = self._sliders["saturation"][1]
        if preset["color"]:
            sat_slider.state(["!disabled"])
        else:
            sat_slider.state(["disabled"])
        self._save_state()

    def _apply_preset(self, preset):
        defaults = {
            "gamma":      preset["gamma"],
            "brightness": preset["brightness"],
            "saturation": preset["saturation"],
            "contrast":   preset["contrast"],
            "sharpness":  float(preset["unsharp"].split("+")[1]),
        }
        fmts = {
            "gamma": ".2f", "brightness": "d",
            "saturation": "d", "contrast": ".1f", "sharpness": ".1f",
        }
        for key, (var, _, val_label, fmt) in self._sliders.items():
            var.set(defaults[key])
            val_label.config(text=f"%{fmt}" % defaults[key])

    def _reset_sliders(self):
        self._apply_preset(self._current_preset())

    # ── Folder browsing ───────────────────────────────────────────────────────

    def _browse_input(self):
        path = filedialog.askdirectory(title="Select input folder")
        if path:
            self._set_input(path)
            self._update_process_btn()
            self._save_state()

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self._set_output(path)
            self._update_process_btn()
            self._save_state()

    def _update_process_btn(self):
        if self._input_dir and self._output_dir:
            self.process_btn.config(state="normal")
        else:
            self.process_btn.config(state="disabled")

    # ── Processing ────────────────────────────────────────────────────────────

    def _start_processing(self):
        preset = self._current_preset()

        sliders = {
            "gamma":      round(self._sliders["gamma"][0].get(), 2),
            "brightness": round(self._sliders["brightness"][0].get()),
            "saturation": round(self._sliders["saturation"][0].get()),
            "contrast":   round(self._sliders["contrast"][0].get(), 1),
            "sharpness":  round(self._sliders["sharpness"][0].get(), 1),
        }

        self.process_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("Starting…")

        self._q = queue.Queue()
        thread = threading.Thread(
            target=process_files,
            args=(self._input_dir, self._output_dir, preset, sliders, self._q),
            daemon=True,
        )
        thread.start()
        self._poll_queue()

    def _poll_queue(self):
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]

                if kind == "done":
                    total = msg[1]
                    self.progress_var.set(100)
                    self.status_var.set(
                        f"Done — {total} file{'s' if total != 1 else ''} processed."
                    )
                    self.process_btn.config(state="normal")
                    return

                elif kind == "error":
                    self.status_var.set(f"Error: {msg[1]}")
                    self.process_btn.config(state="normal")
                    return

                else:
                    current, total, filename = msg
                    pct = (current - 1) / total * 100
                    self.progress_var.set(pct)
                    short = filename if len(filename) <= 44 else "…" + filename[-41:]
                    self.status_var.set(f"{current} of {total}  —  {short}")

        except queue.Empty:
            pass

        self.after(100, self._poll_queue)


if __name__ == "__main__":
    app = App()
    app.mainloop()
