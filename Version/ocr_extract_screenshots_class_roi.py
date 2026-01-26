
# -*- coding: utf-8 -*-
# Class-based OCR Auswertung: Screenshots -> CSV (ROI-fähig)
# - Streaming CSV write, GPU control, EasyOCR/Tesseract engines
# - NEU: ROI-basierte Extraktion je Feld (relative Koordinaten in Config)

import os, re, csv, sys, json, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple, Dict, Any, Optional

# -----------------------------
# Utilities
# -----------------------------
class TimestampExtractor:
    import re as _re
    TS_REGEX = _re.compile(r'(?<!\d)(\d{10})(?!\d)')
    @staticmethod
    def from_filename(name: str) -> Optional[str]:
        m = TimestampExtractor.TS_REGEX.search(name)
        return m.group(1) if m else None

# -----------------------------
# OCR Engines (mit BBox-Unterstützung)
# -----------------------------
class OCREngine:
    def read_detailed(self, image_path: str):
        """
        Returns: (items, avg_conf)
        items: List[{"text": str, "conf": float, "bbox": [(x,y)...4]}]
        """
        raise NotImplementedError
    @property
    def name(self) -> str:
        return self.__class__.__name__

class EasyOCREngine(OCREngine):
    def __init__(self, languages: List[str], gpu_mode: str = "auto"):
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

    def read_detailed(self, image_path: str):
        results = self.reader.readtext(image_path, detail=1, paragraph=False)
        items, confs = [], []
        for bbox, text, conf in results:
            t = (text or "").strip()
            try:
                cf = float(conf) if conf is not None else 0.0
            except Exception:
                cf = 0.0
            if t:
                items.append({"text": t, "conf": cf, "bbox": bbox})
                confs.append(cf)
        avg_conf = sum(confs)/len(confs) if confs else 0.0
        return items, avg_conf

