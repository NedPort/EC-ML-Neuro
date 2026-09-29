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

    raise RuntimeError("Could not access the Windows clipboard.")


def dismiss_report_generation_error() -> str | None:
    """Dismiss Bosch's internal report-generation failure dialog."""

    dialog = Desktop(backend="uia").window(
        title="GenerateReportAutomated"
    )

    if not dialog.exists(timeout=0.1):
        return None

    try:
        dialog.set_focus()

        ok_button = dialog.child_window(
            title="OK",
            control_type="Button",
        )

        if ok_button.exists(timeout=1):
            ok_button.click_input()
        else:
            dialog.type_keys("{ENTER}")

        time.sleep(0.5)

    except Exception as error:
        return (
            "Bosch CDR report-generation error dialog appeared, "
            f"but could not be dismissed: {type(error).__name__}: {error}"
        )

    return (
        "Bosch CDR report-generation error: "
        "GenerateReportAutomated, Error 91 "
        "(Object variable or With block variable not set)."
    )


def raise_if_report_generation_error() -> None:
    error_message = dismiss_report_generation_error()

    if error_message is not None:
        raise RuntimeError(error_message)


def wait_for_completed_file(
    file_path: Path,
    timeout_seconds: float = 45,
    poll_seconds: float = 0.5,
) -> bool:
    """Wait until a non-empty output file has a stable size."""

    deadline = time.monotonic() + timeout_seconds
    previous_size = -1
    stable_checks = 0

    while time.monotonic() < deadline:
        raise_if_report_generation_error()

        if file_path.is_file():
            current_size = file_path.stat().st_size

            if current_size > 0 and current_size == previous_size:
                stable_checks += 1

                if stable_checks >= 2:
                    return True
            else:
                stable_checks = 0
                previous_size = current_size

        time.sleep(poll_seconds)

    return False


def get_main_window(app: Application):
    main_window = app.window(
        title_re=r".*Crash Data Retrieval.*"
    )

    main_window.wait("visible", timeout=30)
    main_window.set_focus()

    return main_window


def navigate_top_address_bar(
    dialog,
    folder_path: Path,
) -> None:
    """Navigate using the dialog's top address bar."""

    copy_to_clipboard(str(folder_path))

    dialog.set_focus()
    dialog.type_keys("^l")
    time.sleep(0.4)

    dialog.type_keys("^v")
    time.sleep(0.4)

    dialog.type_keys("{ENTER}")
    time.sleep(1.5)


def get_file_name_box(dialog):
    file_name_combo = dialog.child_window(
        auto_id="1148",
        control_type="ComboBox",
    )

    return file_name_combo.child_window(
        control_type="Edit",
    )


def open_cdrx_report(
    app: Application,
    cdrx_file: Path,
) -> None:
    main_window = get_main_window(app)
    raise_if_report_generation_error()

    main_window.type_keys("^o")
    time.sleep(2)

    open_dialog = Desktop(backend="uia").window(
        title="OPEN CDR FILE"
    )

    open_dialog.wait("visible", timeout=15)
    open_dialog.set_focus()

    navigate_top_address_bar(
        dialog=open_dialog,
        folder_path=cdrx_file.parent,
    )

    file_name_box = get_file_name_box(open_dialog)
    file_name_box.set_edit_text(cdrx_file.name)
    file_name_box.set_focus()
    file_name_box.type_keys("{ENTER}")

    # Allow Bosch CDR time to load the selected CDRX.
    time.sleep(5)
    raise_if_report_generation_error()


def wait_for_export_dialog_or_bosch_error(
    dialog_title_pattern: str,
    timeout_seconds: float = 20,
):
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        cdr_error = dismiss_report_generation_error()

        if cdr_error is not None:
            raise RuntimeError(cdr_error)

        for backend in ("win32", "uia"):
            try:
                save_dialog = Desktop(backend=backend).window(
                    title_re=dialog_title_pattern
                )

                if save_dialog.exists(timeout=0.2):
                    save_dialog.wait("visible", timeout=2)
                    save_dialog.set_focus()
                    return save_dialog

            except Exception:
                continue

        time.sleep(0.3)

    raise TimeoutError(
        f"Timed out waiting for export dialog: "
        f"{dialog_title_pattern}"
    )


