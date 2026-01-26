# -*- coding: utf-8 -*-
# Class-based OCR Auswertung: Screenshots -> CSV
# Features:
# - Klassenstruktur (ConfigLoader, OCREngine [EasyOCR/Pytesseract], RegexExtractor, CSVWriter, Pipeline)
# - Streaming-Write: schreibt jede ausgewertete Bild-Zeile sofort (optional --append)
# - GPU-Steuerung: --gpu auto|on|off für EasyOCR
# - Timestamp (10-stellig) wird aus Dateinamen extrahiert und nach --timezone konvertiert
# - Konfiguration über JSON (ocr_config.json) mit Regex-Patterns pro Feld

import os
import re
import csv
import sys
import json
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple, Dict, Any, Optional

# -----------------------------
# Utilities
# -----------------------------

class TimestampExtractor:
    TS_REGEX = re.compile(r'(?<!\d)(\d{10})(?!\d)')
    @staticmethod
    def from_filename(name: str) -> Optional[str]:
        m = TimestampExtractor.TS_REGEX.search(name)
        return m.group(1) if m else None


class ConfigLoader:
    def __init__(self, path: str):
        self.path = path
        self.cfg: Dict[str, Any] = {}
        self.fields: List[Dict[str, Any]] = []

    def load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.fields = self.cfg.get("fields", [])
        if not isinstance(self.fields, list):
            raise ValueError("Konfiguration ungültig: 'fields' muss eine Liste sein.")

# -----------------------------
# OCR Engines
# -----------------------------

class OCREngine:
    def read(self, image_path: str) -> Tuple[List[str], float]:
        raise NotImplementedError
    @property
    def name(self) -> str:
        return self.__class__.__name__


class EasyOCREngine(OCREngine):
    def __init__(self, languages: List[str], gpu_mode: str = "auto"):
        # gpu_mode: auto | on | off
        self.languages = languages
        self.gpu = False
        try:
            import torch  # type: ignore
            cuda_ok = torch.cuda.is_available()
        except Exception:
            cuda_ok = False
        if gpu_mode == "on":
            self.gpu = True
        elif gpu_mode == "off":
            self.gpu = False
        else:
            self.gpu = bool(cuda_ok)
        print(f"[INFO] EasyOCR GPU: {self.gpu} (torch.cuda.is_available={cuda_ok})")
        if self.gpu and cuda_ok:
            try:
                import torch  # type: ignore
                print(f"[INFO] CUDA Device: {torch.cuda.get_device_name(0)}")
            except Exception:
                pass

        import easyocr  # type: ignore
        self.reader = easyocr.Reader(self.languages, gpu=self.gpu)

    def read(self, image_path: str) -> Tuple[List[str], float]:
        results = self.reader.readtext(image_path, detail=1, paragraph=False)
        lines: List[str] = []
        confs: List[float] = []
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


class TesseractEngine(OCREngine):
    def __init__(self):
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        self.pt = pytesseract
        self.Image = Image

    def read(self, image_path: str) -> Tuple[List[str], float]:
        img = self.Image.open(image_path)
        text = self.pt.image_to_string(img, lang="deu+eng")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        avg_conf = 0.0
        try:
            d = self.pt.image_to_data(img, lang="deu+eng", output_type=self.pt.Output.DICT)
            confs = [float(c) for c in d.get("conf", []) if c not in ("-1", None)]
            if confs:
                avg_conf = sum(confs)/len(confs)/100.0
        except Exception:
            pass
        return lines, avg_conf


class OCREngineFactory:
    @staticmethod
    def create(prefer: str = "easyocr", gpu_mode: str = "auto") -> OCREngine:
        prefer = (prefer or "easyocr").lower()
        tried = []

        def try_easy():
            try:
                # probe import
                import easyocr  # type: ignore
                return EasyOCREngine(["de", "en"], gpu_mode=gpu_mode)
            except Exception as e:
                tried.append(("easyocr", str(e)))
                return None

        def try_tess():
            try:
                import pytesseract  # type: ignore
                from PIL import Image  # type: ignore
                return TesseractEngine()
            except Exception as e:
                tried.append(("pytesseract", str(e)))
                return None

        engine: Optional[OCREngine] = None
        if prefer == "easyocr":
            engine = try_easy() or try_tess()
        else:
            engine = try_tess() or try_easy()

        if engine is None:
            msg = "Keine OCR-Engine verfügbar. Versuche zu installieren:\n"                   "- EasyOCR: pip install easyocr pillow\n"                   "- (optional) Pytesseract + Tesseract: pip install pytesseract && Systempaket 'tesseract-ocr'"
            if tried:
                msg += "\nDetails: " + "; ".join([f"{n}: {err}" for n, err in tried])
            raise RuntimeError(msg)
        print(f"[INFO] OCR-Engine: {engine.name}")
        return engine

# -----------------------------
# Extraction & Writing
# -----------------------------

class RegexExtractor:
    def __init__(self, fields_cfg: List[Dict[str, Any]]):
        self.fields_cfg = fields_cfg

    def extract(self, lines: List[str]) -> Dict[str, str]:
        text = "\n".join(lines)
        out: Dict[str, str] = {}
        for field in self.fields_cfg:
            label = field["label"]
            patterns = field.get("patterns", [])
            value = ""
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
            out[label] = value
        return out


