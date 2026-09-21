from __future__ import annotations

import argparse
import csv
import time
import win32clipboard
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pywinauto import Application, Desktop


CDR_EXE = Path(
    r"C:\Program Files (x86)\Bosch\Crash Data Retrieval\CDR.EXE"
)

INVENTORY_FILE = Path(
    "data/processed/edr/cdrx_file_inventory.csv"
)

ATTEMPT_LOG_FILE = Path(
    "data/processed/edr/cdr_export_attempts.csv"
)


def copy_to_clipboard(text: str) -> None:
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()

            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text)
            finally:
                win32clipboard.CloseClipboard()

            return

        except Exception:
            time.sleep(0.5)

    raise RuntimeError(
        "Could not access the Windows clipboard."
    )


def get_main_window(app: Application):
    main_window = app.window(
        title_re=".*Crash Data Retrieval.*"
    )
    main_window.wait("visible", timeout=30)
    main_window.set_focus()

    return main_window


def navigate_top_address_bar(
    dialog,
    folder_path: Path,
) -> None:
    # Ctrl + L moves focus to the top address bar.
    # Clipboard paste preserves Windows backslashes exactly.
    copy_to_clipboard(str(folder_path))

    dialog.set_focus()
    dialog.type_keys("^l")
    time.sleep(1)

    dialog.type_keys("^v")
    time.sleep(1)

    dialog.type_keys("{ENTER}")
    time.sleep(3)


def open_cdrx_report(
    app: Application,
    cdrx_file: Path,
) -> None:
    main_window = get_main_window(app)

    main_window.type_keys("^o")
    time.sleep(2)

    open_dialog = Desktop(backend="uia").window(
        title="OPEN CDR FILE"
    )
    open_dialog.wait("visible", timeout=15)
    open_dialog.set_focus()

    # Top address bar: navigate to this vehicle folder.
    navigate_top_address_bar(
        dialog=open_dialog,
        folder_path=cdrx_file.parent,
    )

    # Bottom File name box: enter only the CDRX filename.
    file_name_combo = open_dialog.child_window(
        auto_id="1148",
        control_type="ComboBox",
    )
    file_name_box = file_name_combo.child_window(
        control_type="Edit",
    )

    file_name_box.set_edit_text(cdrx_file.name)
    file_name_box.set_focus()
    file_name_box.type_keys("{ENTER}")

    # Allow Bosch CDR to load the report.
    time.sleep(10)


def open_export_dialog(
    main_window,
    menu_down_count: int,
    dialog_title_pattern: str,
):
    main_window.set_focus()
    main_window.type_keys("%f")
    time.sleep(1)

    main_window.type_keys(
        f"{{DOWN {menu_down_count}}}"
    )
    main_window.type_keys("{ENTER}")
    time.sleep(2)

    save_dialog = Desktop(backend="uia").window(
        title_re=dialog_title_pattern
    )
    save_dialog.wait("visible", timeout=15)
    save_dialog.set_focus()

    return save_dialog


def cancel_overwrite_confirmation() -> bool:
    confirmation_titles = [
        r"(?i)^pdf write$",
        r"(?i)^confirm save as$",
    ]

    for title_pattern in confirmation_titles:
        dialog = Desktop(backend="uia").window(
            title_re=title_pattern
        )

        if not dialog.exists(timeout=1):
            continue

        no_button = dialog.child_window(
            title="No",
            control_type="Button",
        )

        if no_button.exists(timeout=1):
            no_button.click_input()
            time.sleep(2)
            return True

    return False


def save_to_export_directory(
    save_dialog,
    export_directory: Path,
) -> bool:
    # Top address bar: navigate to cdr_exports.
    navigate_top_address_bar(
        dialog=save_dialog,
        folder_path=export_directory,
    )

    # Bosch retains the source CDRX basename and
    # automatically applies PDF or CSV extension.
    save_dialog.type_keys("%s")
    time.sleep(2)

    return cancel_overwrite_confirmation()


def save_report_as_pdf(
    app: Application,
    pdf_file: Path,
) -> str:
    if pdf_file.exists():
        return "already_present"

    pdf_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    main_window = get_main_window(app)

    # File -> Save CDR Report as PDF.
    save_dialog = open_export_dialog(
        main_window=main_window,
        menu_down_count=6,
        dialog_title_pattern=r"(?i)^save report$",
    )

    overwrite_cancelled = save_to_export_directory(
        save_dialog=save_dialog,
        export_directory=pdf_file.parent,
    )

    if overwrite_cancelled:
        return "already_present_not_overwritten"

    time.sleep(15)

    if pdf_file.exists():
        return "exported"

    return "not_created"


def save_report_as_csv(
    app: Application,
    csv_file: Path,
) -> str:
    if csv_file.exists():
        return "already_present"

    csv_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    main_window = get_main_window(app)

    # File -> Save CDR Report as CSV Text File.
    save_dialog = open_export_dialog(
        main_window=main_window,
        menu_down_count=8,
        dialog_title_pattern=r"(?i)^save as csv file$",
    )

    overwrite_cancelled = save_to_export_directory(
        save_dialog=save_dialog,
        export_directory=csv_file.parent,
    )

    if overwrite_cancelled:
        return "already_present_not_overwritten"

    time.sleep(15)

    if csv_file.exists():
        return "exported"

    return "not_created_or_not_supported"


