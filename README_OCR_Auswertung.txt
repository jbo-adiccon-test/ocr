
OCR-Auswertung für Screenshots – Anleitung
==========================================

1) Lege Deine Screenshots in den Ordner: /mnt/data
   - Erlaubte Endungen: .png .jpg .jpeg .bmp .tif .tiff
   - Idealerweise enthält der Dateiname einen 10-stelligen UNIX-Timestamp (Sekunden), z.B.:
     meeting_1725206400_screenshot.png

2) (Optional) Passe die Erkennungsregeln an in: /mnt/data/ocr_config.json
   - Die Datei enthält reguläre Ausdrücke je Feld.
   - Du kannst weitere Patterns ergänzen, falls das Layout/Naming leicht abweicht.

3) Führe das Script aus:
   python /mnt/data/ocr_extract_screenshots.py --input /mnt/data --output /mnt/data/auswertung.csv --timezone Europe/Berlin

4) Ergebnis:
   - CSV unter /mnt/data/auswertung.csv
   - Spalten:
     timestamp; datetime_local; Gesendete Bitrate; Empfangene Bitrate; Gesendete Bildfrequenz;
     Gesendete Auflösung; Roundtripzeit; Gesendete Pakete; Gesendeter Codec; ocr_confidence; source_file

Hinweise:
- Das Script versucht zuerst EasyOCR, fällt dann auf pytesseract zurück.
- Falls weder installiert ist, installiere lokal:
    pip install easyocr Pillow
  (Für pytesseract zusätzlich das Systempaket 'tesseract-ocr')
- Die OCR ist robust bei konstantem Layout. Bei Bedarf kannst Du in der config weitere Patterns hinzufügen.

