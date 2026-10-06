from pathlib import Path

# Location of this Python file: fnirs_first_recording/src/main.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Raw fNIRS recording
file_path = PROJECT_ROOT / "data" / "raw" / "NedaSignal.txt"

print("Reading:", file_path)
print("File exists:", file_path.exists())

# Show the first 10 lines exactly as they were recorded
with open(file_path, "r") as file:
    for _ in range(10):
        print(file.readline().strip())