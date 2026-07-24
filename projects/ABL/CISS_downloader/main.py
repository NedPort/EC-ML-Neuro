from pathlib import Path

from src.api.client import CISSApi
from src.crawler.navigation import NavigationCrawler
from src.crawler.tree import get_downloadable_nodes

CASE_ID = 2400271

api = CISSApi()

crawler = NavigationCrawler(api)

# Build the navigation tree
tree = crawler.build(CASE_ID)

# Find all downloadable nodes
downloadable_nodes = get_downloadable_nodes(tree)

print(f"Found {len(downloadable_nodes)} downloadable nodes.\n")

for node in downloadable_nodes:
    print(f"Name: {node['name']}")
    print(f"Component: {node['componentName']}")
    print(f"Params: {node['params']}")
    print("-" * 50)

# Save the navigation tree
output_dir = Path("data/raw") / str(CASE_ID)
output_dir.mkdir(parents=True, exist_ok=True)

crawler.save(
    tree,
    output_dir / "navigation_tree.json"
)

api.close()
