import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import ImageOps


DEFAULTS = argparse.Namespace(
    config="./ocr_config_ping.json",
    timezone="Europe/Berlin",
    preprocess="manual",
    black=80,
    white=255,
    auto_factor=2.5,
    run_output="./output/auswertung.csv",
    batch_output_dir="./test_output",
    
    batch_root=r"E:\0_nd_e2e_evaluation\CLOUDGAMiNG\UB9J4_50\COUNTSTRIKE_PING_TESTS\20260219_0900003", # Wurzelverzeichns bei Batchverarbeitung
    batch_prefix="Check",
    #batch_prefix=datetime.now().strftime("%Y%m%d"),
)


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
    for _bbox, text, conf in results:
        t = text.strip()
        if t:
            lines.append(t)
            confs.append(conf if conf is not None else 0.0)
    avg_conf = sum(confs) / len(confs) if confs else 0.0
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
            avg_conf = sum(confs) / len(confs) / 100.0
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
                # Prefer a named group "val" if present
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
    m = re.search(r"(?<!\d)(\d{10})(?!\d)", name)
    return m.group(1) if m else None


def preprocess_image(image_path, mode, black, white, auto_factor):
    if mode == "off":
        return None

    try:
        from PIL import Image, ImageStat  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Vorverarbeitung benoetigt Pillow (PIL). Bitte installieren: pip install Pillow"
        ) from exc

    img = Image.open(image_path).convert("L")

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

    return ImageOps.invert(img.point(clamp_pixel))


def list_images(input_dir):
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
    images = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.lower().endswith(exts)
    ]
    images.sort()
    return images


def process_directory(
    input_dir,
    output_path,
    cfg,
    engine,
    reader_or_pt,
    tz,
    preprocess_mode,
    black,
    white,
    auto_factor,
    dry_run=False,
    verbose=False,
):
    images = list_images(input_dir)
    fieldnames = (
        ["timestamp", "datetime_local"]
        + [fld["label"] for fld in cfg["fields"]]
        + ["ocr_confidence", "source_file"]
    )

    if dry_run:
        return len(images), fieldnames

    rows = []
    total_images = len(images)
    for idx, img_path in enumerate(images, start=1):
        if verbose:
            print(f"  [{idx}/{total_images}] Verarbeite {os.path.basename(img_path)}")

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

        # Timestamp from filename (10-digit epoch seconds)
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

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return len(rows), fieldnames


