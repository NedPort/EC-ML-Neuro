"""
COP - Configurable Optodes Placement

Stage 1: Virtual Anatomical Geometry
Module: Create Head

Purpose
-------
Combine the ICBM152 cortical surface and scalp surface
into one interactive anatomical visualization.

The scalp is displayed semi-transparently so that the
cortical surface remains visible inside the head.

Current stage:
    - Real ICBM152 cortical surface
    - Real ICBM152 scalp surface
    - Interactive visualization
    - No optodes yet
    - No optical sensitivity yet
"""

import sys
from pathlib import Path

import pyvista as pv


# ============================================================
# 1. PROJECT PATHS
# ============================================================

# Current file:
#
# COP/
# └── stage_1_virtual_geometry/
#     ├── create_head.py
#     └── head/
#         ├── brain_surface.py
#         └── scalp_surface.py

PROJECT_ROOT = Path(__file__).resolve().parents[1]

STAGE_DIR = Path(__file__).resolve().parent
HEAD_CODE_DIR = STAGE_DIR / "head"


# Add head/ to Python import path
if str(HEAD_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(HEAD_CODE_DIR))


# ============================================================
# 2. IMPORT OUR EXISTING LOADERS
# ============================================================

from brain_surface import load_brain_surface
from scalp_surface import load_scalp_surface


# ============================================================
# 3. CREATE COMPLETE HEAD
# ============================================================

def create_head():
    """
    Load the ICBM152 brain and scalp surfaces.

    Returns
    -------
    brain : pyvista.PolyData
        High-resolution cortical surface.

    scalp : pyvista.PolyData
        Anatomical scalp surface.
    """

    print("\n========================================")
    print("COP - Creating ICBM152 Virtual Head")
    print("========================================")

    # Load brain using brain_surface.py
    brain = load_brain_surface()

    # Load scalp using scalp_surface.py
    scalp = load_scalp_surface()

    print("\nVirtual head created successfully.")

    print("\nBrain:")
    print(f"  Points : {brain.n_points}")
    print(f"  Cells  : {brain.n_cells}")

    print("\nScalp:")
    print(f"  Points : {scalp.n_points}")
    print(f"  Cells  : {scalp.n_cells}")

    print("========================================\n")

    return brain, scalp


# ============================================================
# 4. VISUALIZE COMPLETE HEAD
# ============================================================

def visualize_head(brain, scalp):
    """
    Visualize the brain inside the semi-transparent scalp.
    """

    plotter = pv.Plotter(
        window_size=(1200, 900)
    )

    # ========================================================
    # Brain
    # ========================================================

    plotter.add_mesh(
        brain,
        color="lightcoral",
        smooth_shading=True,
        show_edges=False,
        opacity=1.0,
        name="Brain"
    )

    # ========================================================
    # Scalp
    # ========================================================

    plotter.add_mesh(
        scalp,
        color="lightgray",
        smooth_shading=True,
        show_edges=False,

        # Keep scalp transparent enough to see cortex
        opacity=0.15,

        name="Scalp"
    )

    # ========================================================
    # Title
    # ========================================================

    plotter.add_text(
        "COP Stage 1 - ICBM152 Virtual Head",
        position="upper_left",
        font_size=12
    )

    # ========================================================
    # Anatomical axes
    # ========================================================

    plotter.add_axes(
        xlabel="X: Left / Right",
        ylabel="Y: Posterior / Anterior",
        zlabel="Z: Inferior / Superior"
    )

    # ========================================================
    # Camera
    # ========================================================

    plotter.reset_camera()

    # Start from a useful anatomical view
    plotter.view_isometric()

    # ========================================================
    # Show interactive window
    # ========================================================

    plotter.show()


# ============================================================
# 5. MAIN
# ============================================================

if __name__ == "__main__":

    brain, scalp = create_head()

    visualize_head(brain, scalp)