class CSVWriter:
    def __init__(self, path: str, fieldnames: List[str], append: bool = False):
        self.path = path
        self.fieldnames = fieldnames
        self.append = append
        self._file = None
        self._writer = None

        # ensure directory
        outdir = os.path.dirname(self.path) or "."
        os.makedirs(outdir, exist_ok=True)

        mode = "a" if append else "w"
        need_header = True
        if append and os.path.exists(self.path):
            try:
                need_header = os.path.getsize(self.path) == 0
            except Exception:
                need_header = True

        self._file = open(self.path, mode, encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.fieldnames, delimiter=";")
        if (mode == "w") or need_header:
            self._writer.writeheader()
            self._file.flush()

    def write_row(self, row: Dict[str, Any]) -> None:
        self._writer.writerow(row)
        self._file.flush()

    def close(self) -> None:
        try:
            if self._file:
                self._file.close()
        finally:
            self._file = None
            self._writer = None

# -----------------------------
# Pipeline
# -----------------------------

class Pipeline:
    def __init__(self, input_dir: str, output_csv: str, timezone_str: str,
                 config_path: str, gpu_mode: str = "auto", append: bool = False,
                 prefer_engine: str = "easyocr"):
        self.input_dir = input_dir
        self.output_csv = output_csv
        self.tz = ZoneInfo(timezone_str)
        self.config_path = config_path
        self.gpu_mode = gpu_mode
        self.append = append
        self.prefer_engine = prefer_engine

        self.config = ConfigLoader(self.config_path)
        self.config.load()
        self.extractor = RegexExtractor(self.config.fields)
        self.engine = OCREngineFactory.create(prefer=self.prefer_engine, gpu_mode=self.gpu_mode)

        # CSV fieldnames
        self.fieldnames = ["timestamp", "datetime_local"] +                           [fld["label"] for fld in self.config.fields] +                           ["ocr_confidence", "source_file"]

    def collect_images(self) -> List[str]:
        if not os.path.isdir(self.input_dir):
            raise FileNotFoundError(f"Eingabeordner nicht gefunden: {self.input_dir}")
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
        paths = [os.path.join(self.input_dir, f) for f in os.listdir(self.input_dir)
                 if f.lower().endswith(exts)]
        paths.sort()
        return paths

    def process_one(self, image_path: str) -> Dict[str, Any]:
        try:
            lines, conf = self.engine.read(image_path)
        except Exception as e:
            print(f"[WARN] OCR-Fehler bei {image_path}: {e}")
            lines, conf = [], 0.0
        parsed = self.extractor.extract(lines)

        base = os.path.basename(image_path)
        ts_str = TimestampExtractor.from_filename(base)
        dt_local_str = ""
        if ts_str:
            try:
                ts_int = int(ts_str)
                dt_local = datetime.fromtimestamp(ts_int, self.tz)
                dt_local_str = dt_local.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt_local_str = ""

        row: Dict[str, Any] = {
            "timestamp": ts_str or "",
            "datetime_local": dt_local_str,
            "ocr_confidence": f"{conf:.3f}",
            "source_file": base,
        }
        for fld in self.config.fields:
            row[fld["label"]] = parsed.get(fld["label"], "")
        return row

    def run(self) -> None:
        images = self.collect_images()
        print(f"[INFO] {len(images)} Bilddatei(en) gefunden.")
        writer = CSVWriter(self.output_csv, self.fieldnames, append=self.append)
        written = 0
        try:
            for idx, img in enumerate(images, start=1):
                row = self.process_one(img)
                writer.write_row(row)
                written += 1
                print(f"[OK] ({idx}/{len(images)}) geschrieben: {row['source_file']}")
        finally:
            writer.close()
        print(f"Fertig. {written} Zeilen nach '{self.output_csv}' geschrieben.")

# -----------------------------
# CLI
# -----------------------------

def main():
    ap = argparse.ArgumentParser(description="Class-based OCR-Auswertung: Screenshots -> CSV")
    ap.add_argument("--input", default="./screenshots", help="Ordner mit Bildern (PNG/JPG/BMP/TIF)")
    ap.add_argument("--output", default="./output/auswertung.csv", help="Pfad zur Ausgabe-CSV")
    ap.add_argument("--timezone", default="Europe/Berlin", help="Zeitzone für lesbares Datum/Zeit")
    ap.add_argument("--config", default="./ocr_config.json", help="Pfad zur Konfigurationsdatei (Regex)")
    ap.add_argument("--gpu", choices=["auto", "on", "off"], default="auto",
                    help="GPU-Nutzung für EasyOCR (nur wenn CUDA-fähiges PyTorch installiert ist)")
    ap.add_argument("--append", action="store_true",
                    help="An vorhandene CSV anhängen (Header nur schreiben, wenn Datei leer ist)")
    ap.add_argument("--engine", choices=["easyocr", "tesseract"], default="easyocr",
                    help="Bevorzugte OCR-Engine (fällt automatisch auf andere zurück, wenn nicht verfügbar)")
    args = ap.parse_args()

    pipe = Pipeline(
        input_dir=args.input,
        output_csv=args.output,
        timezone_str=args.timezone,
        config_path=args.config,
        gpu_mode=args.gpu,
        append=args.append,
        prefer_engine=args.engine,
    )
    pipe.run()


if __name__ == "__main__":
    start_time=datetime.now()
    main()
    print(f'Dauer: {datetime.now() - start_time}')
    
