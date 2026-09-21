from pathlib import Path
import time

from pywinauto import Application, Desktop


CDR_EXE = Path(
    r"C:\Program Files (x86)\Bosch\Crash Data Retrieval\CDR.EXE"
)

OUTPUT_FILE = Path("cdr_open_dialog_controls.txt").resolve()

app = Application(backend="uia").start(f'"{CDR_EXE}"')

main_window = app.window(title_re=".*Crash Data Retrieval.*")
main_window.wait("visible", timeout=30)
main_window.set_focus()
main_window.type_keys("^o")

time.sleep(2)

open_dialog = Desktop(backend="uia").window(
    title="OPEN CDR FILE"
)
open_dialog.wait("visible", timeout=15)

open_dialog.print_control_identifiers(
    depth=5,
    filename=str(OUTPUT_FILE),
)

print(f"Created: {OUTPUT_FILE}")
input("Leave the Open CDR File dialog visible. Press Enter here to finish.")