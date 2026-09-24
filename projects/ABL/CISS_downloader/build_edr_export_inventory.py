from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DATA_ROOT = Path("data/temp")
OUTPUT_DIRECTORY = Path("data/processed/edr")

EXPORT_INVENTORY_FILE = OUTPUT_DIRECTORY / "edr_export_inventory.csv"
CSV_PROFILE_FILE = OUTPUT_DIRECTORY / "edr_csv_profile.csv"
METADATA_FILE = OUTPUT_DIRECTORY / "edr_export_inventory_metadata.json"

VEHICLE_PATTERN = re.compile(r"^vehicle\s+(\d+)$", re.IGNORECASE)
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def find_case_and_vehicle(export_directory: Path) -> tuple[str, str]:
    """
    Expected directory structure:
    data/temp/<case_id>/extracted/Docs/Vehicle <number>/cdr_exports/
    """
    vehicle_directory = export_directory.parent
    vehicle_match = VEHICLE_PATTERN.match(vehicle_directory.name)

    vehicle_number = ""
    if vehicle_match:
        vehicle_number = vehicle_match.group(1)

    case_id = ""
    path_parts = vehicle_directory.parts

    if "extracted" in path_parts:
        extracted_index = path_parts.index("extracted")

        if extracted_index > 0:
            case_id = path_parts[extracted_index - 1]

    return case_id, vehicle_number


def find_source_cdrx(
    vehicle_directory: Path,
    export_basename: str,
) -> tuple[str, str]:
    """
    Returns:
        source CDRX path,
        source-match status.
    """
    cdrx_files = sorted(
        path
        for path in vehicle_directory.glob("*")
        if path.is_file() and path.suffix.lower() == ".cdrx"
    )

    exact_matches = [
        path
        for path in cdrx_files
        if path.stem.casefold() == export_basename.casefold()
    ]

    if len(exact_matches) == 1:
        return str(exact_matches[0].resolve()), "exact_basename_match"

    if len(cdrx_files) == 1:
        return str(cdrx_files[0].resolve()), "single_cdrx_in_vehicle_directory"

    if len(cdrx_files) == 0:
        return "", "no_cdrx_found"

    return "", "multiple_cdrx_files_ambiguous"


def read_csv_text(csv_path: Path) -> tuple[str, str]:
    for encoding in TEXT_ENCODINGS:
        try:
            return csv_path.read_text(
                encoding=encoding,
                errors="strict",
            ), encoding
        except UnicodeDecodeError:
            continue

    return csv_path.read_text(
        encoding="latin-1",
        errors="replace",
    ), "latin-1_replacement"


def detect_delimiter(sample_text: str) -> str:
    candidate_delimiters = [",", "\t", ";", "|"]

    try:
        dialect = csv.Sniffer().sniff(
            sample_text,
            delimiters="".join(candidate_delimiters),
        )
        return dialect.delimiter
    except csv.Error:
        pass

    counts = {
        delimiter: sample_text.count(delimiter)
        for delimiter in candidate_delimiters
    }

    best_delimiter = max(
        counts,
        key=counts.get,
    )

    if counts[best_delimiter] == 0:
        return ","

    return best_delimiter


def profile_csv(csv_path: Path) -> dict[str, str]:
    text, encoding_used = read_csv_text(csv_path)
    delimiter = detect_delimiter(text[:10000])

    reader = csv.reader(
        text.splitlines(),
        delimiter=delimiter,
    )

    row_count = 0
    nonempty_row_count = 0
    maximum_column_count = 0
    first_nonempty_rows: list[list[str]] = []

    for row in reader:
        row_count += 1
        cleaned_row = [cell.strip() for cell in row]

        maximum_column_count = max(
            maximum_column_count,
            len(cleaned_row),
        )

        if any(cleaned_row):
            nonempty_row_count += 1

            if len(first_nonempty_rows) < 12:
                first_nonempty_rows.append(cleaned_row)

    first_row = first_nonempty_rows[0] if first_nonempty_rows else []

    return {
        "csv_encoding": encoding_used,
        "csv_delimiter": repr(delimiter),
        "csv_row_count": str(row_count),
        "csv_nonempty_row_count": str(nonempty_row_count),
        "csv_maximum_column_count": str(maximum_column_count),
        "csv_first_nonempty_row": " | ".join(first_row),
        "csv_preview_rows_json": json.dumps(
            first_nonempty_rows,
            ensure_ascii=False,
        ),
    }


