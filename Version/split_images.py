from __future__ import annotations

import os, sys
from typing import Tuple

from pathlib import Path
from PIL import Image, ImageOps
from datetime import datetime
import argparse


class ScreenshotSplitter:
    """
    Lädt einen Screenshot, schneidet optional einen Rand weg, wandelt optional in
    Graustufen und teilt anschließend in linke/rechte Hälfte.

    Zusätzlich kann pro Hälfte das *mittlere Segment* entfernt werden:
    - Bei remove_mode="thirds": Halbieren, dann jede Hälfte in drei Teile (X1|X2|X3) zerlegen
      und zu X1+X3 zusammensetzen.
    - Bei remove_mode="quarters": Halbieren, dann jede Hälfte in vier Teile (X1|X2|X3|X4) zerlegen
      und zu X1+X4 zusammensetzen.
    """

    def __init__(self, crop_margin: int = 0, grayscale: bool = False) -> None:
        self.crop_margin = crop_margin
        self.grayscale = grayscale

    # ------------------------- Core helpers -------------------------
    def _load(self, path: str | Path) -> Image.Image:
        img = Image.open(path)
        if self.crop_margin:
            w, h = img.size
            img = img.crop((self.crop_margin, self.crop_margin,
                            w - self.crop_margin, h - self.crop_margin))
        if self.grayscale:
            img = ImageOps.grayscale(img)
        return img

    @staticmethod
    def _split_left_right(img: Image.Image) -> Tuple[Image.Image, Image.Image]:
        w, h = img.size
        mid = w // 2
        left = img.crop((0, 0, mid, h))
        right = img.crop((mid, 0, w, h))
        return left, right

    @staticmethod
    def _remove_middle_third(img: Image.Image) -> Image.Image:
        w, h = img.size
        x1 = w // 3
        x2 = (2 * w) // 3
        A1 = img.crop((0, 0, x1, h))
        A3 = img.crop((x2, 0, w, h))
        new_w = A1.size[0] + A3.size[0]
        out = Image.new(img.mode, (new_w, h))
        out.paste(A1, (0, 0))
        out.paste(A3, (A1.size[0], 0))
        return out

    @staticmethod
    def _remove_middle_quarters(img: Image.Image) -> Image.Image:
        w, h = img.size
        q1 = w // 4
        q2 = w // 2
        q3 = (3 * w) // 4
        X1 = img.crop((0, 0, q1, h))
        X4 = img.crop((q3, 0, w, h))
        new_w = X1.size[0] + X4.size[0]
        out = Image.new(img.mode, (new_w, h))
        out.paste(X1, (0, 0))
        out.paste(X4, (X1.size[0], 0))
        return out

    # ------------------------- Public API -------------------------
    def process_file(self, path: str | Path, out_dir: str | Path | None = None,
                     remove_mode: str | None = None) -> Tuple[Path | Image.Image, Path | Image.Image]:
        """
        Lädt `path`, splittet in zwei Hälften, optional entfernt in jeder Hälfte
        mittlere Segmente.

        remove_mode: None | "thirds" | "quarters"
        """
        img = self._load(path)
        left, right = self._split_left_right(img)

        if remove_mode == "thirds":
            left = self._remove_middle_third(left)
            right = self._remove_middle_third(right)
        elif remove_mode == "quarters":
            left = self._remove_middle_quarters(left)
            right = self._remove_middle_quarters(right)

        if out_dir is None:
            return left, right

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = Path(path)
        left_path = out_dir / f"{p.stem}._left{p.suffix}"
        right_path = out_dir / f"{p.stem}._right{p.suffix}"
        left.save(left_path)
        right.save(right_path)
        return left_path, right_path






def main():
    start_time = datetime.now()
    ap = argparse.ArgumentParser(description="OCR-Auswertung für Screenshots -> CSV")
    ap.add_argument("--input", default="./screenshots", help="Ordner mit Bildern (PNG/JPG/BMP/TIF)")
    ap.add_argument("--output", default="./output", help="Pfad zur Ausgabe-CSV")
    ap.add_argument("--timezone", default="Europe/Berlin", help="Zeitzone für lesbares Datum/Zeit")
#    ap.add_argument("--config", default="./ocr_config.json", help="Pfad zur Konfigurationsdatei")
#    ap.add_argument("--gpu", choices=["auto","on","off"], default="auto",
#                    help="GPU-Nutzung für EasyOCR: auto|on|off")
    args = ap.parse_args()

    # Bilder einsammeln
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
    if not os.path.isdir(args.input):
        print(f"Eingabeordner nicht gefunden: {args.input}")
        sys.exit(3)

    images = [os.path.join(args.input, f) for f in os.listdir(args.input) if f.lower().endswith(exts)]
    images.sort()
    print(f"[INFO] {len(images)} Bilddatei(en) gefunden.")

    splitter = ScreenshotSplitter(crop_margin=0, grayscale=False)

    for img_path in images[:5]:
        left_img, right_img = splitter.process_file(img_path, out_dir=args.output, remove_mode = 'quarters')
        print("gespeichert unter:", left_img, right_img)



if __name__ == "__main__":
    main()
