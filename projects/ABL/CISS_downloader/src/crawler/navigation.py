"""
Navigation crawler for CISS.
"""

import json


class NavigationCrawler:

    def __init__(self, api):
        self.api = api

    def build(self, case_id):
        navigation = self.api.get_case_tree(case_id)

        nodes = {}

        # Create all nodes
        for item in navigation:
            item["children"] = []
            nodes[item["id"]] = item

        root = None

        # Connect parent and child
        for node in nodes.values():
            if node["parentId"] is None:
                root = node
            else:
                parent = nodes.get(node["parentId"])
                if parent:
                    parent["children"].append(node)

        return root
    
    def save(self, tree, filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=4, ensure_ascii=False)

    def pretty_print(self, tree):
        print(json.dumps(tree, indent=4, ensure_ascii=False))
        