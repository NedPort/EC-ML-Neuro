"""
Navigation crawler for CISS.
"""

import json


class NavigationCrawler:

    def __init__(self, api):
        self.api = api

    def build(self, case_id):
        """
        Retrieve the navigation tree from the API.
        """
        return self.api.get_case_tree(case_id)

    def save(self, tree, filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=4, ensure_ascii=False)

    def pretty_print(self, tree):
        print(json.dumps(tree, indent=4, ensure_ascii=False))
        