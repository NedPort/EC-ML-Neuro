from pathlib import Path

import numpy as np
import pyvista as pv


# ============================================================
# Paths
# ============================================================

ROOT = Path(__file__).resolve().parents[3]

BEM_ROOT = (
    ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "bem"
)

SURFACE_DIR = BEM_ROOT / "surfaces"

INNER_PATH = SURFACE_DIR / "inner_skull.vtk"
OUTER_PATH = SURFACE_DIR / "outer_skull.vtk"


# ============================================================
# Load surfaces
# ============================================================

print("\nLOADING SKULL SURFACES")
print("=" * 72)

inner = pv.read(INNER_PATH).triangulate().clean()
outer = pv.read(OUTER_PATH).triangulate().clean()

print(
    f"Inner skull: {inner.n_points:,} vertices, "
    f"{inner.n_cells:,} triangles"
)

print(
    f"Outer skull: {outer.n_points:,} vertices, "
    f"{outer.n_cells:,} triangles"
)


# ============================================================
# Make normals consistent
#
# This does NOT change the anatomical geometry.
# It only makes triangle orientation consistent.
# ============================================================

inner = inner.compute_normals(
    cell_normals=True,
    point_normals=True,
    consistent_normals=True,
    auto_orient_normals=True,
    split_vertices=False,
    inplace=False,
)

outer = outer.compute_normals(
    cell_normals=True,
    point_normals=True,
    consistent_normals=True,
    auto_orient_normals=True,
    split_vertices=False,
    inplace=False,
)


# ============================================================
# Test inner-skull vertices against outer-skull volume
# ============================================================

print("\nTESTING INNER-SKULL CONTAINMENT")
print("=" * 72)

inner_points = pv.PolyData(
    np.asarray(inner.points)
)

selection = inner_points.select_enclosed_points(
    outer,
    tolerance=0.0,
    check_surface=True,
)

inside_mask = (
    np.asarray(selection["SelectedPoints"])
    .astype(bool)
)

outside_mask = ~inside_mask

inside_points = np.asarray(inner.points)[inside_mask]
outside_points = np.asarray(inner.points)[outside_mask]

n_total = len(inner.points)
n_inside = int(inside_mask.sum())
n_outside = int(outside_mask.sum())

print(f"Total inner vertices : {n_total:,}")
print(f"Inside outer skull   : {n_inside:,}")
print(f"Outside/touching     : {n_outside:,}")

print(
    f"Containment          : "
    f"{100.0 * n_inside / n_total:.6f}%"
)


# ============================================================
# Location of violations
# ============================================================

print("\nVIOLATION LOCATION")
print("=" * 72)

if n_outside == 0:

    print(
        "No violating inner-skull vertices were detected."
    )

else:

    mins = outside_points.min(axis=0)
    maxs = outside_points.max(axis=0)
    means = outside_points.mean(axis=0)

    print("Bounds of problematic vertices [mm]:")

    print(
        f"  x: {mins[0]:.3f} to {maxs[0]:.3f}"
    )

    print(
        f"  y: {mins[1]:.3f} to {maxs[1]:.3f}"
    )

    print(
        f"  z: {mins[2]:.3f} to {maxs[2]:.3f}"
    )

    print("\nMean location [mm]:")

    print(
        f"  x = {means[0]:.3f}"
    )

    print(
        f"  y = {means[1]:.3f}"
    )

    print(
        f"  z = {means[2]:.3f}"
    )

    # --------------------------------------------------------
    # Z distribution
    # --------------------------------------------------------

    z = outside_points[:, 2]

    print("\nProblematic-vertex z statistics [mm]:")

    print(
        f"  minimum : {np.min(z):.3f}"
    )

    print(
        f"  5%      : {np.percentile(z, 5):.3f}"
    )

    print(
        f"  25%     : {np.percentile(z, 25):.3f}"
    )

    print(
        f"  median  : {np.median(z):.3f}"
    )

    print(
        f"  75%     : {np.percentile(z, 75):.3f}"
    )

    print(
        f"  95%     : {np.percentile(z, 95):.3f}"
    )

    print(
        f"  maximum : {np.max(z):.3f}"
    )


