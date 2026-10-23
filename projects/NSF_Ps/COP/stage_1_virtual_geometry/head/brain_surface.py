"""
COP - Configurable Optodes Placement

Stage 1: Virtual Anatomical Geometry
Module: Brain Surface

Purpose
-------
Load and visualize the high-resolution cortical surface
from the ICBM152 anatomical head model.

Current stage:
    - Real anatomical cortical geometry
    - Interactive 3D visualization
    - No scalp yet
    - No optodes yet
    - No optical simulation yet

Coordinate convention:
    +X = Right
    +Y = Anterior
    +Z = Superior
"""

from pathlib import Path

import pyvista as pv


# ============================================================
# 1. PROJECT PATHS
# ============================================================

# Current file:
#
# COP/
# └── stage_1_virtual_geometry/
#     └── head/
#         └── brain_surface.py
#
# parents[0] -> head/
# parents[1] -> stage_1_virtual_geometry/
# parents[2] -> COP/

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ICBM152 anatomical model folder
HEAD_MODEL_DIR = PROJECT_ROOT / "hm_icbm152"


# High-resolution cortical surface
BRAIN_MESH_PATH = HEAD_MODEL_DIR / "cortex_pial_high.obj"


# ============================================================
# 2. LOAD BRAIN SURFACE
# ============================================================

def load_brain_surface():
    """
    Load the high-resolution ICBM152 cortical surface.

    Returns
    -------
    brain : pyvista.PolyData
        Triangular cortical surface mesh.
    """

    print("\n========================================")
    print("COP - Loading ICBM152 Cortical Surface")
    print("========================================")

    print(f"\nProject root:\n{PROJECT_ROOT}")

    print(f"\nBrain mesh path:\n{BRAIN_MESH_PATH}")

    # --------------------------------------------------------
    # Check that the anatomical file exists
    # --------------------------------------------------------

    if not BRAIN_MESH_PATH.exists():

        raise FileNotFoundError(
            "\nICBM152 cortical mesh was not found.\n\n"
            f"Expected location:\n{BRAIN_MESH_PATH}\n"
        )

    # --------------------------------------------------------
    # Load OBJ mesh
    # --------------------------------------------------------

    brain = pv.read(BRAIN_MESH_PATH)

    print("\nBrain loaded successfully.")

    print("\nMesh information:")
    print(f"Number of points : {brain.n_points}")
    print(f"Number of cells  : {brain.n_cells}")

    print("\nMesh bounds:")
    print(brain.bounds)

    print("========================================\n")

    return brain


# ============================================================
# 3. VISUALIZE BRAIN
# ============================================================

def visualize_brain(brain):
    """
    Display the ICBM152 cortical surface interactively.

    Mouse controls
    --------------
    Left drag:
        Rotate

    Right drag:
        Zoom

    Middle drag:
        Pan

    Mouse wheel:
        Zoom
    """

    # --------------------------------------------------------
    # Create interactive 3D window
    # --------------------------------------------------------

    plotter = pv.Plotter(
        window_size=(1100, 850)
    )

    # --------------------------------------------------------
    # Add cortical mesh
    # --------------------------------------------------------

    plotter.add_mesh(
        brain,
        color="lightcoral",
        smooth_shading=True,
        show_edges=False,
        opacity=1.0
    )

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    plotter.add_text(
        "COP Stage 1 - ICBM152 Cortical Surface",
        position="upper_left",
        font_size=12
    )

    # --------------------------------------------------------
    # Coordinate axes
    # --------------------------------------------------------

    plotter.add_axes(
        xlabel="X: Left / Right",
        ylabel="Y: Posterior / Anterior",
        zlabel="Z: Inferior / Superior"
    )

    # --------------------------------------------------------
    # Grid
    # --------------------------------------------------------

    plotter.show_grid(
        xlabel="X (mm)",
        ylabel="Y (mm)",
        zlabel="Z (mm)"
    )

    # --------------------------------------------------------
    # Camera
    # --------------------------------------------------------

    plotter.reset_camera()

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    plotter.show()


# ============================================================
# 4. MAIN
# ============================================================

if __name__ == "__main__":

    brain = load_brain_surface()

    visualize_brain(brain)