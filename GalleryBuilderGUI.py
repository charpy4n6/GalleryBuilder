#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, html, shutil, subprocess, pathlib, argparse
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser  # for "Open Report" button

# -------- Optional deps detection --------
PIL_AVAILABLE = False
try:
    from PIL import Image, ImageFile, UnidentifiedImageError
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    PIL_AVAILABLE = True
except Exception:
    pass

def which_ffmpeg():
    return shutil.which("ffmpeg")

# -------- Photo builder (images) --------
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.bmp', '.tif', '.tiff', '.svg'}

def find_images(root: pathlib.Path, recursive: bool = True):
    if recursive:
        files = [p for p in root.rglob('*') if p.suffix.lower() in IMG_EXTS and p.is_file()]
    else:
        files = [p for p in root.iterdir() if p.suffix.lower() in IMG_EXTS and p.is_file()]
    return sorted(files, key=lambda p: p.name.lower())

def make_thumbs(paths, root: pathlib.Path, thumb_dir: pathlib.Path, size: int, log=lambda *_: None):
    mapping = {}
    if not PIL_AVAILABLE:
        log("Pillow not installed; skipping thumbnails.")
        return mapping
    thumb_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        rel = p.relative_to(root)
        out = thumb_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            if p.suffix.lower() == '.svg':
                if not out.exists():
                    out.write_bytes(p.read_bytes())
                mapping[str(rel).replace(os.sep, '/')] = str(out.relative_to(root)).replace(os.sep, '/')
                continue
            with Image.open(p) as im:
                im.verify()
            with Image.open(p) as im2:
                if im2.mode not in ("RGB", "RGBA"):
                    im2 = im2.convert("RGB")
                im2.thumbnail((size, size))
                if out.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    out = out.with_suffix(".jpg")
                save_kwargs = {}
                if out.suffix.lower() in (".jpg", ".jpeg"):
                    save_kwargs.update(dict(quality=85, optimize=True))
                im2.save(out, **save_kwargs)
            mapping[str(rel).replace(os.sep, '/')] = str(out.relative_to(root)).replace(os.sep, '/')
        except (Exception,) as e:
            log(f"[thumb-skip] {p.name}: {e}")
    return mapping

def write_photos_html(out_path: pathlib.Path, title: str, items):
    css = """
:root { --gap:12px; --bg:#0b0c0f; --fg:#eaecef; --muted:#9aa4b2; }
html,body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
header{position:sticky;top:0;z-index:10;backdrop-filter:blur(8px);background:rgba(0,0,0,.35);border-bottom:1px solid #1d2127}
.bar{display:flex;align-items:center;gap:12px;padding:12px clamp(12px,4vw,28px)}
.muted{color:var(--muted)}
main{padding:clamp(12px,3vw,28px)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:var(--gap)}
figure{margin:0;background:#0f1217;border:1px solid #1f2630;border-radius:16px;overflow:hidden}
.thumb{width:100%;height:160px;object-fit:cover;display:block;background:#0b0b0b}
figcaption{padding:10px;font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
"""
    items_html = []
    for thumb, full, label in items:
        items_html.append(
            f'<a href="{html.escape(full)}" target="_blank" rel="noopener">'
            f'<figure><img class="thumb" loading="lazy" decoding="async" src="{html.escape(thumb)}" alt="{html.escape(label)}">'
            f'<figcaption>{html.escape(label)}</figcaption></figure></a>'
        )
    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>{css}</style>
</head>
<body>
<header><div class="bar">
  <h1 style="margin:0;font-size:18px">{html.escape(title)}</h1>
  <span class="muted" style="margin-left:auto">{len(items_html)} images • built {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
</div></header>
<main><div class="grid">
{os.linesep.join(items_html)}
</div></main>
</body></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding='utf-8')

