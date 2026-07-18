import json

from src.api import get_documents

data = get_documents(15480)

print(json.dumps(data, indent=4))