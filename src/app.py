import glob
import json
import math
import os
import platform
import queue
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path
from tkinter import filedialog, ttk
import tkinter as tk
from PIL import Image, ImageEnhance, ImageFilter

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_SYSTEM = platform.system()  # "Darwin", "Windows", "Linux"


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------
def _prefs_path() -> Path:
    if _SYSTEM == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "InkReady"
    elif _SYSTEM == "Windows":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "InkReady"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = (Path(xdg) if xdg else Path.home() / ".config") / "InkReady"
    return base / "prefs.json"


PREFS_PATH = _prefs_path()


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
# Platform fonts — each OS has its own system font stack
# ---------------------------------------------------------------------------
if _SYSTEM == "Darwin":
    F_TITLE   = ("Helvetica Neue", 22, "bold")
    F_SECTION = ("Helvetica Neue", 10, "bold")
    F_BODY    = ("Helvetica Neue", 13)
    F_BOLD    = ("Helvetica Neue", 13, "bold")
    F_SMALL   = ("Helvetica Neue", 11)
elif _SYSTEM == "Windows":
    F_TITLE   = ("Segoe UI", 22, "bold")
    F_SECTION = ("Segoe UI", 10, "bold")
    F_BODY    = ("Segoe UI", 13)
    F_BOLD    = ("Segoe UI", 13, "bold")
    F_SMALL   = ("Segoe UI", 11)
else:  # Linux + others
    F_TITLE   = ("Sans", 22, "bold")
    F_SECTION = ("Sans", 10, "bold")
    F_BODY    = ("Sans", 13)
    F_BOLD    = ("Sans", 13, "bold")
    F_SMALL   = ("Sans", 11)

C_MUTED   = "#888888"
C_LABEL   = "#444444"
C_PATH    = "#999999"
C_SECTION = "#AAAAAA"


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
        "color": True,
    },
    {
        "label": "Kindle Colorsoft — 1272×1696",
        "width": 1272, "height": 1696,
        "gamma": 1.18, "brightness": 105, "saturation": 165,
        "contrast": 3.5, "midpoint": 48,
        "unsharp": "0x0.9+0.9+0.005",
        "color": True,
    },
    {
        "label": "Kindle Scribe — 1860×2480",
        "width": 1860, "height": 2480,
        "gamma": 1.10, "brightness": 100, "saturation": 100,
        "contrast": 3.5, "midpoint": 50,
        "unsharp": "0x1.0+1.0+0.005",
        "color": False,
    },
    {
        "label": "reMarkable Paper Pro — 1620×2160",
        "width": 1620, "height": 2160,
        "gamma": 1.08, "brightness": 100, "saturation": 100,
        "contrast": 3.0, "midpoint": 50,
        "unsharp": "0x1.0+1.0+0.005",
        "color": False,
    },
    {
        "label": "Kobo (greyscale) — 1072×1448",
        "width": 1072, "height": 1448,
        "gamma": 1.08, "brightness": 100, "saturation": 100,
        "contrast": 3.0, "midpoint": 50,
        "unsharp": "0x0.8+0.8+0.008",
        "color": False,
    },
    {
        "label": "Kindle (greyscale) — 1264×1680",
        "width": 1264, "height": 1680,
        "gamma": 1.08, "brightness": 100, "saturation": 100,
        "contrast": 3.0, "midpoint": 50,
        "unsharp": "0x0.8+0.8+0.008",
        "color": False,
    },
    {
        "label": "reMarkable 1/2 — 1404×1872",
        "width": 1404, "height": 1872,
        "gamma": 1.08, "brightness": 100, "saturation": 100,
        "contrast": 3.0, "midpoint": 50,
        "unsharp": "0x0.8+0.8+0.008",
        "color": False,
    },
]

DEVICE_LABELS = [d["label"] for d in DEVICES]
DEFAULT_DEVICE_INDEX = 0


# ---------------------------------------------------------------------------
# Image processing (Pillow — no ImageMagick dependency)
# ---------------------------------------------------------------------------
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _gamma_lut(gamma: float) -> list:
    """
    256-entry gamma correction table.
    output = (input / 255) ^ (1 / gamma) * 255
    gamma > 1 lifts midtones (brightens without blowing highlights).
    """
    inv = 1.0 / gamma
    return [int(((i / 255.0) ** inv) * 255 + 0.5) for i in range(256)]


