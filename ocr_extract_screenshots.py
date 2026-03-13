import os
import re
import csv
import sys
import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageOps

import json

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

def run_easyocr(reader, image_input):
    # Returns text lines and average confidence (0..1)
    results = reader.readtext(image_input, detail=1, paragraph=False)
    lines = []
    confs = []
    for bbox, text, conf in results:
        t = text.strip()
        if t:
            lines.append(t)
            confs.append(conf if conf is not None else 0.0)
    avg_conf = sum(confs)/len(confs) if confs else 0.0
    return lines, avg_conf

def run_pytesseract(pt, Image, image_input):
    # Basic OCR using pytesseract; no confidences per word in simple mode
    if isinstance(image_input, str):
        img = Image.open(image_input)
    else:
        img = image_input
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

def preprocess_image(image_path, mode, black, white, auto_factor):
    if mode == "off":
        return None

    try:
        from PIL import Image, ImageStat  # type: ignore
    except Exception:
        raise RuntimeError("Vorverarbeitung benötigt Pillow (PIL). Bitte installieren: pip install Pillow")

    img = Image.open(image_path).convert("L")
    img.__reduce__


    if mode == "auto":
        mean_val = ImageStat.Stat(img).mean[0]
        black_thr = int(max(0, min(255, auto_factor * mean_val)))
        
    else:
        black_thr = int(max(0, min(255, black)))

    white_thr = int(max(0, min(255, white)))
    if white_thr < black_thr:
        white_thr = black_thr

    def clamp_pixel(p):
        if p < black_thr:
            return 0
        if p > white_thr:
            return 255
        return p
    #
    # ImageOps.invert(img.point(clamp_pixel)).show()
    # img.point(clamp_pixel).show()
    #
    #im_invert = ImageOps.invert(img)

    #return img.point(clamp_pixel)
    return ImageOps.invert(img.point(clamp_pixel))

def process_directory(input_dir, output_path, cfg, engine, reader_or_pt, tz, preprocess_mode, black, white, auto_factor):
    # Collect images
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
    images = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.lower().endswith(exts)]
    images.sort()

    # Prepare CSV
    fieldnames = ["timestamp", "datetime_local"] + [fld["label"] for fld in cfg["fields"]] + ["ocr_confidence", "source_file"]
    rows = []

    for img_path in images:
        pre_img = preprocess_image(img_path, preprocess_mode, black, white, auto_factor)
        if engine == "easyocr":
            if pre_img is None:
                lines, conf = run_easyocr(reader_or_pt, img_path)
            else:
                import numpy as np  # type: ignore
                lines, conf = run_easyocr(reader_or_pt, np.array(pre_img))
        else:
            pytesseract, Image = reader_or_pt
            if pre_img is None:
                lines, conf = run_pytesseract(pytesseract, Image, img_path)
            else:
                lines, conf = run_pytesseract(pytesseract, Image, pre_img)

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
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        w.writeheader()
        for r in rows:
            w.writerow(r)

    return len(rows), fieldnames