class TesseractEngine(OCREngine):
    def __init__(self):
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        self.pt = pytesseract
        self.Image = Image

    def read_detailed(self, image_path: str):
        img = self.Image.open(image_path)
        d = self.pt.image_to_data(img, lang="deu+eng", output_type=self.pt.Output.DICT)
        n = len(d.get("text", []))
        items, confs = [], []
        for i in range(n):
            txt = (d["text"][i] or "").strip()
            try:
                cf = float(d["conf"][i])
                if cf < 0: cf = 0.0
            except Exception:
                cf = 0.0
            if txt:
                x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
                bbox = [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
                items.append({"text": txt, "conf": cf/100.0, "bbox": bbox})
                confs.append(cf/100.0)
        avg_conf = sum(confs)/len(confs) if confs else 0.0
        return items, avg_conf

class OCREngineFactory:
    @staticmethod
    def create(prefer: str = "easyocr", gpu_mode: str = "auto") -> OCREngine:
        prefer = (prefer or "easyocr").lower()
        tried = []
        def try_easy():
            try:
                import easyocr  # probe
                return EasyOCREngine(["de","en"], gpu_mode=gpu_mode)
            except Exception as e:
                tried.append(("easyocr", str(e)))
                return None
        def try_tess():
            try:
                import pytesseract; from PIL import Image  # type: ignore
                return TesseractEngine()
            except Exception as e:
                tried.append(("pytesseract", str(e)))
                return None
        engine = try_easy() if prefer=="easyocr" else try_tess()
        if engine is None:
            engine = try_tess() if prefer=="easyocr" else try_easy()
        if engine is None:
            msg = "Keine OCR-Engine verfügbar. Installiere easyocr (empf.) oder pytesseract + tesseract-ocr."
            if tried:
                msg += " Details: " + "; ".join([f"{n}:{er}" for n,er in tried])
            raise RuntimeError(msg)
        print(f"[INFO] OCR-Engine: {engine.name}")
        return engine

# -----------------------------
# Region/Regex Extraction
# -----------------------------
def bbox_center(bbox):
    xs = [p[0] for p in bbox]; ys = [p[1] for p in bbox]
    return (sum(xs)/4.0, sum(ys)/4.0)

class RegionExtractor:
    def __init__(self, img_w: int, img_h: int):
        self.w = img_w; self.h = img_h
    def select_items(self, items, roi_rel):
        x1 = roi_rel[0]*self.w; y1 = roi_rel[1]*self.h
        x2 = roi_rel[2]*self.w; y2 = roi_rel[3]*self.h
        picked = []
        for it in items:
            cx, cy = bbox_center(it["bbox"])
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                picked.append(it)
        return picked
    @staticmethod
    def text_from_items(items):
        return "\n".join([it["text"] for it in items])

class RegexExtractor:
    def __init__(self, fields_cfg):
        self.fields_cfg = fields_cfg
    def extract(self, items, img_size):
        out = {}
        full_text = "\n".join([it["text"] for it in items])
        W, H = img_size
        regioner = RegionExtractor(W,H)
        for field in self.fields_cfg:
            label = field["label"]
            pats = field.get("patterns", [])
            roi = field.get("roi")  # [x1,y1,x2,y2] in 0..1, optional
            search_text = full_text
            if roi:
                picked = regioner.select_items(items, roi)
                search_text = regioner.text_from_items(picked)
            value = ""
            for pat in pats:
                m = re.search(pat, search_text, flags=re.IGNORECASE | re.MULTILINE)
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

# -----------------------------
# CSV Writer
# -----------------------------
class CSVWriter:
    def __init__(self, path: str, fieldnames: List[str], append: bool = False):
        self.path = path; self.fieldnames = fieldnames; self.append = append
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        mode = "a" if append else "w"
        need_header = True
        if append and os.path.exists(path):
            try: need_header = os.path.getsize(path)==0
            except Exception: need_header = True
        self._f = open(path, mode, encoding="utf-8", newline="")
        self._w = csv.DictWriter(self._f, fieldnames=fieldnames, delimiter=";")
        if (mode=="w") or need_header:
            self._w.writeheader(); self._f.flush()
    def write_row(self, row: Dict[str,Any]):
        self._w.writerow(row); self._f.flush()
    def close(self):
        try: self._f.close()
        except Exception: pass

# -----------------------------
# Pipeline
# -----------------------------
class Pipeline:
    def __init__(self, input_dir, output_csv, timezone_str, config_path, gpu_mode="auto", append=False, engine_pref="easyocr"):
        self.input_dir = input_dir; self.output_csv=output_csv; self.tz = ZoneInfo(timezone_str)
        self.config_path = config_path; self.gpu_mode=gpu_mode; self.append=append; self.engine_pref=engine_pref
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.fields = self.cfg.get("fields", [])
        self.engine = OCREngineFactory.create(prefer=self.engine_pref, gpu_mode=self.gpu_mode)
        self.fieldnames = ["timestamp","datetime_local"] + [fld["label"] for fld in self.fields] + ["ocr_confidence","source_file"]

    def collect_images(self):
        if not os.path.isdir(self.input_dir):
            raise FileNotFoundError(f"Eingabeordner nicht gefunden: {self.input_dir}")
        exts = (".png",".jpg",".jpeg",".bmp",".tif",".tiff")
        paths = [os.path.join(self.input_dir,f) for f in os.listdir(self.input_dir) if f.lower().endswith(exts)]
        paths.sort(); return paths

    def process_one(self, path):
        # Read OCR with bboxes
        from PIL import Image
        img_w, img_h = Image.open(path).size
        items, avg_conf = self.engine.read_detailed(path)
        extractor = RegexExtractor(self.fields)
        parsed = extractor.extract(items, (img_w, img_h))


        base = os.path.basename(path)
        ts = TimestampExtractor.from_filename(base)
        dt_str = ""
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts), self.tz); dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception: dt_str = ""
        row = {"timestamp": ts or "", "datetime_local": dt_str, "ocr_confidence": f"{avg_conf:.3f}", "source_file": base}
        for f in self.fields:
            row[f["label"]] = parsed.get(f["label"], "")
        return row

    def run(self):
        imgs = self.collect_images()
        print(f"[INFO] {len(imgs)} Bilddatei(en) gefunden.")
        writer = CSVWriter(self.output_csv, self.fieldnames, append=self.append)
        written=0
        try:
            for i,p in enumerate(imgs, start=1):
                r = self.process_one(p); writer.write_row(r); written+=1
                print(f"[OK] ({i}/{len(imgs)}) geschrieben: {r['source_file']}")
        finally:
            writer.close()
        print(f"Fertig. {written} Zeilen nach '{self.output_csv}' geschrieben.")

# -----------------------------
# CLI
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Class-based OCR (ROI) -> CSV")
    ap.add_argument("--input", default="./screenshots")
    ap.add_argument("--output", default="./output/auswertung.csv")
    ap.add_argument("--timezone", default="Europe/Berlin")
    ap.add_argument("--config", default="./ocr_config.json")
    ap.add_argument("--gpu", choices=["auto","on","off"], default="auto")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--engine", choices=["easyocr","tesseract"], default="easyocr")
    args = ap.parse_args()
    Pipeline(args.input, args.output, args.timezone, args.config, gpu_mode=args.gpu, append=args.append, engine_pref=args.engine).run()

if __name__ == "__main__":
    main()