# ============================================================
# Distance from every inner vertex to outer surface
#
# This is an unsigned closest-surface distance.
#
# It helps identify whether the problematic regions are
# essentially coincident/touching or substantially separated.
# ============================================================

print("\nCOMPUTING INNER -> OUTER CLOSEST DISTANCES")
print("=" * 72)

distance_mesh = inner.compute_implicit_distance(
    outer,
    inplace=False,
)

signed_distance = np.asarray(
    distance_mesh["implicit_distance"]
)

abs_distance = np.abs(signed_distance)

print("All inner vertices:")

print(
    f"  minimum distance : {abs_distance.min():.6f} mm"
)

print(
    f"  median distance  : {np.median(abs_distance):.6f} mm"
)

print(
    f"  mean distance    : {np.mean(abs_distance):.6f} mm"
)

print(
    f"  maximum distance : {abs_distance.max():.6f} mm"
)


if n_outside > 0:

    bad_dist = abs_distance[outside_mask]

    print("\nProblematic vertices only:")

    print(
        f"  minimum distance : {bad_dist.min():.6f} mm"
    )

    print(
        f"  median distance  : {np.median(bad_dist):.6f} mm"
    )

    print(
        f"  mean distance    : {np.mean(bad_dist):.6f} mm"
    )

    print(
        f"  95% distance     : "
        f"{np.percentile(bad_dist, 95):.6f} mm"
    )

    print(
        f"  maximum distance : {bad_dist.max():.6f} mm"
    )


# ============================================================
# Count near-coincident inner/outer surface points
# ============================================================

print("\nSURFACE-SEPARATION SUMMARY")
print("=" * 72)

thresholds = [
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    3.0,
]

for threshold in thresholds:

    count = int(
        np.sum(abs_distance <= threshold)
    )

    percent = (
        100.0 * count / n_total
    )

    print(
        f"<= {threshold:4.2f} mm : "
        f"{count:8,} vertices "
        f"({percent:7.3f}%)"
    )


# ============================================================
# Save problematic points
# ============================================================

if n_outside > 0:

    bad_cloud = pv.PolyData(
        outside_points
    )

    output_path = (
        BEM_ROOT
        / "inner_skull_outside_outer_skull.vtk"
    )

    bad_cloud.save(
        output_path
    )

    print(
        "\nProblematic vertices saved to:"
    )

    print(
        output_path
    )


# ============================================================
# Visualization
# ============================================================

print("\nOPENING VISUALIZATION")
print("=" * 72)

plotter = pv.Plotter()

# Outer skull:
# transparent orange shell
plotter.add_mesh(
    outer,
    color="orange",
    opacity=0.20,
    smooth_shading=True,
    label="Outer skull",
)

# Inner skull:
# blue shell
plotter.add_mesh(
    inner,
    color="royalblue",
    opacity=0.45,
    smooth_shading=True,
    label="Inner skull",
)


# Problematic vertices:
# yellow points
if n_outside > 0:

    bad_cloud = pv.PolyData(
        outside_points
    )

    plotter.add_mesh(
        bad_cloud,
        color="yellow",
        point_size=8,
        render_points_as_spheres=True,
        label="Inner vertices outside/touching outer skull",
    )


plotter.add_legend()

plotter.add_axes()

plotter.show_grid()

plotter.show()


# ============================================================
# Final interpretation
# ============================================================

print("\nDIAGNOSTIC COMPLETE")
print("=" * 72)

if n_outside == 0:

    print(
        "PyVista reports complete inner -> outer containment."
    )

    print(
        "If MNE still rejects the surfaces, the next step is "
        "triangle-level intersection analysis."
    )

else:

    print(
        f"{n_outside:,} inner-skull vertices were classified "
        "as outside/touching the outer skull."
    )

    print(
        "Inspect their spatial distribution and distance "
        "statistics before modifying either surface."
    )

print("=" * 72)