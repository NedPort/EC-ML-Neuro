class NavigationNode:
    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.parent_id = data["parentId"]
        self.data_available = data["dataAvailable"]
        self.component_name = data["componentName"]
        self.params = data["params"]

        self.parent = None
        self.children = []

def build_navigation_tree(data):
    # Create all nodes
    nodes = {item["id"]: NavigationNode(item) for item in data}

    root = None

    # Connect parents and children
    for node in nodes.values():
        if node.parent_id is None:
            root = node
        else:
            parent = nodes[node.parent_id]
            node.parent = parent
            parent.children.append(node)

    return root
