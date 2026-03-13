import csv
from pathlib import Path

out_dir = Path("output")
files = sorted([p for p in out_dir.glob("2026*.csv") if p.is_file()])

rows = []
for path in files:
    empty_count = 0
    filled_count = 0

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)

        for row in reader:
            value = (row.get("Roundtripzeit") or "").strip()
            if value == "":
                empty_count += 1
            else:
                filled_count += 1

    total = empty_count + filled_count
    rows.append((path.name, empty_count, filled_count, total))

rows.sort(key=lambda r: r[1], reverse=True)

quality_path = out_dir / "quality.csv"
with quality_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f, delimiter=";")
    writer.writerow(["Dateinamen", "Anzahl leer", "Anzahl gefüllt", "Summe"])
    writer.writerows(rows)

headers = ["Dateinamen", "Anzahl leer", "Anzahl gefüllt", "Summe"]
widths = [len(h) for h in headers]
for r in rows:
    for i, v in enumerate(r):
        widths[i] = max(widths[i], len(str(v)))

line = " | ".join(headers[i].ljust(widths[i]) for i in range(4))
sep = "-+-".join("-" * widths[i] for i in range(4))
print(line)
print(sep)
for r in rows:
    print(" | ".join(str(r[i]).ljust(widths[i]) for i in range(4)))

print(f"\nGespeichert: {quality_path}")

