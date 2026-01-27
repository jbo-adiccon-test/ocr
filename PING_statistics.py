import csv
from pathlib import Path
import math


def classify_ms(value_ms: float) -> str:
    if value_ms < 10:
        return "hervorragend"
    if value_ms < 20:
        return "sehr gut"
    if value_ms < 40:
        return "gut"
    if value_ms <= 80:
        return "ausreichend"
    return "ungenügend"


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

    categories = ["hervorragend", "sehr gut", "gut", "ausreichend", "ungenügend"]
    results: list[tuple[str, dict[str, float], dict[str, tuple[float, str]]]] = []

    out_file = output_dir / "statisics.csv"

    for csv_path in sorted(output_dir.glob("*.csv")):
        if csv_path.name == out_file.name:
            continue

        counts = {c: 0 for c in categories}
        total = 0
        values: list[float] = []

        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if not reader.fieldnames or "Roundtripzeit" not in reader.fieldnames:
                continue

            for row in reader:
                value = parse_float(row.get("Roundtripzeit"))
                if value is None:
                    continue
                total += 1
                values.append(value)
                counts[classify_ms(value)] += 1

        if total == 0:
            percents = {c: 0.0 for c in categories}
        else:
            percents = {c: (counts[c] * 100.0 / total) for c in categories}

        stats: dict[str, tuple[float, str]] = {}
        if values:
            values.sort()
            mean_value = sum(values) / len(values)
            median_value = values[len(values) // 2] if len(values) % 2 == 1 else (
                values[len(values) // 2 - 1] + values[len(values) // 2]
            ) / 2
            p90_index = max(0, math.ceil(0.9 * len(values)) - 1)
            p90_value = values[p90_index]
        else:
            mean_value = 0.0
            median_value = 0.0
            p90_value = 0.0

        stats["Mittelwert"] = (mean_value, classify_ms(mean_value))
        stats["Median"] = (median_value, classify_ms(median_value))
        stats["P90"] = (p90_value, classify_ms(p90_value))

        results.append((csv_path.name, percents, stats))

    headers = [
        "Dateiname",
        "Mittelwert",
        "Mittelwert_Note",
        "Median",
        "Median_Note",
        "P90",
        "P90_Note",
    ] + categories
    with out_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(headers)
        for name, percents, stats in results:
            writer.writerow(
                [
                    name,
                    f"{stats['Mittelwert'][0]:.1f}",
                    stats["Mittelwert"][1],
                    f"{stats['Median'][0]:.1f}",
                    stats["Median"][1],
                    f"{stats['P90'][0]:.1f}",
                    stats["P90"][1],
                ]
                + [f"{percents[c]:.1f}" for c in categories]
            )

    if not results:
        print("Keine passenden CSV-Dateien gefunden.")
        return 0

    col_widths = [max(len("Dateiname"), max(len(name) for name, _, _ in results))]
    col_widths.extend(len(label) for label in headers[1:-len(categories)])
    col_widths.extend(max(len(label), 6) for label in categories)

    print(" | ".join(h.ljust(w) for h, w in zip(headers, col_widths)))
    print("-+-".join("-" * w for w in col_widths))
    for name, percents, stats in results:
        row = [
            name,
            f"{stats['Mittelwert'][0]:.1f}",
            stats["Mittelwert"][1],
            f"{stats['Median'][0]:.1f}",
            stats["Median"][1],
            f"{stats['P90'][0]:.1f}",
            stats["P90"][1],
        ] + [f"{percents[c]:.1f}%" for c in categories]
        print(" | ".join(value.ljust(width) for value, width in zip(row, col_widths)))

    print(f"\nGespeichert: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