def write_csv(
    output_path: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> None:
    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not DATA_ROOT.is_dir():
        raise FileNotFoundError(
            f"Data directory does not exist: {DATA_ROOT.resolve()}"
        )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    export_rows: list[dict[str, str]] = []
    csv_profile_rows: list[dict[str, str]] = []

    status_counts: Counter[str] = Counter()
    source_match_counts: Counter[str] = Counter()

    export_directories = sorted(
        path
        for path in DATA_ROOT.rglob("cdr_exports")
        if path.is_dir()
    )

    for export_directory in export_directories:
        case_id, vehicle_number = find_case_and_vehicle(
            export_directory
        )
        vehicle_directory = export_directory.parent

        grouped_exports: dict[str, dict[str, Path]] = {}

        for file_path in sorted(export_directory.iterdir()):
            if not file_path.is_file():
                continue

            suffix = file_path.suffix.lower()

            if suffix not in {".pdf", ".csv"}:
                continue

            basename_key = file_path.stem.casefold()

            grouped_exports.setdefault(
                basename_key,
                {},
            )[suffix] = file_path

        for files_by_type in grouped_exports.values():
            pdf_path = files_by_type.get(".pdf")
            csv_path = files_by_type.get(".csv")

            reference_path = csv_path or pdf_path

            if reference_path is None:
                continue

            export_basename = reference_path.stem

            source_cdrx_path, source_match_status = find_source_cdrx(
                vehicle_directory=vehicle_directory,
                export_basename=export_basename,
            )

            if pdf_path and csv_path:
                export_status = "pdf_and_csv_present"
            elif pdf_path:
                export_status = "pdf_only"
            else:
                export_status = "csv_only"

            row = {
                "case_id": case_id,
                "vehicle_number": vehicle_number,
                "vehicle_directory": str(
                    vehicle_directory.resolve()
                ),
                "export_directory": str(
                    export_directory.resolve()
                ),
                "export_basename": export_basename,
                "cdrx_source_path": source_cdrx_path,
                "cdrx_source_match_status": source_match_status,
                "pdf_export_path": (
                    str(pdf_path.resolve())
                    if pdf_path
                    else ""
                ),
                "pdf_file_size_bytes": (
                    str(pdf_path.stat().st_size)
                    if pdf_path
                    else ""
                ),
                "pdf_sha256": (
                    sha256_file(pdf_path)
                    if pdf_path
                    else ""
                ),
                "csv_export_path": (
                    str(csv_path.resolve())
                    if csv_path
                    else ""
                ),
                "csv_file_size_bytes": (
                    str(csv_path.stat().st_size)
                    if csv_path
                    else ""
                ),
                "csv_sha256": (
                    sha256_file(csv_path)
                    if csv_path
                    else ""
                ),
                "export_availability_status": export_status,
            }

            export_rows.append(row)
            status_counts[export_status] += 1
            source_match_counts[source_match_status] += 1

            if csv_path:
                csv_profile = profile_csv(csv_path)

                csv_profile_rows.append(
                    {
                        "case_id": case_id,
                        "vehicle_number": vehicle_number,
                        "export_basename": export_basename,
                        "cdrx_source_path": source_cdrx_path,
                        "csv_export_path": str(
                            csv_path.resolve()
                        ),
                        **csv_profile,
                    }
                )

    export_fieldnames = [
        "case_id",
        "vehicle_number",
        "vehicle_directory",
        "export_directory",
        "export_basename",
        "cdrx_source_path",
        "cdrx_source_match_status",
        "pdf_export_path",
        "pdf_file_size_bytes",
        "pdf_sha256",
        "csv_export_path",
        "csv_file_size_bytes",
        "csv_sha256",
        "export_availability_status",
    ]

    csv_profile_fieldnames = [
        "case_id",
        "vehicle_number",
        "export_basename",
        "cdrx_source_path",
        "csv_export_path",
        "csv_encoding",
        "csv_delimiter",
        "csv_row_count",
        "csv_nonempty_row_count",
        "csv_maximum_column_count",
        "csv_first_nonempty_row",
        "csv_preview_rows_json",
    ]

    write_csv(
        output_path=EXPORT_INVENTORY_FILE,
        rows=export_rows,
        fieldnames=export_fieldnames,
    )

    write_csv(
        output_path=CSV_PROFILE_FILE,
        rows=csv_profile_rows,
        fieldnames=csv_profile_fieldnames,
    )

    metadata = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "data_root": str(DATA_ROOT.resolve()),
        "export_directory_count": len(export_directories),
        "edr_export_record_count": len(export_rows),
        "csv_profile_record_count": len(csv_profile_rows),
        "export_availability_status_counts": dict(
            sorted(status_counts.items())
        ),
        "cdrx_source_match_status_counts": dict(
            sorted(source_match_counts.items())
        ),
        "outputs": {
            "export_inventory_csv": str(
                EXPORT_INVENTORY_FILE
            ),
            "csv_profile_csv": str(CSV_PROFILE_FILE),
        },
        "notes": [
            "This stage inventories and profiles exported EDR files only.",
            "It does not extract crash variables or merge EDR data into linked tables.",
            "PDF-only reports remain valid EDR evidence.",
            "CSV structure may vary by manufacturer, module, and Bosch report family.",
        ],
    }

    METADATA_FILE.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("EDR export inventory completed.")
    print(f"Export records: {len(export_rows)}")
    print(f"CSV profiles: {len(csv_profile_rows)}")
    print(f"Export inventory: {EXPORT_INVENTORY_FILE}")
    print(f"CSV profiles: {CSV_PROFILE_FILE}")
    print(f"Metadata: {METADATA_FILE}")

    print("\nExport availability:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")


if __name__ == "__main__":
    main()