def build_photos(folder: pathlib.Path, out_path: pathlib.Path, title: str, recursive: bool, make_thumbnails: bool, thumb_size: int, thumb_dir_name: str, log=lambda *_: None):
    images = find_images(folder, recursive=recursive)
    if not images:
        raise SystemExit("No images found.")
    thumb_map = {}
    if make_thumbnails:
        thumb_map = make_thumbs(images, folder, folder / thumb_dir_name, thumb_size, log=log)
    items = []
    for p in images:
        rel = p.relative_to(folder)
        rel_str = str(rel).replace(os.sep, '/')
        thumb_rel = thumb_map.get(rel_str, rel_str)
        items.append((thumb_rel, rel_str, rel.name))
    write_photos_html(out_path, title, items)
    log(f"Wrote {out_path} with {len(items)} images.")

# -------- Video builder --------
VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".webm", ".ogv", ".mkv", ".avi"}
EMBED_EXTS = {".mp4", ".webm", ".ogv"}
MIME_BY_EXT = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".webm": "video/webm", ".ogv": "video/ogg", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
}

def find_videos(root: pathlib.Path, recursive: bool = True):
    if recursive:
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    else:
        files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    return sorted(files, key=lambda p: p.name.lower())

def run_ffmpeg_poster(ffmpeg_exe: str, src: pathlib.Path, dst: pathlib.Path, time_sec: float):
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe,
        "-v", "error",        # show only errors
        "-hide_banner",       # no banner
        "-nostdin",           # don’t wait for input
        "-ss", str(time_sec),
        "-i", str(src),
        "-frames:v", "1",
        "-y",
        str(dst),
    ]
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if os.name == "nt":
        # Windows: prevent flashing console windows
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.run(cmd, **kwargs)
    return proc.returncode == 0

def make_posters(paths, root: pathlib.Path, poster_dir: pathlib.Path, time_sec: float, log=lambda *_: None):
    mapping = {}
    exe = which_ffmpeg()
    if not exe:
        log("ffmpeg not found; skipping poster generation.")
        return mapping
    for p in paths:
        rel = p.relative_to(root)
        out = (poster_dir / rel).with_suffix(".png")
        try:
            ok = run_ffmpeg_poster(exe, p, out, time_sec)
            if ok:
                mapping[str(rel).replace(os.sep, "/")] = str(out.relative_to(root)).replace(os.sep, "/")
            else:
                log(f"[poster-skip] {p.name}")
        except Exception as e:
            log(f"[poster-fail] {p.name}: {e}")
    return mapping

def source_tag(rel_path: str):
    ext = pathlib.Path(rel_path).suffix.lower()
    mime = MIME_BY_EXT.get(ext, "")
    type_attr = f' type="{mime}"' if mime else ""
    return f'<source src="{html.escape(rel_path)}"{type_attr}>'

