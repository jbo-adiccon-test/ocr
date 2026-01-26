# Dokumentation: OCR-Auswertung von Screenshots → CSV

Diese Dokumentation erklärt Zweck, Aufbau und Nutzung des Skripts **`ocr_extract_screenshots.py`** sowie die zugehörige Konfiguration **`ocr_config.json`**. Sie richtet sich an Personen, die die Auswertung **unter Windows 11 oder Linux (Debian/Ubuntu)** mit **Conda** durchführen. Außerdem wird beschrieben, **wie** das Skript arbeitet (OCR, Regex, Zeitstempel), **wo** Dateien liegen, **welche** Kommando-Parameter es gibt und **wie** man es für andere Screenshot-Layouts erweitert.

---

## 1) Ziel & Funktionsweise (Kurzüberblick)

- **Ziel:** Messwerte aus Screenshots per OCR lesen und als **CSV (UTF‑8, Semikolon)** exportieren.
- **Kernprinzip:** 
  1. **OCR** liest Textzeilen aus jedem Bild (EasyOCR bevorzugt, optional Pytesseract).
  2. **Regex-Patterns** aus `ocr_config.json` finden die gewünschten Werte in den OCR-Zeilen.
  3. **Zeitstempel** (10-stellig, UNIX-Sekunden) wird **aus dem Dateinamen** extrahiert.
  4. **CSV-Schreiben** mit Spalten: `timestamp`, `datetime_local`, die Messfelder, `ocr_confidence`, `source_file`.

---

## 2) Projektstruktur & Dateien

Empfohlene Struktur im Projektverzeichnis (beliebiger Pfad):

```
projekt/
├─ ocr_extract_screenshots.py      # Skript
├─ ocr_config.json                 # Regex-Konfiguration
├─ screenshots/                    # Eingabebilder
└─ output/                         # (optional) Ausgabedateien
```

- **Screenshots-Ordner:** `./screenshots`
- **Standard-Ausgabe:** CSV-Datei(n) deiner Wahl, z. B. `./output/auswertung.csv`

> **Timestamp im Dateinamen:** Der Dateiname enthält *irgendwo* einen **10‑stelligen UNIX‑Timestamp** (z. B. `…_1725206400.png`). Das Skript extrahiert die **erste** 10‑stellige Zahl, die **nicht** Teil einer längeren Ziffernfolge ist.

---

## 3) Installation (Windows 11 & Linux mit Conda)

### 3.1 Conda-Umgebung erstellen
```bash
conda create -n ocr_env python=3.10
conda activate ocr_env
```

### 3.2 Pakete installieren
**Empfohlen (Conda + Pip gemischt):**
```bash
# PyTorch mit CUDA (falls GPU genutzt werden soll)
# Windows & Linux (Debian/Ubuntu):
conda install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia

# Python-Pakete
pip install easyocr pillow python-dateutil
```

**Optional (Alternative OCR-Engine):**
- System: Tesseract installieren (Windows-Installer bzw. apt/yum, je nach OS)
- Python-Bindings: `pip install pytesseract`

**GPU-Schnelltest (optional):**
```bash
python - << "PY"
import torch
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("Device:", torch.cuda.get_device_name(0))
PY
```

> **Hinweis GPU:** Es **muss getestet werden**, ob eine GPU genutzt werden kann (Treiber & CUDA‑fähiges PyTorch). Wenn `torch.cuda.is_available()` **False** ist, läuft EasyOCR automatisch auf der CPU.

---

## 4) Ausführen des Skripts

### 4.1 Windows 11 (PowerShell/CMD)
```bash
python ocr_extract_screenshots.py ^
  --input .\screenshots ^
  --output .\output\auswertung.csv ^
  --timezone Europe/Berlin ^
  --config .\ocr_config.json ^
  --gpu auto
```

### 4.2 Linux (Debian/Ubuntu, Bash)
```bash
python ocr_extract_screenshots.py \
  --input ./screenshots \
  --output ./output/auswertung.csv \
  --timezone Europe/Berlin \
  --config ./ocr_config.json \
  --gpu auto
```

### 4.3 Wichtige Pfade
- **`--input`**: Ordner mit Bildern (Standard: `/mnt/data` im Beispiel; **bei euch:** `./screenshots`).
- **`--output`**: Ziel‑CSV (wird neu erstellt/überschrieben).
- **`--config`**: Pfad zur Regex‑Konfiguration (hier im Projektordner).
- **`--timezone`**: z. B. `Europe/Berlin` für das lesbare Datum.
- **`--gpu`**: `auto` (Standard), `on` (erzwingt GPU), `off` (nur CPU).

