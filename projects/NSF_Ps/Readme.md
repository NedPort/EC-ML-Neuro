## Create and Activate the shared environment:

python -m venv .venv
.\.venv\Scripts\Activate.ps1  


## Install all dependencies

uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt

uv run --active python .\src\main.py
