from pathlib import Path

import numpy as np
import pyvista as pv


ROOT = Path(__file__).resolve().parent
MASTER_DIR = ROOT / "surfaces_master"
REDUCED_DIR = ROOT / "surfaces_mne"

SURFACES = [
    "inner_skull",
    "outer_skull",
    "outer_skin",
]


def prepare(mesh):
    return mesh.triangulate().clean()


def topology(mesh):
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

    regions = np.unique(
        mesh.connectivity()["RegionId"]
    )

    return (
        boundary.n_cells,
        non_manifold.n_cells,
        len(regions),
    )


def distances(source, target):
    temp = source.copy()

    temp.compute_implicit_distance(
        target,
        inplace=True,
    )

    return np.abs(
        np.asarray(temp["implicit_distance"])
    )


def report_distances(d):
    print(f"    Median  : {np.median(d):.6f} mm")
    print(f"    Mean    : {np.mean(d):.6f} mm")
    print(f"    95th pct: {np.percentile(d, 95):.6f} mm")
    print(f"    99th pct: {np.percentile(d, 99):.6f} mm")
    print(f"    Maximum : {np.max(d):.6f} mm")

    for threshold in [1.0, 2.0, 3.0, 5.0, 8.0]:
        count = np.count_nonzero(d > threshold)
        pct = 100.0 * count / len(d)

        print(
            f"    > {threshold:3.1f} mm: "
            f"{count:,} ({pct:.4f}%)"
        )


print("=" * 72)
print("ALL BEM SURFACE VALIDATION")
print("=" * 72)

all_topology_pass = True


for name in SURFACES:

    master_path = MASTER_DIR / f"{name}.vtk"
    reduced_path = REDUCED_DIR / f"{name}_20480.vtk"

    print("\n" + "=" * 72)
    print(name.upper())
    print("=" * 72)

    master = prepare(
        pv.read(master_path)
    )

    reduced = prepare(
        pv.read(reduced_path)
    )

    # --------------------------------------------------------
    # Mesh statistics
    # --------------------------------------------------------

    print("\nMASTER")
    print(f"  Vertices : {master.n_points:,}")
    print(f"  Triangles: {master.n_cells:,}")

    print("\nREDUCED")
    print(f"  Vertices : {reduced.n_points:,}")
    print(f"  Triangles: {reduced.n_cells:,}")

    # --------------------------------------------------------
    # Topology
    # --------------------------------------------------------

    boundary, nonmanifold, regions = topology(reduced)

    print("\nTOPOLOGY")
    print(f"  Boundary edges     : {boundary:,}")
    print(f"  Non-manifold edges : {nonmanifold:,}")
    print(f"  Connected regions  : {regions:,}")

    topo_pass = (
        boundary == 0
        and nonmanifold == 0
        and regions == 1
    )

    print(
        f"  Result             : "
        f"{'PASS' if topo_pass else 'FAIL'}"
    )

    if not topo_pass:
        all_topology_pass = False

    # --------------------------------------------------------
    # Reduced -> master
    # --------------------------------------------------------

    r2m = distances(
        reduced,
        master,
    )

    print("\nREDUCED -> MASTER")
    report_distances(r2m)

    # --------------------------------------------------------
    # Master -> reduced
    # --------------------------------------------------------

    m2r = distances(
        master,
        reduced,
    )

    print("\nMASTER -> REDUCED")
    report_distances(m2r)

    # --------------------------------------------------------
    # Maximum-error position
    # --------------------------------------------------------

    idx = int(np.argmax(m2r))

    xyz = master.points[idx]

    print("\nMAXIMUM MASTER -> REDUCED ERROR")
    print(f"  Vertex   : {idx}")
    print(f"  Distance : {m2r[idx]:.6f} mm")
    print(
        f"  XYZ      : "
        f"({xyz[0]:.3f}, "
        f"{xyz[1]:.3f}, "
        f"{xyz[2]:.3f}) mm"
    )


print("\n" + "=" * 72)

if all_topology_pass:
    print("ALL REDUCED SURFACES: TOPOLOGY PASS")
else:
    print("ONE OR MORE REDUCED SURFACES: TOPOLOGY FAIL")

print("=" * 72)