def validate_output_csv(output_path, fieldnames, rtt_label):
    total_rows = 0
    complete_rows = 0
    rtt_gt_zero = 0
    rtt_missing_or_invalid = 0

    with open(output_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
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


def load_and_validate_config(config_path):
    if not os.path.isfile(config_path):
        raise FileNotFoundError(
            f"Konfigurationsdatei nicht gefunden: {config_path}"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    fields = cfg.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("Konfiguration ungueltig: 'fields' muss eine nicht-leere Liste sein.")
    for idx, field in enumerate(fields, start=1):
        if not isinstance(field, dict):
            raise ValueError(f"Konfiguration ungueltig: Feld {idx} ist kein Objekt.")
        label = field.get("label")
        patterns = field.get("patterns")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Konfiguration ungueltig: Feld {idx} hat kein gueltiges 'label'.")
        if not isinstance(patterns, list) or not patterns:
            raise ValueError(f"Konfiguration ungueltig: Feld '{label}' hat keine gueltigen 'patterns'.")
    return cfg


def validate_timezone(timezone_name):
    try:
        return ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValueError(
            f"Ungueltige Zeitzone '{timezone_name}'. Beispiel: Europe/Berlin"
        ) from exc


def build_parser():
    parser = argparse.ArgumentParser(
        description="OCR-Auswertung fuer Screenshots -> CSV",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", default=DEFAULTS.config, help="Pfad zur Konfigurationsdatei"
    )
    common.add_argument(
        "--timezone", default=DEFAULTS.timezone, help="Zeitzone fuer lesbares Datum/Zeit"
    )
    common.add_argument(
        "--preprocess",
        default=DEFAULTS.preprocess,
        choices=["off", "auto", "manual"],
        help="Grauwert-Vorverarbeitung",
    )
    common.add_argument(
        "--black",
        type=int,
        default=DEFAULTS.black,
        help="Schwarzwert (0..255), nur im manual-Modus relevant",
    )
    common.add_argument(
        "--white", type=int, default=DEFAULTS.white, help="Weisswert (0..255)"
    )
    common.add_argument(
        "--auto-factor",
        type=float,
        default=DEFAULTS.auto_factor,
        help="Faktor fuer auto-Modus (black = mean * faktor)",
    )
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur pruefen und geplante Verarbeitung anzeigen, keine OCR/CSV-Ausgabe",
    )
    common.add_argument(
        "--verbose", action="store_true", help="Detaillierte Fortschrittsausgaben"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    root_required = not bool(DEFAULTS.batch_root)

    run_parser = subparsers.add_parser(
        "run", parents=[common], help="Einen Screenshot-Ordner verarbeiten"
    )
    run_parser.add_argument("--input", required=True, help="Ordner mit Bildern")
    run_parser.add_argument(
        "--output", default=DEFAULTS.run_output, help="Pfad zur Ausgabe-CSV"
    )

    batch_parser = subparsers.add_parser(
        "batch", parents=[common], help="Alle Unterordner eines Root-Ordners verarbeiten"
    )
    batch_parser.add_argument(
        "--root",
        default=DEFAULTS.batch_root,
        required=root_required,
        help="Ursprungsverzeichnis mit Unterordnern (Batch)",
    )
    batch_parser.add_argument(
        "--output-dir",
        default=DEFAULTS.batch_output_dir,
        help="Ausgabeordner fuer Batch-CSVs",
    )
    batch_parser.add_argument(
        "--prefix",
        default=DEFAULTS.batch_prefix,
        help="Praefix fuer Ausgabe-Dateinamen im Batch-Modus",
    )
    return parser


def print_run_header(args, cfg, mode_label):
    print("Startkonfiguration")
    print(f"- Modus: {mode_label}")
    if args.command == "run":
        print(f"- Input: {args.input}")
        print(f"- Output: {args.output}")
    else:
        print(f"- Root: {args.root}")
        print(f"- Output-Dir: {args.output_dir}")
        print(f"- Prefix: {args.prefix}")
    print(f"- Config: {args.config} ({len(cfg.get('fields', []))} Felder)")
    print(f"- Zeitzone: {args.timezone}")
    print(
        f"- Preprocess: {args.preprocess} (black={args.black}, white={args.white}, auto-factor={args.auto_factor})"
    )
    print(f"- Dry-Run: {'ja' if args.dry_run else 'nein'}")
    print(f"- Verbose: {'ja' if args.verbose else 'nein'}")


def resolve_ocr_engine(dry_run):
    engine, mod = try_import_ocr()
    if engine is None:
        if dry_run:
            return None, None
        print(
            "Kein OCR-Modul gefunden. Installiere entweder 'easyocr' (empfohlen) oder "
            "'pytesseract' + systemweiten Tesseract.",
            file=sys.stderr,
        )
        print("Beispiel: pip install easyocr Pillow", file=sys.stderr)
        sys.exit(2)
    if engine == "easyocr":
        reader = mod.Reader(["de", "en"])
        return engine, reader
    pytesseract, image_mod = mod
    return engine, (pytesseract, image_mod)


def run_single(args, cfg, tz, engine, reader_or_pt):
    if not os.path.isdir(args.input):
        raise FileNotFoundError(f"Input-Ordner nicht gefunden: {args.input}")

    image_count = len(list_images(args.input))
    print(f"Gefundene Bilder: {image_count}")
    if image_count == 0:
        print("Hinweis: Keine Bilddateien gefunden.")

    rows, fieldnames = process_directory(
        args.input,
        args.output,
        cfg,
        engine,
        reader_or_pt,
        tz,
        args.preprocess,
        args.black,
        args.white,
        args.auto_factor,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    if args.dry_run:
        print(
            f"Dry-Run abgeschlossen. {rows} Bilder wuerden verarbeitet und nach '{args.output}' geschrieben."
        )
        return

    print(f"Fertig. {rows} Zeilen nach '{args.output}' geschrieben.")
    rtt_label = cfg["fields"][0]["label"] if cfg.get("fields") else "Roundtripzeit"
    stats = validate_output_csv(args.output, fieldnames, rtt_label)
    print(
        f"Qualitaet: komplett {stats['complete_rows']}/{stats['total_rows']}, "
        f"{rtt_label} > 0: {stats['rtt_gt_zero']}, "
        f"{rtt_label} fehlt/ungueltig: {stats['rtt_missing_or_invalid']}"
    )


def run_batch(args, cfg, tz, engine, reader_or_pt):
    if not os.path.isdir(args.root):
        raise FileNotFoundError(f"Root-Ordner nicht gefunden: {args.root}")

    subdirs = [os.path.join(args.root, d) for d in os.listdir(args.root)]
    subdirs = [d for d in subdirs if os.path.isdir(d)]
    subdirs.sort()

    print(f"Gefundene Unterordner: {len(subdirs)}")
    if not subdirs:
        print("Hinweis: Keine Unterordner gefunden.")
        return

    total_rows = 0
    for idx, subdir in enumerate(subdirs, start=1):
        sub_name = os.path.basename(subdir.rstrip("\\/"))
        out_path = os.path.join(args.output_dir, f"{args.prefix}_{sub_name}.csv")
        image_count = len(list_images(subdir))
        print(f"[{idx}/{len(subdirs)}] Ordner '{sub_name}' mit {image_count} Bildern")

        rows, fieldnames = process_directory(
            subdir,
            out_path,
            cfg,
            engine,
            reader_or_pt,
            tz,
            args.preprocess,
            args.black,
            args.white,
            args.auto_factor,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        total_rows += rows

        if args.dry_run:
            print(f"  Dry-Run: {rows} Bilder wuerden nach '{out_path}' geschrieben.")
            continue

        print(f"  Fertig. {rows} Zeilen nach '{out_path}' geschrieben.")
        rtt_label = cfg["fields"][0]["label"] if cfg.get("fields") else "Roundtripzeit"
        stats = validate_output_csv(out_path, fieldnames, rtt_label)
        print(
            f"  Qualitaet: komplett {stats['complete_rows']}/{stats['total_rows']}, "
            f"{rtt_label} > 0: {stats['rtt_gt_zero']}, "
            f"{rtt_label} fehlt/ungueltig: {stats['rtt_missing_or_invalid']}"
        )

    if args.dry_run:
        print(f"Batch-Dry-Run abgeschlossen. Insgesamt {total_rows} Bilder wuerden verarbeitet.")
    else:
        print(f"Batch fertig. Insgesamt {total_rows} Zeilen.")


# Nutzung (Grundzuege):
# 1) Einzelordner verarbeiten:
#    python "ocr_extract_screenshots copy.py" run --input <BILD_ORDNER> [--output <CSV_PFAD>]
# 2) Mehrere Unterordner im Batch verarbeiten:
#    python "ocr_extract_screenshots copy.py" batch --root <ROOT_ORDNER> [--output-dir <AUSGABE_ORDNER>] [--prefix <NAME>]
# 3) Transparenz/Freigabe:
#    --dry-run prueft nur den Ablauf ohne OCR/Dateischreiben, --verbose zeigt Fortschritt pro Bild.
# 4) Qualitaetsrelevante Optionen:
#    --config, --timezone und --preprocess {off,auto,manual} sowie --black/--white/--auto-factor.
# 5) Defaults zentral pflegen:
#    Standardwerte fuer den Parser stehen im Namespace DEFAULTS (oben in der Datei).
def main():
    start_time = datetime.now()
    parser = build_parser()
    args = parser.parse_args()

    try:
        cfg = load_and_validate_config(args.config)
        tz = validate_timezone(args.timezone)
    except Exception as exc:
        print(f"Fehler bei Startvalidierung: {exc}", file=sys.stderr)
        sys.exit(2)

    mode_label = "Einzelordner" if args.command == "run" else "Batch"
    print_run_header(args, cfg, mode_label)

    engine, reader_or_pt = resolve_ocr_engine(args.dry_run)
    if engine is not None:
        print(f"- OCR-Engine: {engine}")
    else:
        print("- OCR-Engine: nicht geladen (Dry-Run)")

    try:
        if args.command == "run":
            run_single(args, cfg, tz, engine, reader_or_pt)
        else:
            run_batch(args, cfg, tz, engine, reader_or_pt)
    except Exception as exc:
        print(f"Verarbeitung fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Dauer: {datetime.now() - start_time}")


if __name__ == "__main__":
    main()
