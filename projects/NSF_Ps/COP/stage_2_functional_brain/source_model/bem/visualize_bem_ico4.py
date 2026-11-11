from pathlib import Path

import pyvista as pv


# ============================================================
# Configuration
# ============================================================

# This script is located at:
#
# COP/
#   stage_2_functional_brain/
#       source_model/
#           bem/
#               visualize_bem_ico4.py
#
# Therefore:
#   parent       -> source_model
#   parents[0]   -> source_model
#   parents[1]   -> stage_2_functional_brain
#   parents[2]   -> COP

BEM_ROOT = Path(__file__).resolve().parent
COP_ROOT = BEM_ROOT.parents[2]


# ============================================================
# BEM surfaces
# ============================================================

ICO4_DIR = BEM_ROOT / "surfaces_mne_ico4"

INNER_PATH = (
    ICO4_DIR
    / "inner_skull_5120.vtk"
)

OUTER_PATH = (
    ICO4_DIR
    / "outer_skull_5120.vtk"
)

SKIN_PATH = (
    ICO4_DIR
    / "outer_skin_5120.vtk"
)


# ============================================================
# Cortex
# ============================================================

# IMPORTANT:
#
# The MNI152 cortex is stored directly under:
#
# COP/hm_icbm152/
#
# It is NOT inside stage_1_virtual_geometry/head/.
#
# We specifically use cortex_pial_high_mni152.obj because
# the BEM surfaces are also represented in MNI152 coordinates.

CORTEX_PATH = (
    COP_ROOT
    / "hm_icbm152"
    / "cortex_pial_high_mni152.obj"
)


# ============================================================
# Print resolved paths
# ============================================================

print("=" * 72)
print("BEM 3D VISUALIZATION")
print("=" * 72)

print("\nResolved project directories:")

print(f"BEM root : {BEM_ROOT}")
print(f"COP root : {COP_ROOT}")

print("\nInput surfaces:")

paths = {
    "Outer skin": SKIN_PATH,
    "Outer skull": OUTER_PATH,
    "Inner skull": INNER_PATH,
    "Cortex": CORTEX_PATH,
}

for name, path in paths.items():

    print(
        f"{name:12s}: {path}"
    )


# ============================================================
# Verify files
# ============================================================

print()
print("=" * 72)
print("FILE CHECK")
print("=" * 72)

missing = []

for name, path in paths.items():

    if path.exists():

        print(
            f"PASS  {name:12s}: "
            f"{path.name}"
        )

    else:

        print(
            f"FAIL  {name:12s}: "
            f"{path}"
        )

        missing.append(
            (name, path)
        )


if missing:

    print()
    print("=" * 72)
    print("VISUALIZATION ABORTED")
    print("=" * 72)

    print(
        "\nOne or more required files "
        "could not be found."
    )

    for name, path in missing:

        print(
            f"\n{name}:"
        )

        print(path)

    raise FileNotFoundError(
        "Required visualization input "
        "file(s) missing."
    )


# ============================================================
# Load surfaces
# ============================================================

print()
print("=" * 72)
print("LOADING SURFACES")
print("=" * 72)


skin = (
    pv.read(SKIN_PATH)
    .triangulate()
    .clean()
)

outer = (
    pv.read(OUTER_PATH)
    .triangulate()
    .clean()
)

inner = (
    pv.read(INNER_PATH)
    .triangulate()
    .clean()
)

cortex = (
    pv.read(CORTEX_PATH)
    .triangulate()
    .clean()
)


# ============================================================
# Surface statistics
# ============================================================

print("\nSurface sizes:")

print(
    f"Outer skin : "
    f"{skin.n_points:,} vertices, "
    f"{skin.n_cells:,} triangles"
)

print(
    f"Outer skull: "
    f"{outer.n_points:,} vertices, "
    f"{outer.n_cells:,} triangles"
)

print(
    f"Inner skull: "
    f"{inner.n_points:,} vertices, "
    f"{inner.n_cells:,} triangles"
)

print(
    f"Cortex     : "
    f"{cortex.n_points:,} vertices, "
    f"{cortex.n_cells:,} triangles"
)


# ============================================================
# Bounds
# ============================================================

print()
print("=" * 72)
print("SPATIAL BOUNDS [mm]")
print("=" * 72)