def validate_output_csv(output_path, fieldnames, rtt_label):
    total_rows = 0
    complete_rows = 0
    rtt_gt_zero = 0
    rtt_missing_or_invalid = 0

    with open(output_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            total_rows += 1
            if all((row.get(fn, "") or "").strip() != "" for fn in fieldnames):
                complete_rows += 1

            rtt_val = (row.get(rtt_label, "") or "").strip()
            if rtt_val:
                tokens = re.findall(r"\b\d{1,4}\b", rtt_val)
                if len(tokens) == 1:
                    num = int(tokens[0])
                    if num > 0:
                        rtt_gt_zero += 1
                else:
                    rtt_missing_or_invalid += 1
            else:
                rtt_missing_or_invalid += 1

    return {
        "total_rows": total_rows,
        "complete_rows": complete_rows,
        "rtt_gt_zero": rtt_gt_zero,
        "rtt_missing_or_invalid": rtt_missing_or_invalid,
    }

def main():
    start_time = datetime.now()
    prefix = "20260219"
    default_screenshots = r"./screenshots"
    default_output = "./output/auswertung.csv"
    screenshots = f'D:/0_nd_e2e_evaluation/CLOUDGAMiNG/ULBWE/COUNTERSTRIKE/20260203_LAN/{prefix}'
    rootdir=r'E:\0_nd_e2e_evaluation\CLOUDGAMiNG\UB9J4_50\COUNTSTRIKE_PING_TESTS\20260219_0411083'
    output = default_output    
    output = f"./output/20260203_{prefix}.csv"
    
   
    #screenshots=r'C:\Users\bodensohn\git\0_nd_e2e_evaluation\HomeLAN_Results\GeForceNowPing\WLAN_VerstÃ¤rker_BOOST_ON_NO_LOAD'
    ap = argparse.ArgumentParser(description="OCR-Auswertung für Screenshots -> CSV")
    ap.add_argument("--input", default=screenshots, help="Ordner mit Bildern (PNG/JPG)")
    ap.add_argument("--root", default=rootdir, help="Ursprungsverzeichnis mit Unterordnern (Batch)")
    ap.add_argument("--output", default=output, help="Pfad zur Ausgabe-CSV")
    ap.add_argument("--prefix", default=prefix, help="Prefix für Ausgabe-Dateinamen im Batch-Modus")
    ap.add_argument("--preprocess", default="manual", choices=["auto", "manual", "auto"], help="Grauwert-Vorverarbeitung")
    ap.add_argument("--black", type=int, default=80, help="Schwarzwert (0..255) im manual-Modus")
    ap.add_argument("--white", type=int, default=255, help="Weißwert (0..255)")
    ap.add_argument("--auto-factor", type=float, default=2.5, help="Faktor für auto-Modus (black = mean * faktor)")
    ap.add_argument("--timezone", default="Europe/Berlin", help="Zeitzone für lesbares Datum/Zeit")
    ap.add_argument("--config", default="./ocr_config_ping.json", help="Pfad zur Konfigurationsdatei")
    args = ap.parse_args()

    # Load config    
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

    tz = ZoneInfo(args.timezone)

    if args.root:
        subdirs = [os.path.join(args.root, d) for d in os.listdir(args.root)]
        subdirs = [d for d in subdirs if os.path.isdir(d)]
        subdirs.sort()

        total_rows = 0
        for subdir in subdirs:
            sub_name = os.path.basename(subdir.rstrip("\\/"))
            out_path = os.path.join("./output", f"{args.prefix}_{sub_name}.csv")
            if engine == "easyocr":
                rows, fieldnames = process_directory(
                    subdir, out_path, cfg, engine, reader, tz,
                    args.preprocess, args.black, args.white, args.auto_factor
                )
            else:
                rows, fieldnames = process_directory(
                    subdir, out_path, cfg, engine, (pytesseract, Image), tz,
                    args.preprocess, args.black, args.white, args.auto_factor
                )
            total_rows += rows
            print(f"Fertig. {rows} Zeilen nach '{out_path}' geschrieben (Ordner: {sub_name}).")
            rtt_label = cfg["fields"][0]["label"] if cfg.get("fields") else "Roundtripzeit"
            stats = validate_output_csv(out_path, fieldnames, rtt_label)
            print(
                f"Test: komplett {stats['complete_rows']}/{stats['total_rows']}, "
                f"Roundtripzeit > 0: {stats['rtt_gt_zero']}, "
                f"Roundtripzeit fehlt/ungueltig: {stats['rtt_missing_or_invalid']}"
            )

        print(f"Batch fertig. Insgesamt {total_rows} Zeilen. Dauer: {datetime.now() - start_time}")
    else:
        if engine == "easyocr":
            rows, fieldnames = process_directory(
                args.input, args.output, cfg, engine, reader, tz,
                args.preprocess, args.black, args.white, args.auto_factor
            )
        else:
            rows, fieldnames = process_directory(
                args.input, args.output, cfg, engine, (pytesseract, Image), tz,
                args.preprocess, args.black, args.white, args.auto_factor
            )
        print(f"Fertig. {rows} Zeilen nach '{args.output}' geschrieben. Dauer: {datetime.now() - start_time}")
        rtt_label = cfg["fields"][0]["label"] if cfg.get("fields") else "Roundtripzeit"
        stats = validate_output_csv(args.output, fieldnames, rtt_label)
        print(
            f"Test: komplett {stats['complete_rows']}/{stats['total_rows']}, "
            f"Roundtripzeit > 0: {stats['rtt_gt_zero']}, "
            f"Roundtripzeit fehlt/ungueltig: {stats['rtt_missing_or_invalid']}"
        )

if __name__ == "__main__":
    main()