def write_videos_html(out_path: pathlib.Path, title: str, items):
    css = """
:root { --gap:12px; --bg:#0b0c0f; --fg:#eaecef; --muted:#9aa4b2; }
html,body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
header{position:sticky;top:0;z-index:10;backdrop-filter:blur(8px);background:rgba(0,0,0,.35);border-bottom:1px solid #1d2127}
.bar{display:flex;align-items:center;gap:12px;padding:12px clamp(12px,4vw,28px)}
.muted{color:var(--muted)}
main{padding:clamp(12px,3vw,28px)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:var(--gap)}
figure{margin:0;background:#0f1217;border:1px solid #1f2630;border-radius:16px;overflow:hidden;display:flex;flex-direction:column}
.video-wrap{position:relative;aspect-ratio:16/9;background:#000}
video{width:100%;height:100%;display:block;background:#000}
figcaption{padding:10px;font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.controls{display:flex;gap:8px;padding:8px 10px;border-top:1px solid #1f2630;background:#0f1217}
.controls a{font-size:12px;color:#9cc2ff;text-decoration:none}
.controls a:hover{text-decoration:underline}
.coverlink{position:absolute; inset:0; display:block; text-decoration:none}
.coverlink:focus-visible{outline:2px solid #4b9fff; outline-offset:2px}
"""
    items_html = []
    for (poster, video_rel, label, embeddable) in items:
        poster_tag = f'<img src="{html.escape(poster)}" alt="" style="width:100%;height:100%;object-fit:cover;background:#000">' if poster else '<div style="width:100%;height:100%;background:#000"></div>'
        if embeddable:
            items_html.append(
                f'<figure>'
                f'  <div class="video-wrap">'
                f'    <video controls preload="metadata" {"poster="+html.escape(poster) if poster else ""}>'
                f'      {source_tag(video_rel)}'
                f'      Your browser does not support the video tag.'
                f'    </video>'
                f'  </div>'
                f'  <figcaption title="{html.escape(label)}">{html.escape(label)}</figcaption>'
                f'  <div class="controls">'
                f'    <a href="{html.escape(video_rel)}" target="_blank" rel="noopener">Open in new tab</a>'
                f'  </div>'
                f'</figure>'
            )
        else:
            items_html.append(
                f'<figure>'
                f'  <div class="video-wrap">'
                f'    {poster_tag}'
                f'    <a class="coverlink" href="{html.escape(video_rel)}" target="_blank" rel="noopener" title="Open in new tab"></a>'
                f'  </div>'
                f'  <figcaption title="{html.escape(label)}">{html.escape(label)}'
                f'    <span style="color:#eaad7a;margin-left:6px">(opens in system player / may download)</span>'
                f'  </figcaption>'
                f'  <div class="controls">'
                f'    <a href="{html.escape(video_rel)}" target="_blank" rel="noopener">Open in new tab</a>'
                f'    <a href="{html.escape(video_rel)}" download>Download</a>'
                f'  </div>'
                f'</figure>'
            )

    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>{css}</style>
</head>
<body>
<header><div class="bar">
  <h1 style="margin:0;font-size:18px">{html.escape(title)}</h1>
  <span class="muted" style="margin-left:auto">{len(items_html)} videos • built {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
</div></header>
<main><div class="grid">
{os.linesep.join(items_html)}
</div></main>
</body></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding='utf-8')

def build_videos(folder: pathlib.Path, out_path: pathlib.Path, title: str, recursive: bool, make_posters_flag: bool, poster_time: float, poster_dir_name: str, log=lambda *_: None):
    videos = find_videos(folder, recursive=recursive)
    if not videos:
        raise SystemExit("No videos found.")
    poster_map = {}
    if make_posters_flag:
        poster_map = make_posters(videos, folder, folder / poster_dir_name, poster_time, log=log)
    items = []
    for p in videos:
        rel = p.relative_to(folder)
        rel_str = str(rel).replace(os.sep, "/")
        poster_rel = poster_map.get(rel_str)
        embeddable = pathlib.Path(rel_str).suffix.lower() in EMBED_EXTS
        items.append((poster_rel, rel_str, rel.name, embeddable))
    write_videos_html(out_path, title, items)
    log(f"Wrote {out_path} with {len(items)} videos.")

