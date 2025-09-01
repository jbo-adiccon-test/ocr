# GPU-Nutzung für EasyOCR/PyTorch (Linux · Conda)

Diese Anleitung zeigt, wie du **EasyOCR** auf Linux mit **NVIDIA‑GPU** nutzt und wie du das Skript mit aktivierter GPU startest.

---

## 1) Voraussetzungen
- Linux (z. B. Ubuntu/Debian/Fedora)
- **NVIDIA-Treiber** installiert und funktionsfähig
- **Conda** (Anaconda/Miniconda)
- Python **3.10** (empfohlen)

---

## 2) NVIDIA-Treiber prüfen/ installieren
**Prüfen:**
```bash
nvidia-smi
```
Wenn das nicht verfügbar ist oder Fehler zeigt, Treiber installieren (Beispiel **Ubuntu**):
```bash
sudo apt update
sudo ubuntu-drivers list
sudo ubuntu-drivers autoinstall
sudo reboot
```
Nach dem Neustart erneut prüfen:
```bash
nvidia-smi
```

> Für andere Distributionen (Fedora, Arch, …) bitte die dort übliche Treiberinstallation nutzen.

---

## 3) Conda-Umgebung mit Python 3.10 erstellen
```bash
conda create -n ocr_env python=3.10
conda activate ocr_env
```

---

## 4) CUDA-fähiges PyTorch + EasyOCR installieren (Conda, empfohlen)
```bash
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

> Du brauchst **kein separates CUDA Toolkit** – die PyTorch-Pakete enthalten die notwendigen CUDA-Runtimes.

### Alternative (pip statt conda)
Falls versehentlich CPU-Builds installiert sind, zuerst entfernen:
```bash
pip uninstall -y torch torchvision torchaudio
pip cache purge
```
Dann CUDA‑Build installieren (Beispiel **cu121**):
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install easyocr pillow python-dateutil
```

---

## 5) Skript mit GPU starten
Das Skript unterstützt `--gpu`:
- `auto` (Standard): nutzt GPU, wenn verfügbar
- `on`: erzwingt GPU-Nutzung
- `off`: CPU-Nutzung

**Beispiel:**
```bash
python ocr_extract_screenshots.py   --input /pfad/zu/screenshots   --output /pfad/auswertung.csv   --timezone Europe/Berlin   --config /pfad/ocr_config.json   --gpu on
```

Beim Start erscheinen Infozeilen wie:
```
[INFO] EasyOCR GPU: True (torch.cuda.is_available=True)
[INFO] CUDA Device: NVIDIA <dein Modell>
```

---

## 6) Troubleshooting (kurz)
- **CUDA available: False** → CPU‑Build installiert oder Treiber fehlt. PyTorch mit CUDA wie oben installieren und Treiber prüfen (`nvidia-smi`).  
- **CUDA initialization error / cuDNN-Fehler** → Treiber zu alt oder Versionskonflikt. Treiber aktualisieren, ggf. neu starten.  
- **OCR langsam** → `--gpu on` setzen und prüfen, dass `torch.cuda.is_available()` `True` liefert.  
- **Import-/libGL-Fehler** (selten):  
  ```bash
  sudo apt-get install -y libgl1 libglib2.0-0
  ```

---

## 7) Bonus: Headless/Server
Auf Servern ohne Desktop genügt der proprietäre NVIDIA-Treiber (ggf. über SSH installiert). Display/GUI ist nicht erforderlich.

---

Viel Erfolg! Wenn du magst, kann ich dir zusätzlich eine kurze Anleitung für **WSL2** (Windows Subsystem for Linux) erstellen.
