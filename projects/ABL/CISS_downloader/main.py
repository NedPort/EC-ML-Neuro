from pathlib import Path

from src.api.client import CISSApi
from src.crawler.navigation import NavigationCrawler

CASE_ID = 2400271

api = CISSApi()

crawler = NavigationCrawler(api)

tree = crawler.build(CASE_ID)

crawler.pretty_print(tree)

output_dir = Path("data/raw") / str(CASE_ID)
output_dir.mkdir(parents=True, exist_ok=True)

crawler.save(
    tree,
    output_dir / "navigation_tree.json"
)

api.close()
