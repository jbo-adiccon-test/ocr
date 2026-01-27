
import os
import re
import csv
import sys
import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def try_import_ocr():
    # Try EasyOCR first
    try:
        import easyocr  # type: ignore
        return ("easyocr", easyocr)
    except Exception:
        pass
    # Fallback: pytesseract (requires Tesseract installed on system)
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        return ("pytesseract", (pytesseract, Image))
    except Exception:
        return (None, None)

def run_easyocr(reader, image_path):
    # Returns text lines and average confidence (0..1)
    results = reader.readtext(image_path, detail=1, paragraph=False)
    lines = []
    confs = []
    for bbox, text, conf in results:
        t = text.strip()
        if t:
            lines.append(t)
            confs.append(conf if conf is not None else 0.0)
    avg_conf = sum(confs)/len(confs) if confs else 0.0
    return lines, avg_conf

def run_pytesseract(pt, Image, image_path):
    # Basic OCR using pytesseract; no confidences per word in simple mode
    img = Image.open(image_path)
    text = pt.image_to_string(img, lang="deu+eng")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Try to estimate a pseudo-confidence (not reliable)
    avg_conf = 0.0
    try:
        d = pt.image_to_data(img, lang="deu+eng", output_type=pt.Output.DICT)
        confs = [float(c) for c in d.get("conf", []) if c not in ("-1", None)]
        if confs:
            avg_conf = sum(confs)/len(confs)/100.0
    except Exception:
        pass
    return lines, avg_conf

def parse_fields(lines, cfg):
    text = "\n".join(lines)
    out = {}
    for field in cfg["fields"]:
        label = field["label"]
        patterns = field["patterns"]
        value = None
        for pat in patterns:
            m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
            if m:
                # prefer a named group 'val' if present
                if "val" in m.groupdict():
                    value = m.group("val").strip()
                elif m.groups():
                    value = m.group(1).strip()
                else:
                    value = m.group(0).strip()
                break
        out[label] = value
    return out

def extract_timestamp_from_name(name):
    
    m = re.search(r'(?<!\d)(\d{10})(?!\d)', name)
    return m.group(1) if m else None

def main():
    start_time = datetime.now()
    ap = argparse.ArgumentParser(description="OCR-Auswertung für Screenshots -> CSV")
    ap.add_argument("--input", default="./screenshots", help="Ordner mit Bildern (PNG/JPG)")
    ap.add_argument("--output", default="./output/auswertung.csv", help="Pfad zur Ausgabe-CSV")
    ap.add_argument("--timezone", default="Europe/Berlin", help="Zeitzone für lesbares Datum/Zeit")
    ap.add_argument("--config", default="./ocr_config_ping.json", help="Pfad zur Konfigurationsdatei")
    args = ap.parse_args()

    # Load config
    import json
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    engine, mod = try_import_ocr()
    if engine is None:
        print("Kein OCR-Modul gefunden. Bitte installiere entweder 'easyocr' (empfohlen) oder 'pytesseract' + system-weiten Tesseract.")
        print("Beispiel: pip install easyocr Pillow")
        sys.exit(2)

    if engine == "easyocr":
        reader = mod.Reader(['de','en'])
    else:
        pytesseract, Image = mod

    # Collect images
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
    images = [os.path.join(args.input, f) for f in os.listdir(args.input) if f.lower().endswith(exts)]
    images.sort()

    tz = ZoneInfo(args.timezone)

    # Prepare CSV
    fieldnames = ["timestamp", "datetime_local"] + [fld["label"] for fld in cfg["fields"]] + ["ocr_confidence", "source_file"]
    rows = []

    for img_path in images:
        if engine == "easyocr":
            lines, conf = run_easyocr(reader, img_path)
        else:
            lines, conf = run_pytesseract(pytesseract, Image, img_path)

        parsed = parse_fields(lines, cfg)

        # timestamp from filename (10-digit, epoch seconds)
        base = os.path.basename(img_path)
        ts_str = extract_timestamp_from_name(base)
        dt_local_str = ""
        if ts_str:
            try:
                ts_int = int(ts_str)
                dt_local = datetime.fromtimestamp(ts_int, tz)
                dt_local_str = dt_local.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        row = {
            "timestamp": ts_str or "",
            "datetime_local": dt_local_str,
            "ocr_confidence": f"{conf:.3f}",
            "source_file": base,
        }
        for fld in cfg["fields"]:
            row[fld["label"]] = parsed.get(fld["label"], "")
        rows.append(row)

    # Write CSV (semicolon for DE)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Fertig. {len(rows)} Zeilen nach '{args.output}' geschrieben. Dauer: {datetime.now() - start_time}")

if __name__ == "__main__":
    main()
