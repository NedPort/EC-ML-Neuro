"""
Tree utilities for CISS navigation.
"""


def get_downloadable_nodes(node):
    """
    Return all nodes that contain downloadable data.
    """
    downloadable = []

    if node["dataAvailable"]:
        downloadable.append(node)

    for child in node["children"]:
        downloadable.extend(get_downloadable_nodes(child))

    return downloadable