def open_export_dialog(
    main_window,
    menu_down_count: int,
    dialog_title_pattern: str,
):
    main_window.set_focus()
    main_window.type_keys("%f")
    time.sleep(0.4)

    main_window.type_keys(
        f"{{DOWN {menu_down_count}}}"
    )
    main_window.type_keys("{ENTER}")

    return wait_for_export_dialog_or_bosch_error(
        dialog_title_pattern=dialog_title_pattern,
    )


def cancel_overwrite_confirmation() -> bool:
    """Click No if Bosch asks to overwrite an existing export."""

    confirmation_titles = [
        r"(?i)^pdf write$",
        r"(?i)^confirm save as$",
    ]

    for title_pattern in confirmation_titles:
        dialog = Desktop(backend="uia").window(
            title_re=title_pattern
        )

        if not dialog.exists(timeout=0.5):
            continue

        try:
            dialog.set_focus()

            no_button = dialog.child_window(
                title="No",
                control_type="Button",
            )

            if no_button.exists(timeout=1):
                no_button.click_input()
            else:
                dialog.type_keys("{ESC}")

            time.sleep(1)
            return True

        except Exception:
            dialog.type_keys("{ESC}")
            time.sleep(1)
            return True

    return False


def save_to_export_directory(
    save_dialog,
    export_directory: Path,
) -> bool:
    """Navigate to cdr_exports and save using Bosch's native filename."""

    navigate_top_address_bar(
        dialog=save_dialog,
        folder_path=export_directory,
    )

    save_dialog.type_keys("%s")
    time.sleep(1)

    return cancel_overwrite_confirmation()


def save_report_as_pdf(
    app: Application,
    pdf_file: Path,
) -> str:
    if pdf_file.is_file():
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

    if save_to_export_directory(
        save_dialog=save_dialog,
        export_directory=pdf_file.parent,
    ):
        return "already_present_not_overwritten"

    if wait_for_completed_file(pdf_file):
        return "exported"

    return "not_created"


def save_report_as_csv(
    app: Application,
    csv_file: Path,
) -> str:
    if csv_file.is_file():
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

    if save_to_export_directory(
        save_dialog=save_dialog,
        export_directory=csv_file.parent,
    ):
        return "already_present_not_overwritten"

    if wait_for_completed_file(csv_file):
        return "exported"

    return "not_created_or_not_supported"


def close_cdr(app: Application) -> None:
    try:
        for backend in ("win32", "uia"):
            for title_pattern in (
                r"(?i)^save report$",
                r"(?i)^save as csv file$",
                r"(?i)^open cdr file$",
            ):
                dialog = Desktop(backend=backend).window(
                    title_re=title_pattern
                )

                if dialog.exists(timeout=0.2):
                    dialog.set_focus()
                    dialog.type_keys("{ESC}")
                    time.sleep(0.5)

        dismiss_report_generation_error()

        main_window = get_main_window(app)
        main_window.type_keys("%{F4}")
        time.sleep(1)

        app.kill()

    except Exception:
        try:
            app.kill()
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

    if pdf_file.is_file() and csv_file.is_file():
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

        # Always skip files that already have both exports.
        if pdf_file.is_file() and csv_file.is_file():
            continue

        # Skip known PDF-only reports only when their PDF remains present.
        if (
            row.get("cdr_export_status") == "pdf_only_available"
            and pdf_file.is_file()
        ):
            continue

        row["cdrx_source_path"] = str(cdrx_file)
        pending_rows.append(row)

    return pending_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export pending Bosch CDRX files to PDF and CSV."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of pending CDRX files to process.",
    )

    arguments = parser.parse_args()

    if arguments.limit < 1:
        raise SystemExit("--limit must be at least 1.")

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

        print(f"PDF status: {result['pdf_status']}")
        print(f"CSV status: {result['csv_status']}")

        if result["error_message"]:
            print(f"Error: {result['error_message']}")

    print("\nBatch complete.")

    for status, count in sorted(summary.items()):
        print(f"{status}: {count}")

    print(f"\nAttempt log: {ATTEMPT_LOG_FILE}")


if __name__ == "__main__":
    main()