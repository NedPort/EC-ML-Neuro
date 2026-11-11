from pathlib import Path

import numpy as np
import pyvista as pv


# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SURFACE_DIR = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "fem"
    / "tissue_surfaces"
)


# ============================================================
# Tissue definitions
# ============================================================

TISSUES = {
    "skin": SURFACE_DIR / "skin_surface_mni152.vtp",
    "bone": SURFACE_DIR / "bone_surface_mni152.vtp",
    "csf": SURFACE_DIR / "csf_surface_mni152.vtp",
    "gray": SURFACE_DIR / "gray_surface_mni152.vtp",
    "white": SURFACE_DIR / "white_surface_mni152.vtp",
}


COLORS = {
    "skin": "peachpuff",
    "bone": "ivory",
    "csf": "deepskyblue",
    "gray": "lightcoral",
    "white": "wheat",
}


# ============================================================
# Helper
# ============================================================

def extract_nonmanifold_edges(surface):
    """
    Extract edges shared by more than two surface faces.
    """

    return surface.extract_feature_edges(
        boundary_edges=False,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=True,
    )


# ============================================================
# 1. Load surfaces
# ============================================================

print("\n============================================")
print("LOADING TISSUE SURFACES")
print("============================================")

surfaces = {}

for tissue_name, path in TISSUES.items():

    surface = pv.read(path)

    surfaces[tissue_name] = surface

    print(
        f"{tissue_name:<8} | "
        f"vertices={surface.n_points:>9,} | "
        f"faces={surface.n_cells:>9,}"
    )


# ============================================================
# 2. Extract non-manifold edges
# ============================================================

print("\n============================================")
print("NON-MANIFOLD EDGE ANALYSIS")
print("============================================")

nonmanifold = {}

for tissue_name, surface in surfaces.items():

    edges = extract_nonmanifold_edges(
        surface
    )

    nonmanifold[tissue_name] = edges

    print("\n--------------------------------------------")
    print(tissue_name.upper())
    print("--------------------------------------------")

    print(
        f"Non-manifold edge cells: "
        f"{edges.n_cells:,}"
    )

    print(
        f"Unique edge points: "
        f"{edges.n_points:,}"
    )

    if edges.n_points == 0:
        print("No non-manifold geometry.")
        continue

    xyz = np.asarray(
        edges.points,
        dtype=float,
    )

    print(
        "MNI bounds:"
        f"\n  x: {xyz[:, 0].min():.1f} "
        f"to {xyz[:, 0].max():.1f}"
        f"\n  y: {xyz[:, 1].min():.1f} "
        f"to {xyz[:, 1].max():.1f}"
        f"\n  z: {xyz[:, 2].min():.1f} "
        f"to {xyz[:, 2].max():.1f}"
    )


# ============================================================
# 3. Find connected groups of non-manifold edges
# ============================================================

print("\n============================================")
print("NON-MANIFOLD CONNECTED GROUPS")
print("============================================")

for tissue_name, edges in nonmanifold.items():

    print("\n--------------------------------------------")
    print(tissue_name.upper())
    print("--------------------------------------------")

    if edges.n_cells == 0:
        print("Groups: 0")
        continue

    connected = edges.connectivity()

    if "RegionId" in connected.cell_data:

        region_ids = np.asarray(
            connected.cell_data["RegionId"]
        )

    elif "RegionId" in connected.point_data:

        region_ids = np.asarray(
            connected.point_data["RegionId"]
        )

    else:
        print(
            "Could not determine RegionId."
        )
        continue

    unique_regions = np.unique(
        region_ids
    )

    print(
        f"Connected groups: "
        f"{len(unique_regions)}"
    )

    # --------------------------------------------------------
    # Print location of each group
    # --------------------------------------------------------

    for region_id in unique_regions:

        region = connected.threshold(
            [
                float(region_id),
                float(region_id),
            ],
            scalars="RegionId",
        )

        if region.n_points == 0:
            continue

        xyz = np.asarray(
            region.points,
            dtype=float,
        )

        center = xyz.mean(axis=0)

        print(
            f"  Group {int(region_id):>3}: "
            f"points={region.n_points:>4} | "
            f"center="
            f"({center[0]:.1f}, "
            f"{center[1]:.1f}, "
            f"{center[2]:.1f})"
        )


# ============================================================
# 4. Combined visualization
# ============================================================

print("\n============================================")
print("OPENING NON-MANIFOLD DIAGNOSTIC VIEW")
print("============================================")

plotter = pv.Plotter(
    window_size=(1300, 900)
)

# Tissue surfaces
for tissue_name, surface in surfaces.items():

    plotter.add_mesh(
        surface,
        color=COLORS[tissue_name],
        opacity=0.08,
        smooth_shading=True,
        show_edges=False,
        label=tissue_name,
    )


# Non-manifold edges
#
# All problematic edges are shown in red so that their
# positions stand out against the transparent anatomy.
for tissue_name, edges in nonmanifold.items():

    if edges.n_cells == 0:
        continue

    plotter.add_mesh(
        edges,
        color="red",
        line_width=6,
        render_lines_as_tubes=True,
        label=f"{tissue_name} non-manifold",
    )

    # Add points too, which makes very short edges easier
    # to identify.
    edge_points = pv.PolyData(
        edges.points
    )

    plotter.add_mesh(
        edge_points,
        color="yellow",
        point_size=9,
        render_points_as_spheres=True,
    )


plotter.add_axes(
    xlabel="X",
    ylabel="Y",
    zlabel="Z",
)

plotter.show_grid(
    xtitle="X MNI (mm)",
    ytitle="Y MNI (mm)",
    ztitle="Z MNI (mm)",
)

plotter.add_legend()

plotter.camera_position = "iso"

plotter.show()