# === Mixed (images + videos) ===
def write_mixed_html(out_path: pathlib.Path, title: str, items):
    """
    items: list of dicts:
      {
        "kind": "image"|"video",
        "thumb": "rel/path/to/thumb_or_poster",
        "src":   "rel/path/to/original",
        "label": filename,
        "embeddable": bool   # only for kind=="video"
      }
    """
    css = """
:root { --gap:12px; --bg:#0b0c0f; --fg:#eaecef; --muted:#9aa4b2; --accent:#14b8a6; }
html,body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
header{position:sticky;top:0;z-index:10;backdrop-filter:blur(8px);background:rgba(0,0,0,.35);border-bottom:1px solid #1d2127}
.bar{display:flex;align-items:center;gap:12px;padding:12px clamp(12px,4vw,28px)}
.muted{color:var(--muted)}
main{padding:clamp(12px,3vw,28px)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:var(--gap)}
figure{margin:0;background:#0f1217;border:1px solid #1f2630;border-radius:16px;overflow:hidden;display:flex;flex-direction:column;position:relative}
.thumbwrap{position:relative;background:#000}
.thumbimg{width:100%;height:160px;object-fit:cover;display:block;background:#0b0b0b}
.videowrap{position:relative;aspect-ratio:16/9;background:#000}
.play{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:46px;height:46px;border-radius:50%;background:rgba(0,0,0,.55);display:grid;place-items:center;border:1px solid rgba(255,255,255,.25)}
.play:after{content:"";border-style:solid;border-width:9px 0 9px 15px;border-color:transparent transparent transparent white;display:block;margin-left:3px}
.ribbon{position:absolute;top:8px;left:8px;background:linear-gradient(135deg,var(--accent),#0ea5a3);color:#042b2b;font-weight:600;font-size:11px;padding:3px 6px;border-radius:8px}
figcaption{padding:10px;font-size:12px;color:#9aa4b2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.controls{display:flex;gap:8px;padding:8px 10px;border-top:1px solid #1f2630;background:#0f1217}
.controls a{font-size:12px;color:#9cc2ff;text-decoration:none}
.controls a:hover{text-decoration:underline}
.coverlink{position:absolute; inset:0; display:block; text-decoration:none}
.coverlink:focus-visible{outline:2px solid #4b9fff; outline-offset:2px}
"""
    cards = []
    for it in items:
        label_html = html.escape(it["label"])
        src = html.escape(it["src"])
        thumb = html.escape(it["thumb"])

        if it["kind"] == "image":
            cards.append(
                f'<figure>'
                f'  <div class="thumbwrap">'
                f'    <img class="thumbimg" loading="lazy" decoding="async" src="{thumb}" alt="{label_html}">'
                f'    <a class="coverlink" href="{src}" target="_blank" rel="noopener" title="Open in new tab"></a>'
                f'  </div>'
                f'  <figcaption title="{label_html}">{label_html}</figcaption>'
                f'  <div class="controls"><a href="{src}" target="_blank" rel="noopener">Open in new tab</a></div>'
                f'</figure>'
            )
        else:
            ribbon = '<span class="ribbon">VIDEO</span>'
            poster_tag = f'<img class="thumbimg" style="height:100%;object-fit:cover" src="{thumb}" alt="">' if thumb else '<div style="width:100%;height:100%;background:#000"></div>'
            cards.append(
                f'<figure>'
                f'  <div class="videowrap">'
                f'    {poster_tag}<span class="play"></span>{ribbon}'
                f'    <a class="coverlink" href="{src}" target="_blank" rel="noopener" title="Open in new tab"></a>'
                f'  </div>'
                f'  <figcaption title="{label_html}">{label_html}</figcaption>'
                f'  <div class="controls"><a href="{src}" target="_blank" rel="noopener">Open in new tab</a></div>'
                f'</figure>'
            )

    html_doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>{css}</style>
