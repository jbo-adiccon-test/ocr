# GPU-Nutzung für EasyOCR/PyTorch (Windows 11 · Conda)

Diese Anleitung zeigt, wie du **EasyOCR** mit **NVIDIA-GPU** (z. B. T550) nutzt und wie du das Skript mit aktivierter GPU startest.

---

## 1) Voraussetzungen
- **Windows 11**
- **NVIDIA-Treiber** aktuell (GeForce/Studio)
- **Conda-Umgebung** (Anaconda/Miniconda)
- Python **3.10** (empfohlen)

---

## 2) CUDA-fähiges PyTorch + EasyOCR installieren (Conda, empfohlen)
```bash
conda activate ocr_env
conda install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia
pip install easyocr pillow python-dateutil
```

**Schnelltest (GPU verfügbar?):**
```bash
python - << "PY"
import torch
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("Device:", torch.cuda.get_device_name(0))
PY
```

> Hinweis: Du brauchst kein separates CUDA Toolkit zu installieren – die PyTorch-Wheels bringen die benötigten CUDA-Runtimes mit.

---

## 3) Skript mit GPU starten
Das Skript unterstützt die Option `--gpu`:
- `auto` (Standard): nutzt GPU, wenn verfügbar
- `on`: erzwingt GPU-Nutzung
- `off`: CPU-Nutzung

**Beispielaufruf (GPU an):**
```bash
python ocr_extract_screenshots.py ^
  --input C:\Pfad\zu\Screenshots ^
  --output C:\Pfaduswertung.csv ^
  --timezone Europe/Berlin ^
  --config C:\Pfad\zu\ocr_config.json ^
  --gpu on
```

Beim Start siehst du eine Infozeile wie:
```
[INFO] EasyOCR GPU: True (torch.cuda.is_available=True)
[INFO] CUDA Device: NVIDIA T550
```

---

## 4) Troubleshooting (kurz)
- **CUDA available: False** → meist CPU-Build von PyTorch installiert. Erst `pip uninstall -y torch torchvision torchaudio`, dann CUDA-Build wie oben installieren.
- **CUDA initialization error** → NVIDIA-Treiber veraltet. Treiber aktualisieren und erneut testen.
- **OCR langsam** → prüfen, ob `--gpu on` gesetzt ist und `torch.cuda.is_available()` wirklich `True` liefert.

