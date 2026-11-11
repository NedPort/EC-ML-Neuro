from pathlib import Path

import numpy as np
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent

MASTER_DIR = ROOT / "surfaces_master"
REDUCED_DIR = ROOT / "surfaces_mne_ico4"

SURFACES = [
    "inner_skull",
    "outer_skull",
    "outer_skin",
]


# ============================================================
# Helpers
# ============================================================

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

    connected = mesh.connectivity()

    regions = np.unique(
        connected["RegionId"]
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
        np.asarray(
            temp["implicit_distance"],
            dtype=float,
        )
    )


def report_distances(d):

    print(
        f"    Median  : "
        f"{np.median(d):.6f} mm"
    )

    print(
        f"    Mean    : "
        f"{np.mean(d):.6f} mm"
    )

    print(
        f"    95th pct: "
        f"{np.percentile(d, 95):.6f} mm"
    )

    print(
        f"    99th pct: "
        f"{np.percentile(d, 99):.6f} mm"
    )

    print(
        f"    Maximum : "
        f"{np.max(d):.6f} mm"
    )

    for threshold in [
        1.0,
        2.0,
        3.0,
        5.0,
        8.0,
        10.0,
        15.0,
        20.0,
    ]:

        count = int(
            np.count_nonzero(
                d > threshold
            )
        )

        pct = (
            100.0
            * count
            / len(d)
        )

        print(
            f"    > {threshold:4.1f} mm: "
            f"{count:7,d} "
            f"({pct:8.4f}%)"
        )


# ============================================================
# Main validation
# ============================================================

print("=" * 72)
print("ICO4 BEM SURFACE VALIDATION")
print("=" * 72)

print(
    "\nComparing each 5,120-triangle ico4 candidate "
    "against its high-resolution master."
)

all_topology_pass = True


for name in SURFACES:

    master_path = (
        MASTER_DIR
        / f"{name}.vtk"
    )

    reduced_path = (
        REDUCED_DIR
        / f"{name}_5120.vtk"
    )

    if not master_path.exists():
        raise FileNotFoundError(
            f"Master surface not found:\n"
            f"{master_path}"
        )

    if not reduced_path.exists():
        raise FileNotFoundError(
            f"ico4 surface not found:\n"
            f"{reduced_path}"
        )

    print("\n" + "=" * 72)
    print(name.upper())
    print("=" * 72)

    master = prepare(
        pv.read(master_path)
    )

    reduced = prepare(
        pv.read(reduced_path)
    )

    # ========================================================
    # Mesh statistics
    # ========================================================

    print("\nMASTER")

    print(
        f"  Vertices : "
        f"{master.n_points:,}"
    )

    print(
        f"  Triangles: "
        f"{master.n_cells:,}"
    )

    print("\nICO4")

    print(
        f"  Vertices : "
        f"{reduced.n_points:,}"
    )

    print(
        f"  Triangles: "
        f"{reduced.n_cells:,}"
    )

    # ========================================================
    # Resolution sanity check
    # ========================================================

    resolution_pass = (
        reduced.n_points == 2_562
        and reduced.n_cells == 5_120
    )

    print("\nRESOLUTION")

    print(
        "  Expected : "
        "2,562 vertices / 5,120 triangles"
    )

    print(
        f"  Result   : "
        f"{'PASS' if resolution_pass else 'FAIL'}"
    )

    # ========================================================
    # Topology
    # ========================================================

    boundary, nonmanifold, regions = topology(
        reduced
    )

    print("\nTOPOLOGY")

    print(
        f"  Boundary edges     : "
        f"{boundary:,}"
    )

    print(
        f"  Non-manifold edges : "
        f"{nonmanifold:,}"
    )

    print(
        f"  Connected regions  : "
        f"{regions:,}"
    )

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

    # ========================================================
    # ICO4 -> master
    # ========================================================

    reduced_to_master = distances(
        reduced,
        master,
    )

    print("\nICO4 -> MASTER")

    report_distances(
        reduced_to_master
    )

    # ========================================================
    # Master -> ico4
    #
    # This direction is particularly important because it
    # reveals anatomical regions that are not represented
    # closely by the lower-resolution surface.
    # ========================================================

    master_to_reduced = distances(
        master,
        reduced,
    )

    print("\nMASTER -> ICO4")

    report_distances(
        master_to_reduced
    )

    # ========================================================
    # Maximum-error position
    # ========================================================

    idx = int(
        np.argmax(
            master_to_reduced
        )
    )

    xyz = master.points[idx]

    print(
        "\nMAXIMUM MASTER -> ICO4 ERROR"
    )

    print(
        f"  Vertex   : {idx}"
    )

    print(
        f"  Distance : "
        f"{master_to_reduced[idx]:.6f} mm"
    )

    print(
        "  XYZ      : "
        f"({xyz[0]:.3f}, "
        f"{xyz[1]:.3f}, "
        f"{xyz[2]:.3f}) mm"
    )


# ============================================================
# Overall topology summary
# ============================================================

print("\n" + "=" * 72)

if all_topology_pass:

    print(
        "ALL ICO4 SURFACES: TOPOLOGY PASS"
    )

else:

    print(
        "ONE OR MORE ICO4 SURFACES: "
        "TOPOLOGY FAIL"
    )

print("=" * 72)

print(
    "\nNOTE:"
)

print(
    "No automatic geometric acceptance threshold "
    "is applied here."
)

print(
    "We will compare these distributions with the "
    "validated ico5 results before deciding whether "
    "ico4 is acceptable."
)