def _sigmoidal_lut(contrast: float, midpoint_pct: float) -> list:
    """
    256-entry sigmoidal S-curve table matching ImageMagick's -sigmoidal-contrast.

    The sigmoid function maps each pixel through an S-curve:
      sig(x) = 1 / (1 + exp(-C * (x - M)))
    where C = contrast strength and M = pivot point (midpoint_pct / 100).

    The output is then normalized so black stays black and white stays white.
    Effect: midtone contrast is boosted while highlights and shadows are
    gently compressed — punchy contrast without clipping.
    """
    M = midpoint_pct / 100.0
    C = contrast

    def sig(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-C * (x - M)))

    s0, s1 = sig(0.0), sig(1.0)
    span = s1 - s0
    result = []
    for i in range(256):
        v = (sig(i / 255.0) - s0) / span
        result.append(int(max(0.0, min(1.0, v)) * 255 + 0.5))
    return result


def _process_image(img_path: str, preset: dict, sliders: dict) -> None:
    """Apply all adjustments to one image file, save back in-place."""
    try:
        img = Image.open(img_path)
    except Exception:
        return  # skip unreadable/corrupt files

    target_mode = "RGB" if preset["color"] else "L"

    # 1. Colorspace — flatten any alpha channel onto a white background first
    if img.mode in ("RGBA", "LA"):
        bg = Image.new(target_mode, img.size, 255)
        bg.paste(img.convert(target_mode), mask=img.split()[-1])
        img = bg
    elif img.mode != target_mode:
        img = img.convert(target_mode)

    n_bands = len(img.getbands())  # 3 for RGB, 1 for L

    # 2. Resize — thumbnail only shrinks, never upscales, preserves aspect ratio
    img.thumbnail((preset["width"], preset["height"]), Image.LANCZOS)

    # 3. Gamma
    g_lut = _gamma_lut(sliders["gamma"])
    img = img.point(g_lut * n_bands)

    # 4. Brightness
    img = ImageEnhance.Brightness(img).enhance(sliders["brightness"] / 100.0)

    # 5. Saturation (colour devices only; ImageEnhance.Color: 0=grey, 1=original, >1=vivid)
    if preset["color"] and sliders["saturation"] != 100:
        img = ImageEnhance.Color(img).enhance(sliders["saturation"] / 100.0)

    # 6. Sigmoidal contrast
    s_lut = _sigmoidal_lut(sliders["contrast"], preset["midpoint"])
    img = img.point(s_lut * n_bands)

    # 7. Unsharp mask
    # preset["unsharp"] format: "{radius}x{sigma}+{amount}+{threshold}"
    # e.g. "0x0.9+0.9+0.005" → sigma=0.9, threshold=0.005*255≈1
    # The user's sharpness slider overrides the amount component.
    unsharp_parts = preset["unsharp"].split("+")
    sigma  = float(unsharp_parts[0].split("x")[1])
    thresh = int(float(unsharp_parts[2]) * 255)
    img = img.filter(ImageFilter.UnsharpMask(
        radius=sigma,
        percent=int(sliders["sharpness"] * 100),
        threshold=thresh,
    ))

    # Save back in the original format
    ext = os.path.splitext(img_path)[1].lower().lstrip(".")
    fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}.get(ext, "JPEG")
    save_kwargs: dict = {"format": fmt}
    if fmt == "JPEG":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        save_kwargs["quality"] = 92
        save_kwargs["subsampling"] = 0
    elif fmt == "WEBP":
        save_kwargs["quality"] = 90
    img.save(img_path, **save_kwargs)


# ---------------------------------------------------------------------------
# EPUB archive helpers
# ---------------------------------------------------------------------------
def _unpack_epub(epub_path: str, temp_dir: str) -> None:
    with zipfile.ZipFile(epub_path, "r") as zf:
        zf.extractall(temp_dir)


def _repack_epub(temp_dir: str, out_path: str) -> None:
    """
    Repack temp_dir as a valid EPUB ZIP archive.

    EPUB spec requirement: the 'mimetype' file must be the very first entry
    in the archive and must be stored without compression (ZIP_STORED).
    This allows readers to identify the file type by peeking at a fixed byte
    offset without decompressing anything.

    Everything else is written with ZIP_DEFLATED for compression.
    """
    if os.path.exists(out_path):
        os.remove(out_path)

    with zipfile.ZipFile(out_path, "w") as zout:
        # Write mimetype first, uncompressed
        mimetype_src = os.path.join(temp_dir, "mimetype")
        if os.path.exists(mimetype_src):
            zout.write(mimetype_src, "mimetype", compress_type=zipfile.ZIP_STORED)

        for root, dirs, filenames in os.walk(temp_dir):
            dirs.sort()
            for fname in sorted(filenames):
                if fname in (".DS_Store", "Thumbs.db"):
                    continue
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, temp_dir).replace(os.sep, "/")
                if arcname == "mimetype":
                    continue  # already written above
                zout.write(fpath, arcname, compress_type=zipfile.ZIP_DEFLATED)


