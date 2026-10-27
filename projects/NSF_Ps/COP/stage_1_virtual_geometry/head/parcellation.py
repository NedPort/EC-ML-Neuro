"""
Stage 2 - Functional Brain
Step 1: Visualize the existing Schaefer cortical parcellation.

This script:
1. Loads the 25,000-vertex inflated cortical surface.
2. Loads the corresponding vertex-level parcel labels.
3. Loads the parcel colors supplied with the ICBM152 model.
4. Assigns an RGB color to every cortical vertex.
5. Displays the parcellated cortical surface.

No functional activity is introduced yet.
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
import pyvista as pv


# ============================================================
# 1. Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_DIR = PROJECT_ROOT / "hm_icbm152"

CORTEX_FILE = MODEL_DIR / "cortex_pial_inflated.obj"
VERTEX_FILE = MODEL_DIR / "brain_vertex_coordinates.csv"
COLOR_FILE = MODEL_DIR / "parcel_colors.json"

print(f"Project root : {PROJECT_ROOT}")
print(f"Model folder : {MODEL_DIR}")

# ============================================================
# 2. Load cortical surface
# ============================================================

brain = pv.read(CORTEX_FILE)

print("\n========================================")
print("INFLATED CORTICAL SURFACE")
print("========================================")
print(f"Number of mesh points : {brain.n_points}")
print(f"Number of mesh cells  : {brain.n_cells}")


# ============================================================
# 3. Load vertex information
# ============================================================

vertex_info = pd.read_csv(VERTEX_FILE)

print("\n========================================")
print("VERTEX INFORMATION")
print("========================================")
print(f"Number of CSV vertices : {len(vertex_info)}")
print(f"Columns                : {list(vertex_info.columns)}")


# ============================================================
# 4. Verify correspondence
# ============================================================

if brain.n_points != len(vertex_info):
    raise ValueError(
        "\nVertex mismatch!\n"
        f"Mesh points : {brain.n_points}\n"
        f"CSV rows    : {len(vertex_info)}\n"
        "The parcel labels cannot safely be attached to this mesh."
    )

print("\n[OK] Mesh and CSV both contain the same number of vertices.")


# Check that vertex IDs are ordered 0 ... N-1
expected_vertices = np.arange(brain.n_points)
actual_vertices = vertex_info["vertex"].to_numpy()

if not np.array_equal(actual_vertices, expected_vertices):
    raise ValueError(
        "The CSV 'vertex' column is not ordered from 0 to N-1."
    )

print("[OK] CSV vertex IDs correspond to mesh point indices.")


# ============================================================
# 5. Load Schaefer parcel colors
# ============================================================

with open(COLOR_FILE, "r", encoding="utf-8") as f:
    parcel_colors = json.load(f)

print("\n========================================")
print("PARCELLATION")
print("========================================")

parcel_labels = vertex_info["parcel"].astype(str).to_numpy()
unique_labels = np.unique(parcel_labels)

print(f"Unique labels in CSV       : {len(unique_labels)}")
print(f"Named colors in JSON       : {len(parcel_colors)}")


# ============================================================
# 6. Identify labels without supplied parcel colors
# ============================================================

missing_labels = sorted(
    set(unique_labels) - set(parcel_colors.keys())
)

if missing_labels:
    print("\nLabels without colors:")
    for label in missing_labels:
        print(f"  - {label}")
else:
    print("\n[OK] Every parcel label has a supplied color.")


# ============================================================
# 7. Assign RGB color to every vertex
# ============================================================

# Neutral gray is used only for labels that do not have a
# corresponding color in parcel_colors.json.
DEFAULT_COLOR = np.array([180, 180, 180], dtype=np.uint8)

vertex_rgb = np.empty((brain.n_points, 3), dtype=np.uint8)

for i, parcel in enumerate(parcel_labels):

    if parcel in parcel_colors:
        vertex_rgb[i] = np.asarray(
            parcel_colors[parcel],
            dtype=np.uint8
        )
    else:
        vertex_rgb[i] = DEFAULT_COLOR


# Attach RGB values directly to mesh points
brain.point_data["parcel_rgb"] = vertex_rgb


# ============================================================
# 8. Print a few examples
# ============================================================

print("\n========================================")
print("EXAMPLE VERTICES")
print("========================================")

for i in range(5):
    print(
        f"Vertex {i:5d} | "
        f"Parcel: {parcel_labels[i]:30s} | "
        f"RGB: {vertex_rgb[i]}"
    )


# ============================================================
# 9. Visualize parcellated cortex
# ============================================================

plotter = pv.Plotter(window_size=(1400, 900))

plotter.add_mesh(
    brain,
    scalars="parcel_rgb",
    rgb=True,
    smooth_shading=False,
    opacity=0.55,
)

plotter.add_text(
    "ICBM152 - Schaefer2018 Cortical Parcellation",
    position="upper_left",
    font_size=14,
)

plotter.add_axes()

plotter.show()

# ============================================================
# 10. Highlight Somatomotor Network A
# ============================================================

# Select all Schaefer parcels belonging to Somatomotor Network A
motor_mask = np.array([
    parcel.startswith("SomMotA_")
    for parcel in parcel_labels
])

print("\n========================================")
print("SOMATOMOTOR NETWORK A")
print("========================================")

motor_parcels = sorted(np.unique(parcel_labels[motor_mask]))

print(f"Number of SomMotA vertices : {motor_mask.sum()}")
print(f"Number of SomMotA parcels  : {len(motor_parcels)}")

print("\nSomMotA parcels:")
for parcel in motor_parcels:
    print(f"  - {parcel}")


# ============================================================
# 11. Create motor-network visualization
# ============================================================

# Everything starts as light gray
motor_rgb = np.full(
    (brain.n_points, 3),
    [190, 190, 190],
    dtype=np.uint8
)

# Restore original Schaefer colors only for SomMotA vertices
motor_rgb[motor_mask] = vertex_rgb[motor_mask]

brain.point_data["motor_rgb"] = motor_rgb


# ============================================================
# 12. Plot
# ============================================================

plotter = pv.Plotter(window_size=(1400, 900))

plotter.add_mesh(
    brain,
    scalars="motor_rgb",
    rgb=True,
    smooth_shading=False,
    opacity=0.45,
)

plotter.add_text(
    "ICBM152 - Somatomotor Network A",
    position="upper_left",
    font_size=14,
)

plotter.add_axes()

plotter.show()