</head>
<body>
<header><div class="bar">
  <h1 style="margin:0;font-size:18px">{html.escape(title)}</h1>
  <span class="muted" style="margin-left:auto">{len(cards)} items • built {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
</div></header>
<main><div class="grid">
{os.linesep.join(cards)}
</div></main>
</body></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")

def build_mixed(folder: pathlib.Path,
                out_path: pathlib.Path,
                title: str,
                recursive: bool = True,
                make_thumbnails: bool = True,
                thumb_size: int = 480,
                thumb_dir_name: str = "_thumbs",
                make_posters_flag: bool = True,   # official name
                poster_time: float = 1.5,
                poster_dir_name: str = "_posters",
                log=lambda *_: None,
                **_compat):                        # accept legacy kwargs (e.g., make_posters=)
    """Build a unified gallery (images + videos) from one folder."""
    # Backward compatibility: allow callers that still pass make_posters=
    if "make_posters" in _compat:
        make_posters_flag = _compat["make_posters"]

    folder = pathlib.Path(folder)
    if not folder.exists():
        raise SystemExit(f"Folder not found: {folder}")

    imgs = find_images(folder, recursive=recursive)
    vids = find_videos(folder, recursive=recursive)
    if not imgs and not vids:
        raise SystemExit("No images or videos found.")

    thumb_map = {}
    if imgs and make_thumbnails:
        log("Generating image thumbnails…")
        thumb_map = make_thumbs(imgs, folder, folder / thumb_dir_name, thumb_size, log=log)

    poster_map = {}
    if vids and make_posters_flag:
        log("Generating video posters…")
        poster_map = make_posters(vids, folder, folder / poster_dir_name, poster_time, log=log)

    items = []
    for p in imgs:
        rel_str = str(p.relative_to(folder)).replace(os.sep, "/")
        items.append({
            "kind": "image",
            "thumb": thumb_map.get(rel_str, rel_str),
            "src": rel_str,
            "label": p.name
        })
    for p in vids:
        rel_str = str(p.relative_to(folder)).replace(os.sep, "/")
        items.append({
            "kind": "video",
            "thumb": poster_map.get(rel_str, ""),
            "src": rel_str,
            "label": p.name,
            "embeddable": pathlib.Path(rel_str).suffix.lower() in EMBED_EXTS
        })

    items.sort(key=lambda d: d["label"].lower())
    write_mixed_html(out_path, title, items)
    log(f"Wrote {out_path} with {len(items)} items.")

# -------- GUI -------- 
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gallery Builder")
        self.geometry("760x520")
        self.resizable(True, True)
        
        # ---- THEME (Dark Teal) ----
        BG="#0d1b1e"; SURFACE="#14292e"; CARD="#18363d"; LINE="#1f4b52"
        FG="#e0f7f9"; MUTED="#9ac5c9"; ACCENT="#14b8a6"

        self.configure(bg=BG)

        style = ttk.Style()
        style.theme_use("clam")  # IMPORTANT: switch off Windows 'vista' theme

        # Base surfaces
        style.configure(".", background=BG, foreground=FG, fieldbackground=SURFACE)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Header.TFrame", background=SURFACE)

        # Text styles
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Header.TLabel", background=SURFACE, foreground=FG, font=("Segoe UI", 12, "bold"))

        # Inputs
        style.configure("TEntry", fieldbackground=SURFACE, foreground=FG)
        style.configure("TSpinbox", fieldbackground=SURFACE, foreground=FG, arrowsize=12)
        style.configure("TCheckbutton", background=BG, foreground=FG)

        # Buttons
        style.configure("TButton", background=SURFACE, foreground=FG, padding=8, borderwidth=0)
        style.map("TButton", background=[("active", LINE)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", padding=8, borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#0d9488")])

        # Checkbuttons (fix white hover/active)
        style.map(
            "TCheckbutton",
            background=[("active", BG), ("selected", BG), ("pressed", BG)],
            foreground=[("active", FG), ("selected", FG), ("pressed", FG)]
        )

        # Notebook (tabs)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=SURFACE, foreground=FG, padding=(12,6))
        style.map("TNotebook.Tab",
                  background=[("selected", CARD), ("active", LINE)],
                  foreground=[("selected", FG)])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.photo_tab = ttk.Frame(nb)
        self.video_tab = ttk.Frame(nb)
        self.mixed_tab = ttk.Frame(nb)  # NEW
        nb.add(self.photo_tab, text="Photos")
        nb.add(self.video_tab, text="Videos")
        nb.add(self.mixed_tab, text="Mixed")  # NEW

        self.make_photo_ui(self.photo_tab)
        self.make_video_ui(self.video_tab)
        self.make_mixed_ui(self.mixed_tab)  # NEW

        # Log box (explicit dark colors since tk.Text doesn't use ttk styles)
        self.log = tk.Text(self, height=6, state="disabled",
                           bg=BG, fg=FG, insertbackground=FG,
                           relief="flat", bd=0, font=("Consolas", 10))
        self.log.pack(fill="both", expand=False, padx=8, pady=(0,8))

        # Status row
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status).pack(anchor="w", padx=10, pady=(0,8))

    def log_print(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.status.set(msg)
        self.update_idletasks()

    # ---- DONE POPUP that opens the report ----
    def show_done_popup(self, out_path: str):
        popup = tk.Toplevel(self)
        popup.title("Gallery Builder")
        popup.resizable(False, False)

        # Center the popup over the main window
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 160
        y = self.winfo_y() + (self.winfo_height() // 2) - 60
        popup.geometry(f"320x120+{x}+{y}")

        frm = ttk.Frame(popup, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=f"Report written to:\n{out_path}").pack(pady=(0,10))

        def open_and_close():
            try:
                webbrowser.open(out_path)  # opens default browser
            finally:
                popup.destroy()

        ttk.Button(frm, text="Open Report", command=open_and_close).pack()
        popup.transient(self)
        popup.grab_set()
        self.wait_window(popup)

    # --- Photos UI ---
    def make_photo_ui(self, root):
        pad = {"padx":8, "pady":6}

        self.p_folder = tk.StringVar()
        self.p_title = tk.StringVar(value="Photo Gallery")
        self.p_out = tk.StringVar(value="index.html")
        self.p_recursive = tk.BooleanVar(value=True)
        self.p_thumbs = tk.BooleanVar(value=True)
        self.p_thumb_size = tk.IntVar(value=480)
        self.p_thumb_dir = tk.StringVar(value="_thumbs")

        frm = ttk.Frame(root); frm.pack(fill="both", expand=True, **pad)

        ttk.Label(frm, text="Photos Folder:").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.p_folder, width=60).grid(row=0, column=1, sticky="we")
        ttk.Button(frm, text="Browse...", command=self.browse_p_folder).grid(row=0, column=2)

        ttk.Label(frm, text="Page Title:").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.p_title, width=40).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Output HTML:").grid(row=2, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.p_out, width=40).grid(row=2, column=1, sticky="w")
        
        ttk.Checkbutton(frm, text="Include subfolders", variable=self.p_recursive).grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(frm, text="Generate thumbnails (Pillow)", variable=self.p_thumbs).grid(row=4, column=1, sticky="w")

        ttk.Label(frm, text="Thumb size (px):").grid(row=5, column=0, sticky="e")
        ttk.Spinbox(frm, from_=120, to=2000, textvariable=self.p_thumb_size, width=8).grid(row=5, column=1, sticky="w")
        ttk.Label(frm, text="Thumbs folder:").grid(row=5, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.p_thumb_dir, width=16).grid(row=5, column=3, sticky="w")

        ttk.Button(frm, text="Build Photo Gallery", command=self.run_photos).grid(row=6, column=1, pady=12, sticky="w")

        for i in range(4):
            frm.columnconfigure(i, weight=1)

    def browse_p_folder(self):
        d = filedialog.askdirectory(title="Select Photos Folder")
        if d:
            self.p_folder.set(d)

    def save_p_out(self):
        f = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML files","*.html")], title="Save gallery as...")
        if f: self.p_out.set(f)

    def run_photos(self):
        try:
            folder = pathlib.Path(self.p_folder.get()).resolve()
            if not folder.exists():
                raise FileNotFoundError("Folder not found.")
            out = pathlib.Path(self.p_out.get())
            if not out.is_absolute():
                out = folder / out
            self.log_print("Building photo gallery...")
            build_photos(
                folder=folder,
                out_path=out,
                title=self.p_title.get().strip() or "Photo Gallery",
                recursive=self.p_recursive.get(),
                make_thumbnails=self.p_thumbs.get(),
                thumb_size=int(self.p_thumb_size.get()),
                thumb_dir_name=self.p_thumb_dir.get().strip() or "_thumbs",
                log=self.log_print
            )
            self.log_print("Photo gallery done.")
            self.show_done_popup(str(out))
        except Exception as e:
            self.log_print(f"Error: {e}")
            messagebox.showerror("Error", str(e))

    # --- Videos UI ---
    def make_video_ui(self, root):
        pad = {"padx":8, "pady":6}

        self.v_folder = tk.StringVar()
        self.v_title = tk.StringVar(value="Video Gallery")
        self.v_out = tk.StringVar(value="index.html")
        self.v_recursive = tk.BooleanVar(value=True)
        self.v_posters = tk.BooleanVar(value=True)
        self.v_poster_time = tk.DoubleVar(value=1.5)
        self.v_poster_dir = tk.StringVar(value="_posters")

        frm = ttk.Frame(root); frm.pack(fill="both", expand=True, **pad)

        ttk.Label(frm, text="Videos Folder:").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.v_folder, width=60).grid(row=0, column=1, sticky="we")
        ttk.Button(frm, text="Browse...", command=self.browse_v_folder).grid(row=0, column=2)

        ttk.Label(frm, text="Page Title:").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.v_title, width=40).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Output HTML:").grid(row=2, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.v_out, width=40).grid(row=2, column=1, sticky="w")
        
        ttk.Checkbutton(frm, text="Include subfolders", variable=self.v_recursive).grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(frm, text="Generate posters (ffmpeg)", variable=self.v_posters).grid(row=4, column=1, sticky="w")

        ttk.Label(frm, text="Poster time (sec):").grid(row=5, column=0, sticky="e")
        ttk.Spinbox(frm, from_=0.0, to=60.0, increment=0.5, textvariable=self.v_poster_time, width=8).grid(row=5, column=1, sticky="w")
        ttk.Label(frm, text="Posters folder:").grid(row=5, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.v_poster_dir, width=16).grid(row=5, column=3, sticky="w")

        ttk.Button(frm, text="Build Video Gallery", command=self.run_videos).grid(row=6, column=1, pady=12, sticky="w")

        # Hint row
        hint = ttk.Label(frm, foreground="#7aa2ff",
                         text="Note: .mp4/.webm/.ogv play inline. Others (e.g., .mov) open in a new tab or external player. Original files are never modified.")
        hint.grid(row=7, column=0, columnspan=4, sticky="w", pady=(4,0))

        for i in range(4):
            frm.columnconfigure(i, weight=1)

    def browse_v_folder(self):
        d = filedialog.askdirectory(title="Select Videos Folder")
        if d:
            self.v_folder.set(d)

    def save_v_out(self):
        f = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML files","*.html")], title="Save gallery as...")
        if f: self.v_out.set(f)

    def run_videos(self):
        try:
            folder = pathlib.Path(self.v_folder.get()).resolve()
            if not folder.exists():
                raise FileNotFoundError("Folder not found.")
            out = pathlib.Path(self.v_out.get())
            if not out.is_absolute():
                out = folder / out
            self.log_print("Building video gallery...")
            build_videos(
                folder=folder,
                out_path=out,
                title=self.v_title.get().strip() or "Video Gallery",
                recursive=self.v_recursive.get(),
                make_posters_flag=self.v_posters.get(),
                poster_time=float(self.v_poster_time.get()),
                poster_dir_name=self.v_poster_dir.get().strip() or "_posters",
                log=self.log_print
            )
            self.log_print("Video gallery done.")
            self.show_done_popup(str(out))
        except Exception as e:
            self.log_print(f"Error: {e}")
            messagebox.showerror("Error", str(e))

    # --- Mixed UI (images + videos) ---
    def make_mixed_ui(self, root):
        pad = {"padx":8, "pady":6}

        self.m_folder = tk.StringVar()
        self.m_title = tk.StringVar(value="Mixed Gallery")
        self.m_out = tk.StringVar(value="index.html")
        self.m_recursive = tk.BooleanVar(value=True)

        # image options
        self.m_thumbs = tk.BooleanVar(value=True)
        self.m_thumb_size = tk.IntVar(value=480)
        self.m_thumb_dir = tk.StringVar(value="_thumbs")

        # video options
        self.m_posters = tk.BooleanVar(value=True)
        self.m_poster_time = tk.DoubleVar(value=1.5)
        self.m_poster_dir = tk.StringVar(value="_posters")

        frm = ttk.Frame(root); frm.pack(fill="both", expand=True, **pad)

        ttk.Label(frm, text="Folder (images + videos):").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.m_folder, width=60).grid(row=0, column=1, sticky="we")
        ttk.Button(frm, text="Browse...", command=self.browse_m_folder).grid(row=0, column=2)

        ttk.Label(frm, text="Page Title:").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.m_title, width=40).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Output HTML:").grid(row=2, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.m_out, width=40).grid(row=2, column=1, sticky="w")

        ttk.Checkbutton(frm, text="Include subfolders", variable=self.m_recursive).grid(row=3, column=1, sticky="w", pady=(6,0))

        # Image row
        ttk.Checkbutton(frm, text="Generate thumbnails (Pillow)", variable=self.m_thumbs).grid(row=4, column=1, sticky="w")
        ttk.Label(frm, text="Thumb size (px):").grid(row=5, column=0, sticky="e")
        ttk.Spinbox(frm, from_=120, to=2000, textvariable=self.m_thumb_size, width=8).grid(row=5, column=1, sticky="w")
        ttk.Label(frm, text="Thumbs folder:").grid(row=5, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.m_thumb_dir, width=16).grid(row=5, column=3, sticky="w")

        # Video row
        ttk.Checkbutton(frm, text="Generate posters (ffmpeg)", variable=self.m_posters).grid(row=6, column=1, sticky="w", pady=(6,0))
        ttk.Label(frm, text="Poster time (sec):").grid(row=7, column=0, sticky="e")
        ttk.Spinbox(frm, from_=0.0, to=60.0, increment=0.5, textvariable=self.m_poster_time, width=8).grid(row=7, column=1, sticky="w")
        ttk.Label(frm, text="Posters folder:").grid(row=7, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.m_poster_dir, width=16).grid(row=7, column=3, sticky="w")

        ttk.Button(frm, text="Build Mixed Gallery", command=self.run_mixed).grid(row=8, column=1, pady=12, sticky="w")

        for i in range(4):
            frm.columnconfigure(i, weight=1)

    def browse_m_folder(self):
        d = filedialog.askdirectory(title="Select Mixed Folder")
        if d:
            self.m_folder.set(d)

    def run_mixed(self):
        try:
            folder = pathlib.Path(self.m_folder.get()).resolve()
            if not folder.exists():
                raise FileNotFoundError("Folder not found.")
            out = pathlib.Path(self.m_out.get())
            if not out.is_absolute():
                out = folder / out
            self.log_print("Building mixed gallery...")
            build_mixed(
                folder=folder,
                out_path=out,
                title=self.m_title.get().strip() or "Mixed Gallery",
                recursive=self.m_recursive.get(),
                make_thumbnails=self.m_thumbs.get(),
                thumb_size=int(self.m_thumb_size.get()),
                thumb_dir_name=self.m_thumb_dir.get().strip() or "_thumbs",
                make_posters_flag=self.m_posters.get(),  # note the _flag name
                poster_time=float(self.m_poster_time.get()),
                poster_dir_name=self.m_poster_dir.get().strip() or "_posters",
                log=self.log_print
            )
            self.log_print("Mixed gallery done.")
            self.show_done_popup(str(out))
        except Exception as e:
            self.log_print(f"Error: {e}")
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    App().mainloop()