def print_bounds(name, mesh):

    b = mesh.bounds

    print(f"\n{name}")

    print(
        f"  x: {b[0]:8.3f} "
        f"to {b[1]:8.3f}"
    )

    print(
        f"  y: {b[2]:8.3f} "
        f"to {b[3]:8.3f}"
    )

    print(
        f"  z: {b[4]:8.3f} "
        f"to {b[5]:8.3f}"
    )


print_bounds(
    "Outer skin",
    skin,
)

print_bounds(
    "Outer skull",
    outer,
)

print_bounds(
    "Inner skull",
    inner,
)

print_bounds(
    "Cortex",
    cortex,
)


# ============================================================
# Create interactive plot
# ============================================================

print()
print("=" * 72)
print("CREATING INTERACTIVE 3D VIEW")
print("=" * 72)


plotter = pv.Plotter(
    window_size=(1500, 950)
)


# ============================================================
# Background
# ============================================================

plotter.set_background(
    "white"
)


# ============================================================
# Outer skin
# ============================================================

plotter.add_mesh(
    skin,
    color="lightgray",
    opacity=0.10,
    smooth_shading=True,
    show_edges=False,
    name="Outer skin",
)


# ============================================================
# Outer skull
# ============================================================

plotter.add_mesh(
    outer,
    color="gold",
    opacity=0.18,
    smooth_shading=True,
    show_edges=False,
    name="Outer skull",
)


# ============================================================
# Inner skull
# ============================================================

plotter.add_mesh(
    inner,
    color="dodgerblue",
    opacity=0.25,
    smooth_shading=True,
    show_edges=False,
    name="Inner skull",
)


# ============================================================
# Cortex
# ============================================================

plotter.add_mesh(
    cortex,
    color="indianred",
    opacity=1.0,
    smooth_shading=True,
    show_edges=False,
    name="Cortex",
)


# ============================================================
# Legend
# ============================================================

plotter.add_legend(
    [
        ["Outer skin", "lightgray"],
        ["Outer skull", "gold"],
        ["Inner skull", "dodgerblue"],
        ["Cortex", "indianred"],
    ],
    bcolor="white",
    border=True,
    size=(0.20, 0.18),
)


# ============================================================
# Axes
# ============================================================

plotter.add_axes(
    xlabel="X",
    ylabel="Y",
    zlabel="Z",
)


# ============================================================
# Title
# ============================================================

plotter.add_text(
    "Validated ICBM152 Three-Layer BEM + Cortex",
    position="upper_left",
    font_size=15,
    color="black",
)


# ============================================================
# Camera
# ============================================================

plotter.view_isometric()

plotter.reset_camera()

plotter.camera.zoom(
    1.15
)


# ============================================================
# Console information
# ============================================================

print()
print("Expected spatial organization:")
print()

print(
    "    Outer skin"
)

print(
    "        |"
)

print(
    "        +-- Outer skull"
)

print(
    "                |"
)

print(
    "                +-- Inner skull"
)

print(
    "                        |"
)

print(
    "                        +-- Cortex"
)


print()
print("Interactive controls:")

print(
    "  Left mouse drag   : rotate"
)

print(
    "  Right mouse drag  : zoom"
)

print(
    "  Middle mouse drag : pan"
)

print(
    "  Mouse wheel       : zoom"
)

print(
    "  R                 : reset camera"
)


print()
print("Visual QC goals:")

print(
    "  1. Cortex remains inside "
    "the inner skull."
)

print(
    "  2. Inner skull remains inside "
    "the outer skull."
)

print(
    "  3. Outer skull remains inside "
    "the outer skin."
)

print(
    "  4. No gross interface crossings "
    "are visually apparent."
)

print(
    "  5. Cortex and BEM surfaces appear "
    "in the same MNI152 coordinate space."
)


print()
print(
    "NOTE: Numerical containment has "
    "already been validated independently."
)

print(
    "This visualization is an additional "
    "qualitative QC step."
)

print()
print("=" * 72)


# ============================================================
# Show interactive visualization
# ============================================================

plotter.show()


# ============================================================
# Finished
# ============================================================

print()
print("=" * 72)
print("VISUALIZATION CLOSED")
print("=" * 72)

print(
    "\nNo geometry was modified."
)

print(
    "The validated ico4 BEM surfaces "
    "remain unchanged."
)

print("=" * 72)