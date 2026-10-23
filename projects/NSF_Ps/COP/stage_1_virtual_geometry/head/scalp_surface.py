"""
COP - Configurable Optodes Placement

Stage 1: Virtual Anatomical Geometry
Module: Scalp Surface

Purpose
-------
Load and visualize the scalp surface
from the ICBM152 anatomical head model.

Current stage:
    - Real anatomical scalp geometry
    - Interactive 3D visualization
    - No brain overlay yet
    - No optodes yet
    - No optical simulation yet
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
#         └── scalp_surface.py
#
# parents[2] -> COP/

PROJECT_ROOT = Path(__file__).resolve().parents[2]

HEAD_MODEL_DIR = PROJECT_ROOT / "hm_icbm152"

SCALP_MESH_PATH = HEAD_MODEL_DIR / "mask_scalp.obj"


# ============================================================
# 2. LOAD SCALP SURFACE
# ============================================================

def load_scalp_surface():
    """
    Load the ICBM152 scalp surface.

    Returns
    -------
    scalp : pyvista.PolyData
        Triangular scalp surface mesh.
    """

    print("\n======================================")
    print("COP - Loading ICBM152 Scalp Surface")
    print("======================================")

    print(f"\nScalp mesh path:\n{SCALP_MESH_PATH}")

    # --------------------------------------------------------
    # Check file
    # --------------------------------------------------------

    if not SCALP_MESH_PATH.exists():

        raise FileNotFoundError(
            "\nICBM152 scalp mesh was not found.\n\n"
            f"Expected location:\n{SCALP_MESH_PATH}\n"
        )

    # --------------------------------------------------------
    # Load OBJ
    # --------------------------------------------------------

    scalp = pv.read(SCALP_MESH_PATH)

    print("\nScalp loaded successfully.")

    print("\nMesh information:")
    print(f"Number of points : {scalp.n_points}")
    print(f"Number of cells  : {scalp.n_cells}")

    print("\nMesh bounds:")
    print(scalp.bounds)

    print("======================================\n")

    return scalp


# ============================================================
# 3. VISUALIZE SCALP
# ============================================================

def visualize_scalp(scalp):
    """
    Display the ICBM152 scalp surface interactively.
    """

    plotter = pv.Plotter(
        window_size=(1100, 850)
    )

    # --------------------------------------------------------
    # Add scalp mesh
    # --------------------------------------------------------

    plotter.add_mesh(
        scalp,
        color="lightgray",
        smooth_shading=True,
        show_edges=False,
        opacity=0.65
    )

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    plotter.add_text(
        "COP Stage 1 - ICBM152 Scalp Surface",
        position="upper_left",
        font_size=12
    )

    # --------------------------------------------------------
    # Anatomical axes
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

    plotter.reset_camera()

    plotter.show()


# ============================================================
# 4. MAIN
# ============================================================

if __name__ == "__main__":

    scalp = load_scalp_surface()

    visualize_scalp(scalp)