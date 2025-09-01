# -*- coding: utf-8 -*-
"""
OCR-Auswertung für Screenshots -> CSV
- Liest feste Felder per Regex (aus externer JSON-Konfiguration)
- Timestamp (10-stellig, UNIX Sekunden) wird aus dem Dateinamen extrahiert
- Optional: GPU-Nutzung für EasyOCR steuerbar (auto/on/off)
"""

import os
import re
import csv
import sys
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

def try_import_ocr():
    """
    Versuche zuerst EasyOCR, dann pytesseract.
    """
    try:
        import easyocr  # type: ignore
        return ("easyocr", easyocr)
    except Exception:
        pass
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        return ("pytesseract", (pytesseract, Image))
    except Exception:
        return (None, None)

def run_easyocr(reader, image_path):
    """
    Führt EasyOCR aus und gibt (Zeilenliste, Durchschnitts-Confidence[0..1]) zurück.
    """
    results = reader.readtext(image_path, detail=1, paragraph=False)
    lines, confs = [], []
    for bbox, text, conf in results:
        t = (text or "").strip()
        if t:
            lines.append(t)
            try:
                confs.append(float(conf) if conf is not None else 0.0)
            except Exception:
                confs.append(0.0)
    avg_conf = sum(confs)/len(confs) if confs else 0.0
    return lines, avg_conf

def run_pytesseract(pt, Image, image_path):
    """
    Führt pytesseract aus und gibt (Zeilenliste, pseudo-Confidence[0..1]) zurück.
    """
    img = Image.open(image_path)
    text = pt.image_to_string(img, lang="deu+eng")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
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
    """
    Wendet die Regex-Patterns aus der Konfiguration an.
    """
    text = "\n".join(lines)
    out = {}
    for field in cfg["fields"]:
        label = field["label"]
        patterns = field["patterns"]
        value = None
        for pat in patterns:
            m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
            if m:
                if "val" in m.groupdict():
                    value = m.group("val").strip()
                elif m.groups():
                    value = m.group(1).strip()
                else:
                    value = m.group(0).strip()
                break
        out[label] = value if value is not None else ""
    return out

def extract_timestamp_from_name(name):
    """
    Extrahiert einen 10-stelligen UNIX-Timestamp aus dem Dateinamen.
    Korrigiertes Regex (keine überflüssigen Escapes).
    """
    m = re.search(r'(?<!\d)(\d{10})(?!\d)', name)
    return m.group(1) if m else None

def main():
    start_time = datetime.now()
    ap = argparse.ArgumentParser(description="OCR-Auswertung für Screenshots -> CSV")
    ap.add_argument("--input", default="./data", help="Ordner mit Bildern (PNG/JPG/BMP/TIF)")
    ap.add_argument("--output", default="./data/auswertung.csv", help="Pfad zur Ausgabe-CSV")
    ap.add_argument("--timezone", default="Europe/Berlin", help="Zeitzone für lesbares Datum/Zeit")
    ap.add_argument("--config", default="./data/ocr_config.json", help="Pfad zur Konfigurationsdatei")
    ap.add_argument("--gpu", choices=["auto","on","off"], default="auto",
                    help="GPU-Nutzung für EasyOCR: auto|on|off")
    args = ap.parse_args()

    # Konfiguration laden
    import json
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # OCR-Engine wählen
    engine, mod = try_import_ocr()
    if engine is None:
        print("Kein OCR-Modul gefunden. Installiere 'easyocr' (empfohlen) oder 'pytesseract' + Tesseract.")
        sys.exit(2)

    reader = None
    pt = None
    Image = None

    if engine == "easyocr":
        # GPU-Entscheidung
        try:
            import torch
            cuda_ok = torch.cuda.is_available()
        except Exception:
            cuda_ok = False

        if args.gpu == "on":
            gpu_flag = True
        elif args.gpu == "off":
            gpu_flag = False
        else:  # auto
            gpu_flag = bool(cuda_ok)

        print(f"[INFO] EasyOCR GPU: {gpu_flag} (torch.cuda.is_available={cuda_ok})")
        if gpu_flag and cuda_ok:
            try:
                import torch
                print(f"[INFO] CUDA Device: {torch.cuda.get_device_name(0)}")
            except Exception:
                pass

        reader = mod.Reader(['de','en'], gpu=gpu_flag)
    else:
        pt, Image = mod

    # Bilder einsammeln
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
    if not os.path.isdir(args.input):
        print(f"Eingabeordner nicht gefunden: {args.input}")
        sys.exit(3)

    images = [os.path.join(args.input, f) for f in os.listdir(args.input) if f.lower().endswith(exts)]
    images.sort()
    print(f"[INFO] {len(images)} Bilddatei(en) gefunden.")

    tz = ZoneInfo(args.timezone)

    # CSV-Vorbereitung
    fieldnames = ["timestamp", "datetime_local"] + [fld["label"] for fld in cfg["fields"]] + ["ocr_confidence", "source_file"]
    rows = []

    for img_path in images:
        try:
            if engine == "easyocr":
                lines, conf = run_easyocr(reader, img_path)
            else:
                lines, conf = run_pytesseract(pt, Image, img_path)
        except Exception as e:
            print(f"[WARN] OCR-Fehler bei {img_path}: {e}")
            lines, conf = [], 0.0

        parsed = parse_fields(lines, cfg)

        # timestamp aus Dateiname
        base = os.path.basename(img_path)
        ts_str = extract_timestamp_from_name(base)
        dt_local_str = ""
        if ts_str:
            try:
                ts_int = int(ts_str)
                dt_local = datetime.fromtimestamp(ts_int, tz)
                dt_local_str = dt_local.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt_local_str = ""

        row = {
            "timestamp": ts_str or "",
            "datetime_local": dt_local_str,
            "ocr_confidence": f"{conf:.3f}",
            "source_file": base,
        }
        # Extrahierte Felder
        for fld in cfg["fields"]:
            row[fld["label"]] = parsed.get(fld["label"], "")

        rows.append(row)

    # CSV schreiben (deutsches Semikolon als Trenner)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Fertig. {len(rows)} Zeilen nach '{args.output}' geschrieben. Dauer: {datetime.now() - start_time}")

if __name__ == "__main__":
    main()
