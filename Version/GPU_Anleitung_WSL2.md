# GPU-Nutzung für EasyOCR/PyTorch unter **WSL2** (Windows Subsystem for Linux)

Diese Anleitung zeigt, wie du unter **Windows 11** mit **WSL2 (Ubuntu)** und **NVIDIA‑GPU** (z. B. T550) EasyOCR + PyTorch auf der GPU nutzt.

---

## 1) Voraussetzungen (Windows-Seite)
- **Windows 11** (empfohlen: aktuelle Version)
- **WSL2** installiert
- Aktueller **NVIDIA‑Grafiktreiber** (Studio/Game) mit WSL‑GPU‑Support

### Schnell einrichten/prüfen (PowerShell als Admin)
```powershell
wsl --install                         # installiert WSL + Ubuntu (falls noch nicht vorhanden)
wsl --update                          # aktualisiert den WSL‑Kernel
wsl --status                          # zeigt Versionen/Infos
nvidia-smi                            # prüft NVIDIA‑Treiber auf Windows-Seite
```
> Wenn `nvidia-smi` in PowerShell nicht läuft, Treiber aktualisieren (NVIDIA GeForce/Studio).

---

## 2) WSL2 (Ubuntu) vorbereiten
Starte **Ubuntu** über das Startmenü (WSL2).

### (optional) Systempakete aktualisieren
```bash
sudo apt update && sudo apt upgrade -y
# Für OpenCV/EasyOCR gelegentlich nötig:
sudo apt install -y libgl1 libglib2.0-0
```

### GPU‑Durchreichung prüfen
```bash
ls /dev/nvidia*
# Optional (falls verfügbar):
nvidia-smi
```
> In WSL2 werden die CUDA‑Bibliotheken vom Windows‑Treiber bereitgestellt. Ein separates CUDA Toolkit in WSL ist **nicht** erforderlich.

---

## 3) Conda‑Umgebung anlegen (in WSL2/Ubuntu)
```bash
conda create -n ocr_env python=3.10
conda activate ocr_env
```

> Falls `conda` noch nicht installiert ist, Miniconda in WSL2 installieren (Download-Skript von Anaconda/Miniconda verwenden). Danach `conda init bash && exec bash` ausführen.

---

## 4) PyTorch (CUDA) + EasyOCR installieren
**Empfohlene Conda‑Variante:**
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

**Alternative (pip statt conda):**
```bash
pip uninstall -y torch torchvision torchaudio
pip cache purge
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install easyocr pillow python-dateutil
```

---

## 5) Skript mit GPU starten
Dein Skript unterstützt `--gpu`:
- `auto` (Standard) → nutzt GPU, wenn verfügbar
- `on` → GPU erzwingen
- `off` → CPU

**Beispiel (WSL2/Ubuntu):**
```bash
python ocr_extract_screenshots.py   --input /mnt/c/Users/DeinName/Screenshots   --output /mnt/c/Users/DeinName/auswertung.csv   --timezone Europe/Berlin   --config /mnt/c/Users/DeinName/ocr_config.json   --gpu on
```
> Hinweis: Windows‑Pfade sind in WSL2 unter `/mnt/c/...` eingebunden.

Beim Start solltest du sehen:
```
[INFO] EasyOCR GPU: True (torch.cuda.is_available=True)
[INFO] CUDA Device: NVIDIA <dein Modell>
```

---

## 6) Troubleshooting (kurz)
- **`CUDA available: False` in WSL** → meist CPU‑Build von PyTorch installiert oder Windows‑Treiber/WSL‑Kernel veraltet.  
  - In PowerShell: `wsl --update` und Treiber aktualisieren; anschließend PyTorch mit CUDA wie oben installieren.  
- **`nvidia-smi` fehlt in WSL** → nicht schlimm, wichtig ist `torch.cuda.is_available() == True`.  
- **Performance gering** → sicherstellen, dass `--gpu on` gesetzt ist und die GPU erkannt wird.  
- **Import-/libGL‑Fehler** → `sudo apt install -y libgl1 libglib2.0-0` (bereits oben).

---

## 7) Best Practices
- Daten auf **Windows‑Seite** ablegen und über `/mnt/c/...` referenzieren, damit du Ergebnisse leicht wiederfindest.
- Für reproduzierbare Setups eine `requirements.txt` (pip) oder `environment.yml` (conda) pflegen.

Viel Erfolg! Wenn du magst, erstelle ich dir auch eine `environment.yml` für das Conda‑Setup in WSL2.