def close_cdr(app: Application) -> None:
    try:
        main_window = get_main_window(app)
        main_window.type_keys("%{F4}")
        time.sleep(3)
    except Exception:
        pass


def write_attempt_log(
    case_id: int,
    vehicle_number: int,
    cdrx_file: Path,
    pdf_file: Path,
    csv_file: Path,
    pdf_status: str,
    csv_status: str,
    error_message: str,
) -> None:
    ATTEMPT_LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    row = {
        "attempted_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "case_id": case_id,
        "vehicle_number": vehicle_number,
        "cdrx_source_path": str(cdrx_file),
        "pdf_export_path": str(pdf_file),
        "pdf_export_status": pdf_status,
        "csv_export_path": str(csv_file),
        "csv_export_status": csv_status,
        "error_message": error_message,
    }

    write_header = not ATTEMPT_LOG_FILE.exists()

    with ATTEMPT_LOG_FILE.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=row.keys(),
        )

        if write_header:
            writer.writeheader()

        writer.writerow(row)


def export_one_cdrx(
    case_id: int,
    vehicle_number: int,
    cdrx_file: Path,
) -> dict[str, str]:
    export_directory = cdrx_file.parent / "cdr_exports"

    pdf_file = export_directory / f"{cdrx_file.stem}.PDF"
    csv_file = export_directory / f"{cdrx_file.stem}.CSV"

    if pdf_file.exists() and csv_file.exists():
        return {
            "pdf_status": "already_present",
            "csv_status": "already_present",
            "error_message": "",
        }

    pdf_status = "not_attempted"
    csv_status = "not_attempted"
    error_message = ""
    app = None

    try:
        app = Application(backend="uia").start(
            cmd_line=f'"{CDR_EXE}"'
        )

        open_cdrx_report(
            app=app,
            cdrx_file=cdrx_file,
        )

        pdf_status = save_report_as_pdf(
            app=app,
            pdf_file=pdf_file,
        )

        if pdf_status in {
            "exported",
            "already_present",
            "already_present_not_overwritten",
        }:
            csv_status = save_report_as_csv(
                app=app,
                csv_file=csv_file,
            )
        else:
            csv_status = "not_attempted_pdf_not_available"

    except Exception as error:
        error_message = (
            f"{type(error).__name__}: {error}"
        )

        if pdf_status == "not_attempted":
            pdf_status = "failed"

        if csv_status == "not_attempted":
            csv_status = "not_attempted_due_to_error"

    finally:
        write_attempt_log(
            case_id=case_id,
            vehicle_number=vehicle_number,
            cdrx_file=cdrx_file,
            pdf_file=pdf_file,
            csv_file=csv_file,
            pdf_status=pdf_status,
            csv_status=csv_status,
            error_message=error_message,
        )

        if app is not None:
            close_cdr(app)

    return {
        "pdf_status": pdf_status,
        "csv_status": csv_status,
        "error_message": error_message,
    }


def load_pending_inventory_rows() -> list[dict[str, str]]:
    with INVENTORY_FILE.open(
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))

    pending_rows = []

    for row in rows:
        cdrx_file = Path(
            row["cdrx_source_path"]
        ).resolve()

        if not cdrx_file.is_file():
            continue

        export_directory = cdrx_file.parent / "cdr_exports"

        pdf_file = export_directory / f"{cdrx_file.stem}.PDF"
        csv_file = export_directory / f"{cdrx_file.stem}.CSV"

        if pdf_file.exists() and csv_file.exists():
            continue

        row["cdrx_source_path"] = str(cdrx_file)
        pending_rows.append(row)

    return pending_rows


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of pending CDRX files to process.",
    )

    arguments = parser.parse_args()

    pending_rows = load_pending_inventory_rows()

    if not pending_rows:
        print("No pending CDRX files were found.")
        return

    selected_rows = pending_rows[:arguments.limit]

    print(f"Pending CDRX files: {len(pending_rows)}")
    print(f"Processing this run: {len(selected_rows)}")

    summary = Counter()

    for index, row in enumerate(
        selected_rows,
        start=1,
    ):
        case_id = int(row["case_id"])
        vehicle_number = int(row["vehicle_number"])
        cdrx_file = Path(row["cdrx_source_path"])

        print("\n" + "=" * 70)
        print(
            f"[{index}/{len(selected_rows)}] "
            f"Case {case_id}, Vehicle {vehicle_number}"
        )
        print(cdrx_file)

        result = export_one_cdrx(
            case_id=case_id,
            vehicle_number=vehicle_number,
            cdrx_file=cdrx_file,
        )

        summary[
            f"PDF: {result['pdf_status']}"
        ] += 1

        summary[
            f"CSV: {result['csv_status']}"
        ] += 1

        print(
            f"PDF status: {result['pdf_status']}"
        )
        print(
            f"CSV status: {result['csv_status']}"
        )

        if result["error_message"]:
            print(
                f"Error: {result['error_message']}"
            )

    print("\nBatch complete.")

    for status, count in sorted(summary.items()):
        print(f"{status}: {count}")

    print(f"\nAttempt log: {ATTEMPT_LOG_FILE}")


if __name__ == "__main__":
    main()