# ---------------------------------------------------------------------------
# Processing worker — runs in a background thread so the GUI stays responsive
# ---------------------------------------------------------------------------
def process_files(
    input_dir: str,
    output_dir: str,
    preset: dict,
    sliders: dict,
    q: queue.Queue,
) -> None:
    files = list(set(glob.glob(os.path.join(input_dir, "*.epub"))))
    files = [f for f in files if not os.path.basename(f).startswith("._")]

    if not files:
        q.put(("error", "No .epub or .kepub.epub files found in input folder.", ""))
        return

    total = len(files)

    for i, file_path in enumerate(files, 1):
        filename = os.path.basename(file_path)

        temp_dir = tempfile.mkdtemp()
        try:
            # 1. Unpack the EPUB/KEPUB archive
            _unpack_epub(file_path, temp_dir)

            # 2. Find all image files inside the archive
            img_files = []
            for root, _, fnames in os.walk(temp_dir):
                for f in fnames:
                    if os.path.splitext(f)[1].lower() in _IMAGE_EXTS:
                        img_files.append(os.path.join(root, f))

            # 3. Process each image, sending per-image progress updates
            n_imgs = len(img_files)
            for j, img_path in enumerate(img_files, 1):
                _process_image(img_path, preset, sliders)
                q.put(("progress", i, total, filename, j, n_imgs))

            # 4. Repack and write to output directory
            out_path = os.path.join(output_dir, filename)
            _repack_epub(temp_dir, out_path)

        except Exception as e:
            q.put(("error", f"Failed on {filename}: {e}", ""))
            return
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    q.put(("done", total, ""))


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
def _section_label(parent, text: str) -> None:
    ttk.Label(parent, text=text, font=F_SECTION, foreground=C_SECTION).pack(
        anchor="w", pady=(0, 6)
    )


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("InkReady")
        self.resizable(True, True)
        self.minsize(600, 0)
        self.geometry("720x700")
        self._prefs = load_prefs()
        self._build_ui()
        self._load_saved_state()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=24, pady=20)

        ttk.Label(outer, text="InkReady", font=F_TITLE).pack(anchor="w")
        ttk.Label(
            outer,
            text="Batch-optimize EPUBs for your e-reader",
            font=F_SMALL,
            foreground=C_MUTED,
        ).pack(anchor="w", pady=(2, 16))

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=(0, 16))

        _section_label(outer, "FOLDERS")
        self._build_folder_row(outer, "Input",  "input")
        ttk.Frame(outer, height=8).pack()
        self._build_folder_row(outer, "Output", "output")

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=16)

        _section_label(outer, "DEVICE")
        self.device_var = tk.StringVar(value=DEVICE_LABELS[DEFAULT_DEVICE_INDEX])
        device_combo = ttk.Combobox(
            outer,
            textvariable=self.device_var,
            values=DEVICE_LABELS,
            state="readonly",
            width=50,
        )
        device_combo.pack(anchor="w")
        device_combo.bind("<<ComboboxSelected>>", lambda _: self._on_device_change())

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=16)

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
                slider_frame,
                text=label,
                font=F_BODY,
                foreground=C_LABEL,
                width=12,
                anchor="w",
            ).grid(row=row, column=0, padx=(0, 4), pady=4, sticky="w")

            var = tk.DoubleVar()
            val_label = ttk.Label(slider_frame, text="", font=F_BOLD, width=6, anchor="e")

            slider = ttk.Scale(
                slider_frame,
                from_=lo,
                to=hi,
                orient="horizontal",
                variable=var,
                length=300,
                command=lambda v, vl=val_label, f=fmt: vl.config(
                    text=f"%{f}" % float(v)
                ),
            )
            slider.grid(row=row, column=1, padx=4, pady=4)
            val_label.grid(row=row, column=2, padx=(4, 0))
            self._sliders[key] = (var, slider, val_label, fmt)

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=16)

        action = ttk.Frame(outer)
        action.pack(fill="x")

        self.process_btn = ttk.Button(
            action, text="▶  Process", command=self._start_processing,
        )
        self.process_btn.pack(side="left")

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            action,
            variable=self.progress_var,
            maximum=100,
            length=340,
            mode="determinate",
        )
        self.progress_bar.pack(side="left", padx=(14, 0))

        self.status_var = tk.StringVar(value="")
        ttk.Label(
            outer,
            textvariable=self.status_var,
            font=F_SMALL,
            foreground=C_MUTED,
            anchor="w",
        ).pack(fill="x", pady=(8, 0))

        self._on_device_change()
        self.process_btn.config(state="disabled")

    def _build_folder_row(self, parent, label: str, key: str) -> None:
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
            self._input_name_var  = name_var
            self._input_path_var  = path_var
            self._input_dir       = ""
            cmd = self._browse_input
        else:
            self._output_name_var = name_var
            self._output_path_var = path_var
            self._output_dir      = ""
            cmd = self._browse_output

        ttk.Button(row, text="Choose…", command=cmd).pack(side="right")

    # ── State helpers ─────────────────────────────────────────────────────────

    def _set_input(self, path: str) -> None:
        self._input_dir = path
        self._input_name_var.set(os.path.basename(path) or path)
        self._input_path_var.set(path)

    def _set_output(self, path: str) -> None:
        self._output_dir = path
        self._output_name_var.set(os.path.basename(path) or path)
        self._output_path_var.set(path)

    def _load_saved_state(self) -> None:
        inp = self._prefs.get("input_dir", "")
        out = self._prefs.get("output_dir", "")
        dev = self._prefs.get("device", "")

        if inp and os.path.isdir(inp):
            self._set_input(inp)
        if out and os.path.isdir(out):
            self._set_output(out)
        if dev in DEVICE_LABELS:
            self.device_var.set(dev)
            self._on_device_change()

        self._update_process_btn()

    def _save_state(self) -> None:
        save_prefs({
            "input_dir":  self._input_dir,
            "output_dir": self._output_dir,
            "device":     self.device_var.get(),
        })

    # ── Device / slider helpers ───────────────────────────────────────────────

    def _current_preset(self) -> dict:
        label = self.device_var.get()
        for d in DEVICES:
            if d["label"] == label:
                return d
        return DEVICES[DEFAULT_DEVICE_INDEX]

    def _on_device_change(self) -> None:
        preset = self._current_preset()
        self._apply_preset(preset)
        sat_slider = self._sliders["saturation"][1]
        if preset["color"]:
            sat_slider.state(["!disabled"])
        else:
            sat_slider.state(["disabled"])
        self._save_state()

    def _apply_preset(self, preset: dict) -> None:
        defaults = {
            "gamma":      preset["gamma"],
            "brightness": preset["brightness"],
            "saturation": preset["saturation"],
            "contrast":   preset["contrast"],
            "sharpness":  float(preset["unsharp"].split("+")[1]),
        }
        for key, (var, _, val_label, fmt) in self._sliders.items():
            var.set(defaults[key])
            val_label.config(text=f"%{fmt}" % defaults[key])

    def _reset_sliders(self) -> None:
        self._apply_preset(self._current_preset())

    # ── Folder browsing ───────────────────────────────────────────────────────

    def _browse_input(self) -> None:
        path = filedialog.askdirectory(title="Select input folder")
        if path:
            self._set_input(path)
            self._update_process_btn()
            self._save_state()

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self._set_output(path)
            self._update_process_btn()
            self._save_state()

    def _update_process_btn(self) -> None:
        if self._input_dir and self._output_dir:
            self.process_btn.config(state="normal")
        else:
            self.process_btn.config(state="disabled")

    # ── Processing ────────────────────────────────────────────────────────────

    def _start_processing(self) -> None:
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

    def _poll_queue(self) -> None:
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

                elif kind == "progress":
                    _, file_i, total_files, filename, img_j, n_imgs = msg
                    # overall pct: completed files + fraction through current file
                    pct = ((file_i - 1) + img_j / max(n_imgs, 1)) / total_files * 100
                    self.progress_var.set(pct)
                    short = filename if len(filename) <= 44 else "…" + filename[-41:]
                    self.status_var.set(f"{int(pct)}% done  —  {short}")

        except queue.Empty:
            pass

        self.after(100, self._poll_queue)


if __name__ == "__main__":
    app = App()
    app.mainloop()
