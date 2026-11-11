from pathlib import Path

import numpy as np
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent

MASTER = ROOT / "surfaces_master" / "inner_skull.vtk"
REDUCED = ROOT / "surfaces_mne" / "inner_skull_20480_test.vtk"


# ============================================================
# Helpers
# ============================================================

def topology_report(mesh, name):
    """Report basic topology without modifying the source file."""

    mesh = mesh.triangulate().clean()

    boundary = mesh.extract_feature_edges(
        boundary_edges=True,
        non_manifold_edges=False,
        feature_edges=False,
        manifold_edges=False,
    )

    non_manifold = mesh.extract_feature_edges(
        boundary_edges=False,
        non_manifold_edges=True,
        feature_edges=False,
        manifold_edges=False,
    )

    connectivity = mesh.connectivity()
    region_ids = np.unique(connectivity["RegionId"])

    print("\n" + "=" * 70)
    print(name)
    print("=" * 70)

    print(f"Vertices           : {mesh.n_points:,}")
    print(f"Triangles          : {mesh.n_cells:,}")
    print(f"Boundary edges     : {boundary.n_cells:,}")
    print(f"Non-manifold edges : {non_manifold.n_cells:,}")
    print(f"Connected regions  : {len(region_ids):,}")

    return {
        "mesh": mesh,
        "boundary_edges": boundary.n_cells,
        "non_manifold_edges": non_manifold.n_cells,
        "regions": len(region_ids),
    }


def point_to_surface_distances(source_mesh, target_mesh):
    """
    Compute absolute distance from every vertex of source_mesh
    to the continuous surface represented by target_mesh.
    """

    source_copy = source_mesh.copy()

    source_copy.compute_implicit_distance(
        target_mesh,
        inplace=True,
    )

    distances = np.abs(
        np.asarray(source_copy["implicit_distance"])
    )

    return distances


def print_distance_report(name, distances):
    """Print descriptive statistics for point-to-surface distances."""

    print("\n" + "-" * 70)
    print(name)
    print("-" * 70)

    print(f"Samples : {len(distances):,}")
    print(f"Minimum : {np.min(distances):.9f} mm")
    print(f"Median  : {np.median(distances):.9f} mm")
    print(f"Mean    : {np.mean(distances):.9f} mm")
    print(f"95th pct: {np.percentile(distances, 95):.9f} mm")
    print(f"99th pct: {np.percentile(distances, 99):.9f} mm")
    print(f"Maximum : {np.max(distances):.9f} mm")


# ============================================================
# Load surfaces
# ============================================================

print("=" * 70)
print("SPHERICAL DECIMATION VALIDATION")
print("=" * 70)

if not MASTER.exists():
    raise FileNotFoundError(f"Master surface not found:\n{MASTER}")

if not REDUCED.exists():
    raise FileNotFoundError(f"Reduced surface not found:\n{REDUCED}")

master_raw = pv.read(MASTER)
reduced_raw = pv.read(REDUCED)


# ============================================================
# Topology
# ============================================================

master_info = topology_report(
    master_raw,
    "MASTER INNER SKULL",
)

reduced_info = topology_report(
    reduced_raw,
    "REDUCED INNER SKULL",
)

master = master_info["mesh"]
reduced = reduced_info["mesh"]


# ============================================================
# Bidirectional geometric deviation
# ============================================================

print("\n" + "=" * 70)
print("BIDIRECTIONAL GEOMETRIC DEVIATION")
print("=" * 70)

# Direction 1:
# Every reduced vertex -> continuous master surface
reduced_to_master = point_to_surface_distances(
    reduced,
    master,
)

print_distance_report(
    "REDUCED -> MASTER",
    reduced_to_master,
)


# Direction 2:
# Every master vertex -> continuous reduced surface
master_to_reduced = point_to_surface_distances(
    master,
    reduced,
)

print_distance_report(
    "MASTER -> REDUCED",
    master_to_reduced,
)

# ============================================================
# Localized deviation analysis
# ============================================================

print("\n" + "=" * 70)
print("MASTER -> REDUCED OUTLIER ANALYSIS")
print("=" * 70)

thresholds = [
    0.5,
    1.0,
    2.0,
    3.0,
    5.0,
    8.0,
]

n_total = len(master_to_reduced)

for threshold in thresholds:
    count = np.count_nonzero(master_to_reduced > threshold)
    percent = 100.0 * count / n_total

    print(
        f"> {threshold:4.1f} mm : "
        f"{count:7,d} vertices "
        f"({percent:8.4f}%)"
    )


# Maximum-error vertex
max_idx = int(np.argmax(master_to_reduced))
max_distance = float(master_to_reduced[max_idx])
max_xyz = master.points[max_idx]

print("\nMaximum-error location:")
print(f"  Vertex index : {max_idx}")
print(f"  Distance     : {max_distance:.6f} mm")
print(
    f"  Coordinate   : "
    f"x={max_xyz[0]:.3f}, "
    f"y={max_xyz[1]:.3f}, "
    f"z={max_xyz[2]:.3f} mm"
)


# Save master surface with distance field for visualization
master_distance_mesh = master.copy()

master_distance_mesh["decimation_error_mm"] = (
    master_to_reduced
)

error_output = (
    ROOT
    / "surfaces_mne"
    / "inner_skull_20480_error_map.vtk"
)

master_distance_mesh.save(error_output)

print("\nSaved spatial error map:")
print(f"  {error_output}")

# ============================================================
# Symmetric summary
# ============================================================

max_r2m = float(np.max(reduced_to_master))
max_m2r = float(np.max(master_to_reduced))

symmetric_max = max(
    max_r2m,
    max_m2r,
)

print("\n" + "=" * 70)
print("SYMMETRIC DISTANCE SUMMARY")
print("=" * 70)

print(f"Max reduced -> master : {max_r2m:.9f} mm")
print(f"Max master  -> reduced: {max_m2r:.9f} mm")
print(f"Symmetric maximum     : {symmetric_max:.9f} mm")


# ============================================================
# Topology decision
# ============================================================

topology_pass = (
    reduced_info["boundary_edges"] == 0
    and reduced_info["non_manifold_edges"] == 0
    and reduced_info["regions"] == 1
)

print("\n" + "=" * 70)

if topology_pass:
    print("TOPOLOGY VALIDATION: PASS")
else:
    print("TOPOLOGY VALIDATION: FAIL")

print("=" * 70)

print(
    "\nNOTE: No automatic geometric PASS/FAIL threshold is applied yet."
)
print(
    "The distance distribution will be evaluated before defining "
    "an acceptance criterion."
)