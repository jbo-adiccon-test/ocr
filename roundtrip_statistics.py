import csv
from pathlib import Path


def classify_ms(value_ms: float) -> str:
    if value_ms < 10:
        return "hervorragend"
    if value_ms < 20:
        return "sehr gut"
    if value_ms < 40:
        return "gut"
    if value_ms <= 80:
        return "ausreichend"
    return "schlecht"


def parse_float(value: str) -> float | None:
    if value is None:
        return None
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def main() -> int:
    output_dir = Path(__file__).resolve().parent / "output"
    if not output_dir.exists():
        print(f"Output-Verzeichnis nicht gefunden: {output_dir}")
        return 1

    categories = ["hervorragend", "sehr gut", "gut", "ausreichend", "schlecht"]
    results: list[tuple[str, dict[str, float]]] = []

    out_file = output_dir / "statisics.csv"

    for csv_path in sorted(output_dir.glob("*.csv")):
        if csv_path.name == out_file.name:
            continue

        counts = {c: 0 for c in categories}
        total = 0

        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if not reader.fieldnames or "Roundtripzeit" not in reader.fieldnames:
                continue

            for row in reader:
                value = parse_float(row.get("Roundtripzeit"))
                if value is None:
                    continue
                total += 1
                counts[classify_ms(value)] += 1

        if total == 0:
            percents = {c: 0.0 for c in categories}
        else:
            percents = {c: (counts[c] * 100.0 / total) for c in categories}

        results.append((csv_path.name, percents))

    headers = ["Dateiname"] + categories
    with out_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(headers)
        for name, percents in results:
            writer.writerow([name] + [f"{percents[c]:.2f}" for c in categories])

    if not results:
        print("Keine passenden CSV-Dateien gefunden.")
        return 0

    col_widths = [max(len("Dateiname"), max(len(name) for name, _ in results))]
    col_widths.extend(max(len(label), 6) for label in categories)

    print(" | ".join(h.ljust(w) for h, w in zip(headers, col_widths)))
    print("-+-".join("-" * w for w in col_widths))
    for name, percents in results:
        row = [name] + [f"{percents[c]:.2f}%" for c in categories]
        print(" | ".join(value.ljust(width) for value, width in zip(row, col_widths)))

    print(f"\nGespeichert: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
