#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrahiert Messwerte aus BenQ-Dashboard-Screens (2x4, dunkles Theme).
Schreibt CSV (Semikolon, UTF-8) mit:
timestamp;datetime_local;Hochladen;Herunterladen;LAN Latency (RTT);WAN Latency (RTT);
LAN Jitter;WAN Jitter;LAN Packet Loss;WAN Packet Loss;source_file

Neu:
- --debug-mini  : zeigt pro Feld (und pro ROI-Versuch) die ersten 120 Zeichen des OCR-Textes
- --debug-roi   : speichert die verwendeten ROI-Crops in ./roi_debug
"""

import re, csv, argparse, sys
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageOps
import pytesseract

# Optional: Unter Windows Tesseract-Pfad setzen, falls nötig
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

FIELDS = [
    ("Hochladen",             0, 0),
    ("Herunterladen",         0, 1),
    ("LAN Latency (RTT)",     1, 0),
    ("WAN Latency (RTT)",     1, 1),
    ("LAN Jitter",            2, 0),
    ("WAN Jitter",            2, 1),
    ("LAN Packet Loss",       3, 0),
    ("WAN Packet Loss",       3, 1),
]

NUM = r"([0-9]+[.,][0-9]+|[0-9]+)"
PAT_MBPS = re.compile(NUM + r"\s*(?:m\s*bit\s*/\s*s|mbps|mbit/s|mbit\s*/\s*s|MBit/s|Mbit/s|Mbps)", re.I)
PAT_MS   = re.compile(NUM + r"\s*ms", re.I)
PAT_PCT  = re.compile(NUM + r"\s*%", re.I)
PAT_MBPS_FALLBACK = re.compile(NUM + r"(?=\s*(?:m\s*bit|mbps|mbit|mb))", re.I)

def parse_val(txt: str, label: str) -> str:
    t = re.sub(r"\s+", " ", txt.replace("\n"," ").strip())
    t = t.replace("Ms","ms").replace("MS","ms")
    if label in ("Hochladen","Herunterladen"):
        m = PAT_MBPS.search(t)
        if m: return m.group(0)
        m = PAT_MBPS_FALLBACK.search(t)
        if m: return m.group(1) + " Mbit/s"
    elif "Latency" in label or "Jitter" in label:
        m = PAT_MS.search(t)
        if m: return m.group(0)
    elif "Loss" in label:
        m = PAT_PCT.search(t)
        if m: return m.group(0)
    # Fallback: erste Zahl + plausibles Suffix
    m = re.search(NUM, t)
    if m:
        if "Loss" in label: return m.group(1) + " %"
        if "Latency" in label or "Jitter" in label: return m.group(1) + " ms"
        return m.group(1) + " Mbit/s"
    return ""

def rois_for_tile(W, H, r, c):
    """liefert 3 ROI-Varianten (eng, breit, tiefer) für die Wertanzeige oben rechts"""
    tile_w, tile_h = W/2.0, H/4.0
    x0, y0 = c*tile_w, r*tile_h
    tight = (int(x0 + 0.64*tile_w), int(y0 + 0.04*tile_h),
             int(x0 + 0.985*tile_w), int(y0 + 0.22*tile_h))
    wide  = (int(x0 + 0.50*tile_w), int(y0 + 0.02*tile_h),
             int(x0 + 0.985*tile_w), int(y0 + 0.30*tile_h))
    lower = (int(x0 + 0.50*tile_w), int(y0 + 0.18*tile_h),
             int(x0 + 0.985*tile_w), int(y0 + 0.40*tile_h))
    return [tight, wide, lower]

ROI_NAMES = ["tight", "wide", "lower"]

def ocr_region(img, bbox, psm=7, whitelist=True):
    region = img.crop(bbox)
    gray = ImageOps.grayscale(region)
    if whitelist:
        cfg = f'--psm {psm} -c preserve_interword_spaces=1 -c tessedit_char_whitelist=0123456789.,/%%MbitmsMBp'
    else:
        cfg = f'--psm {psm} -c preserve_interword_spaces=1'
    return pytesseract.image_to_string(gray, lang='deu+eng', config=cfg)

def extract_from_image(path: Path, debug_dir: Path|None=None, mini_debug: bool=False, mini_sink=None):
    """
    mini_debug=True: schreibt pro Feld und pro ROI-Versuch eine kurze Debug-Zeile
    """
    img = Image.open(path)
    W, H = img.size
    out = {}

    def log(line: str):
        if not mini_debug: 
            return
        if mini_sink:
            mini_sink.write(line + "\n")
        else:
            print(line)

    for label, r, c in FIELDS:
        val = ""
        for idx, bbox in enumerate(rois_for_tile(W,H,r,c)):
            if debug_dir:
                dbg = img.crop(bbox)
                dbg.save(debug_dir / f"{path.stem}_{label.replace(' ','_')}_{ROI_NAMES[idx]}.png")
            raw = ocr_region(img, bbox, psm=7, whitelist=True)
            raw_1line = re.sub(r"\s+", " ", raw).strip()
            short = (raw_1line[:120] + "…") if len(raw_1line) > 120 else raw_1line
            log(f"[{path.name}] {label:<20} roi={ROI_NAMES[idx]:<5} bbox={bbox} txt='{short}'")
            # parse & ggf. abbrechen, wenn Wert plausibel
            parsed = parse_val(raw, label)
            if parsed:
                val = parsed
                break
        out[label] = val
    return out

def ts_from_name(name: str) -> tuple[str,str]:
    m = re.search(r"(\d{10})", name)
    if not m: return "", ""
    ts = m.group(1)
    try:
        dt = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        dt = ""
    return ts, dt

def main():
    ap = argparse.ArgumentParser(description="BenQ Dashboard OCR → CSV (Semikolon)")
    ap.add_argument("input", nargs="?", default="./screenshots", help="Ordner mit PNGs (Standard: .)")
    ap.add_argument("-o", "--out", default="./output/dashboard_values.csv", help="Ausgabedatei (CSV, UTF-8)")
    ap.add_argument("--glob", default="*.png", help="Dateifilter (Standard: *.png)")
    ap.add_argument("--debug-roi", action="store_true", help="Speichert ROI-Crops in ./roi_debug")
    ap.add_argument("--debug-mini", action="store_true",
                    help="Zeigt pro Feld/ROI die ersten 120 Zeichen des OCR-Texts (für Live-ROI-Check)")
    ap.add_argument("--debug-mini-file", default="",
                    help="Schreibt die Mini-Debug-Ausgabe zusätzlich in diese Datei (append)")
    args = ap.parse_args()

    in_dir = Path(args.input)
    files = sorted(in_dir.glob(args.glob))
    if not files:
        print("Keine Bilder gefunden.", file=sys.stderr)
        sys.exit(2)

    debug_dir = None
    if args.debug_roi:
        debug_dir = Path("./roi_debug")
        debug_dir.mkdir(parents=True, exist_ok=True)

    mini_sink = None
    if args.debug_mini and args.debug_mini_file:
        mini_sink = open(args.debug_mini_file, "a", encoding="utf-8")

    cols = ["timestamp","datetime_local","Hochladen","Herunterladen",
            "LAN Latency (RTT)","WAN Latency (RTT)","LAN Jitter","WAN Jitter",
            "LAN Packet Loss","WAN Packet Loss","source_file"]

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        w.writeheader()
        for p in files:
            vals = extract_from_image(p, debug_dir, mini_debug=args.debug_mini, mini_sink=mini_sink)
            ts, dt = ts_from_name(p.name)
            row = {"timestamp": ts, "datetime_local": dt, **vals, "source_file": p.name}
            w.writerow(row)

    if mini_sink:
        mini_sink.close()

    print(f"Fertig: {args.out} (Einträge: {len(files)})")

if __name__ == "__main__":
    main()