---

## 5) Kommando-Parameter (Referenz)

| Parameter      | Typ/Beispiel                 | Bedeutung |
|----------------|------------------------------|-----------|
| `--input`      | `./screenshots`              | Ordner mit Eingabebildern (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.tif`, `.tiff`) |
| `--output`     | `./output/auswertung.csv`    | Ziel‑CSV, wird erzeugt/überschrieben |
| `--timezone`   | `Europe/Berlin`              | Zeitzone für `datetime_local` (aus `timestamp`) |
| `--config`     | `./ocr_config.json`          | Pfad zur Regex‑Konfiguration |
| `--gpu`        | `auto`/`on`/`off`            | Steuert EasyOCR‑GPU‑Nutzung (nur wenn PyTorch CUDA verfügbar ist) |

---

## 6) Output-Format (CSV)

- **Kodierung:** UTF‑8  
- **Trenner:** Semikolon `;`  
- **Spalten (für diese Anwendung):**  
  1. `timestamp` (10‑stellige UNIX‑Sekunden aus Dateiname)  
  2. `datetime_local` (Umrechnung nach `--timezone`)  
  3. **Messfelder** aus `ocr_config.json` (z. B. „Gesendete Bitrate“, „Empfangene Bitrate“, …)  
  4. `ocr_confidence` (Durchschnittswert 0..1)  
  5. `source_file` (Dateiname des Bildes)

Beispiel (Kopfzeile):
```
timestamp;datetime_local;Gesendete Bitrate;Empfangene Bitrate;Gesendete Bildfrequenz;Gesendete Auflösung;Roundtripzeit;Gesendete Pakete;Gesendeter Codec;ocr_confidence;source_file
```

---

## 7) Wie das Skript intern arbeitet

1. **OCR-Engine wählen:**  
   - Versucht **EasyOCR** (bevorzugt). Falls nicht verfügbar, fällt auf **pytesseract** zurück.
   - Mit `--gpu` kann die GPU‑Nutzung gesteuert werden. Bei `auto` nutzt EasyOCR die GPU, wenn `torch.cuda.is_available()` `True` ist.

2. **Texterkennung:**  
   - OCR liefert eine Liste erkannter Textzeilen + Confidencewerte.
   - Aus allen Zeilen wird **ein großer String** gebaut, darauf werden Regex‑Patterns angewendet.

3. **Regex‑Matching:**  
   - `ocr_config.json` enthält je Feld: `label` (Spaltenname) und `patterns` (Liste von Regex‑Strings).
   - Das Skript nimmt pro Feld **das erste passende Pattern**.  
   - Wenn ein Pattern eine **benannte Gruppe `(?P<val>...)`** enthält, wird **diese** als Wert verwendet; sonst die **erste Klammergruppe**; fehlendenfalls der **gesamte Match**.

4. **Zeitstempel:**  
   - Aus dem Dateinamen wird mit Regex `(?<!\d)(\d{10})(?!\d)` die **erste** 10‑stellige Zahl extrahiert, **nicht** Teil einer längeren Ziffernfolge (d. h. an Zifferngrenzen).
   - Daraus wird `datetime_local` mittels `--timezone` berechnet.

5. **CSV-Schreiben:**  
   - Reihenfolge: `timestamp`, `datetime_local`, **Felder aus Config**, `ocr_confidence`, `source_file`.
   - Trenner `;`, Encoding UTF‑8.

---

## 8) GPU-Nutzung (NVIDIA) – Wichtig

- **Vor Nutzung testen**, ob CUDA‑fähiges PyTorch installiert ist und `torch.cuda.is_available()` `True` liefert (siehe Schnelltest in Abschnitt 3).  
- **Aufruf mit GPU:** `--gpu on`  
- **Fallback:** Wenn keine GPU verfügbar ist (oder `--gpu off`), läuft EasyOCR auf CPU.  
- **Treiber:** Aktuelle NVIDIA‑Treiber installieren (Windows: GeForce/Studio; Linux: `nvidia-smi` prüfen).

---

## 9) Konfiguration anpassen (neue Felder/Layouts)

Die Datei **`ocr_config.json`** steuert, **welche Felder** erkannt werden und **wie** sie extrahiert werden (Regex).

### 9.1 Struktur
```json
{
  "fields": [
    {
      "label": "Gesendete Bitrate",
      "patterns": [
        "Gesendete\\s*Bitrate\\s*[:\\-]?\\s*(?P<val>[0-9][0-9\\., ]*\\s*(?:kbps|mbps|MBit/s|...))"
      ]
    }
    // weitere Felder ...
  ]
}
```
> **Wichtig (JSON‑Escapes):** Backslashes müssen in JSON **verdoppelt** werden (`\s` → `\\s`, `\d` → `\\d`, `\.` → `\\.`).

### 9.2 Tipps für robuste Patterns
- Nutze **Labels** aus dem UI als Anker (z. B. `Gesendete\\s*Bitrate`), ggf. in `re.IGNORECASE` (wird im Skript gesetzt).
- Erfasse **Einheiten** variabel (z. B. `MBit/s`, `Mbps`, `mbps`, `kbps` …).
- Verwende **benannte Gruppe `(?P<val>...)`**, um exakt den Zahlen-/Textwert zu extrahieren.
- Erlaube **Leerzeichen** und **Dezimaltrennzeichen**: `[0-9][0-9\\., ]*`
- Beispiel für Auflösung: `\\d{3,5}\\s*[x×]\\s*\\d{3,5}(?:\\s*px)?`

### 9.3 Beispiel: Neues Feld ergänzen
```json
{
  "label": "Jitter",
  "patterns": [
    "Jitter\\s*[:\\-]?\\s*(?P<val>[0-9][0-9\\., ]*\\s*ms)"
  ]
}
```
Füge dieses Objekt in der Liste `fields` hinzu. Die Spalte erscheint automatisch in der CSV.

---

## 10) Troubleshooting (kurz)

- **GPU wird nicht genutzt (langsam):**  
  - `python -c "import torch; print(torch.cuda.is_available())"` → wenn `False`, CUDA‑Build installieren (siehe Abschnitt 3.2).  
  - Windows‑/Linux‑Treiber aktualisieren und erneut testen.  
  - Mit `--gpu on` GPU erzwingen.

- **Spalten bleiben leer:**  
  - Label im Screenshot weicht ab → **Regex anpassen/erweitern** in `ocr_config.json`.  
  - Backslashes in JSON nicht korrekt escaped → **`\\` statt `\`** verwenden.  
  - OCR‑Qualität niedrig → Bildschärfe/Zoom prüfen; ggf. Bildschirmmodus, Kontrast, Farbdarstellung optimieren.

- **Timestamp leer:**  
  - Dateiname enthält keine **10‑stellige** Zahl → Benennung anpassen oder (optional) Timestamp‑Logik erweitern.  
  - Mehrere 10‑stellige Zahlen im Namen → es wird die **erste** genommen. Ggf. Regex anpassen.

- **Fehler „Konfig nicht gefunden“:**  
  - Pfad in `--config` prüfen (relativ zum Projektordner oder absolut angeben).

---

## 11) Best Practices

- **Einheitliche Dateinamen** mit 10‑stelliger UNIX‑Zeit (`XXXXXXXXXX`) sicherstellen.  
- **Projektordner versionieren** (z. B. Git) und Änderungen an `ocr_config.json` dokumentieren.  
- **Beispielbilder** je Layout aufbewahren, um Regex schnell testen zu können.  
- Bei **neuen Screenshot‑Layouts** die Konfig kopieren und Felder/Patterns projektspezifisch anpassen.

---

## 12) Beispielkommandos (copy & paste)

**Windows 11:**
```bash
python ocr_extract_screenshots.py ^
  --input .\screenshots ^
  --output .\output\auswertung.csv ^
  --timezone Europe/Berlin ^
  --config .\ocr_config.json ^
  --gpu on
```

**Linux (Debian/Ubuntu):**
```bash
python ocr_extract_screenshots.py \
  --input ./screenshots \
  --output ./output/auswertung.csv \
  --timezone Europe/Berlin \
  --config ./ocr_config.json \
  --gpu on
```

---

### Kontakt & Übergabe
Diese Dokumentation zusammen mit `ocr_extract_screenshots.py` und `ocr_config.json` im Projektordner an die Assistenz übergeben. Für neue Use‑Cases nur `ocr_config.json` anpassen – das Skript bleibt gleich.
