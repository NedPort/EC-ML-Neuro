from pathlib import Path

import numpy as np
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parents[3]

BEM_ROOT = (
    ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "bem"
)

MASTER_DIR = BEM_ROOT / "surfaces_master"
OUTPUT_DIR = BEM_ROOT / "surfaces_mne"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# Surface names and paths
# ============================================================

SURFACE_NAMES = (
    "inner_skull",
    "outer_skull",
    "outer_skin",
)

MASTER_PATHS = {
    name: MASTER_DIR / f"{name}.vtk"
    for name in SURFACE_NAMES
}

OUTPUT_PATHS = {
    name: OUTPUT_DIR / f"{name}.vtk"
    for name in SURFACE_NAMES
}


# ============================================================
# Target computational resolution
#
# Start conservatively at ~20,000 triangles per surface.
#
# decimate_pro() with preserve_topology=True may stop above
# the requested target. That is acceptable.
#
# Topology and nesting are more important than hitting an
# exact triangle count.
# ============================================================

TARGET_TRIANGLES = {
    "inner_skull": 20_000,
    "outer_skull": 20_000,
    "outer_skin": 20_000,
}


# ============================================================
# Validation parameters
# ============================================================

CONTAINMENT_TOLERANCE = 0.0

# Require strictly positive separation.
MIN_REQUIRED_SKULL_SEPARATION_MM = 0.0


# ============================================================
# Load / orient surfaces
# ============================================================

def orient_surface(mesh):
    """
    Triangulate, clean, and consistently orient a surface.

    This does not intentionally alter the anatomical shape.
    """

    mesh = mesh.triangulate().clean()

    mesh = mesh.compute_normals(
        cell_normals=True,
        point_normals=True,
        consistent_normals=True,
        auto_orient_normals=True,
        split_vertices=False,
        inplace=False,
    )

    return mesh


def load_surface(path):
    """
    Load and prepare one VTK surface.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Surface not found:\n{path}"
        )

    mesh = pv.read(path)

    return orient_surface(mesh)


# ============================================================
# Topology functions
# ============================================================

def count_connected_regions(mesh):
    """
    Count connected surface components.
    """

    connected = mesh.connectivity()

    if connected.n_cells == 0:
        return 0

    if "RegionId" in connected.cell_data:
        region_ids = np.asarray(
            connected.cell_data["RegionId"]
        )

    elif "RegionId" in connected.point_data:
        region_ids = np.asarray(
            connected.point_data["RegionId"]
        )

    else:
        raise RuntimeError(
            "Could not obtain RegionId from connectivity result."
        )

    return len(
        np.unique(region_ids)
    )


def topology_metrics(mesh):
    """
    Compute topology metrics for one surface.
    """

    boundary = mesh.extract_feature_edges(
        boundary_edges=True,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=False,
    )

    non_manifold = mesh.extract_feature_edges(
        boundary_edges=False,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=True,
    )

    return {
        "vertices": int(mesh.n_points),
        "triangles": int(mesh.n_cells),
        "boundary_edges": int(boundary.n_cells),
        "non_manifold_edges": int(non_manifold.n_cells),
        "regions": int(count_connected_regions(mesh)),
    }


def print_topology(name, mesh):
    """
    Print topology and bounds.
    """

    metrics = topology_metrics(mesh)

    print(f"\n{name}")
    print("-" * 72)

    print(
        f"vertices            : "
        f"{metrics['vertices']:,}"
    )

    print(
        f"triangles           : "
        f"{metrics['triangles']:,}"
    )

    print(
        f"boundary edges      : "
        f"{metrics['boundary_edges']:,}"
    )

    print(
        f"non-manifold edges  : "
        f"{metrics['non_manifold_edges']:,}"
    )

    print(
        f"connected regions   : "
        f"{metrics['regions']:,}"
    )

    print(
        f"x bounds [mm]       : "
        f"{mesh.bounds[0]:.3f} to "
        f"{mesh.bounds[1]:.3f}"
    )

    print(
        f"y bounds [mm]       : "
        f"{mesh.bounds[2]:.3f} to "
        f"{mesh.bounds[3]:.3f}"
    )

    print(
        f"z bounds [mm]       : "
        f"{mesh.bounds[4]:.3f} to "
        f"{mesh.bounds[5]:.3f}"
    )

    return metrics


def topology_passes(mesh):
    """
    Return True only if the surface is:
      - closed
      - manifold
      - one connected region
    """

    metrics = topology_metrics(mesh)

    return (
        metrics["boundary_edges"] == 0
        and metrics["non_manifold_edges"] == 0
        and metrics["regions"] == 1
    )


# ============================================================
# Topology-preserving decimation
# ============================================================

def decimate_surface(
    mesh,
    target_triangles,
):
    """
    Reduce a triangular mesh using PyVista/VTK decimate_pro.

    The important settings are:

        preserve_topology=True
        splitting=False
        boundary_vertex_deletion=False

    The decimator is allowed to retain more triangles than
    requested if necessary to preserve topology.
    """

    current_triangles = int(
        mesh.n_cells
    )

    if current_triangles <= target_triangles:

        print(
            "Surface already has <= target triangles."
        )

        return mesh.copy()


    target_reduction = (
        1.0
        - (
            target_triangles
            / current_triangles
        )
    )

    target_reduction = float(
        np.clip(
            target_reduction,
            0.0,
            0.999,
        )
    )


    print(
        f"Current triangles : "
        f"{current_triangles:,}"
    )

    print(
        f"Requested target  : "
        f"{target_triangles:,}"
    )

    print(
        f"Requested reduction: "
        f"{100.0 * target_reduction:.3f}%"
    )


    # --------------------------------------------------------
    # Topology-preserving decimation
    # --------------------------------------------------------

    reduced = mesh.decimate_pro(
        reduction=target_reduction,
        preserve_topology=True,
        splitting=False,
        boundary_vertex_deletion=False,
    )


    # --------------------------------------------------------
    # Re-triangulate / clean / orient.
    # --------------------------------------------------------

    reduced = orient_surface(
        reduced
    )


    print(
        f"Result triangles  : "
        f"{reduced.n_cells:,}"
    )

    print(
        f"Result vertices   : "
        f"{reduced.n_points:,}"
    )


    achieved_reduction = (
        1.0
        - (
            reduced.n_cells
            / current_triangles
        )
    )

    print(
        f"Actual reduction  : "
        f"{100.0 * achieved_reduction:.3f}%"
    )


    return reduced


# ============================================================
# Containment
# ============================================================

def containment_test(
    inner,
    outer,
    description,
):
    """
    Test whether every vertex of `inner` lies inside `outer`.

    This function must only be called when `outer` is a
    validated closed/manifold surface.
    """

    if not topology_passes(outer):

        raise RuntimeError(
            f"Cannot run containment test '{description}'. "
            "The enclosing surface is not closed/manifold."
        )


    points = pv.PolyData(
        np.asarray(
            inner.points
        )
    )


    selection = points.select_enclosed_points(
        outer,
        tolerance=CONTAINMENT_TOLERANCE,
        check_surface=True,
    )


    inside = np.asarray(
        selection["SelectedPoints"]
    ).astype(bool)


    total = len(inside)

    n_inside = int(
        inside.sum()
    )

    n_outside = int(
        total - n_inside
    )

    percent = (
        100.0
        * n_inside
        / total
    )


    print(f"\n{description}")
    print("-" * 72)

    print(
        f"Total vertices     : "
        f"{total:,}"
    )

    print(
        f"Inside             : "
        f"{n_inside:,}"
    )

    print(
        f"Outside/touching   : "
        f"{n_outside:,}"
    )

    print(
        f"Containment        : "
        f"{percent:.6f}%"
    )


    outside_points = np.asarray(
        inner.points
    )[~inside]


    return {
        "passed": n_outside == 0,
        "total": total,
        "inside": n_inside,
        "outside": n_outside,
        "percent": percent,
        "outside_points": outside_points,
    }


# ============================================================
# Surface separation
# ============================================================

def surface_distance(
    source,
    target,
    description,
):
    """
    Compute unsigned closest-surface distances from all
    source vertices to target.
    """

    distance_mesh = source.compute_implicit_distance(
        target,
        inplace=False,
    )

    signed_distance = np.asarray(
        distance_mesh["implicit_distance"]
    )

    distance = np.abs(
        signed_distance
    )


    print(f"\n{description}")
    print("-" * 72)

    print(
        f"minimum : "
        f"{distance.min():.6f} mm"
    )

    print(
        f"5%      : "
        f"{np.percentile(distance, 5):.6f} mm"
    )

    print(
        f"median  : "
        f"{np.median(distance):.6f} mm"
    )

    print(
        f"mean    : "
        f"{np.mean(distance):.6f} mm"
    )

    print(
        f"95%     : "
        f"{np.percentile(distance, 95):.6f} mm"
    )

    print(
        f"maximum : "
        f"{distance.max():.6f} mm"
    )


    return distance


# ============================================================
# Master-surface geometric deviation
# ============================================================

def geometric_error_against_master(
    reduced,
    master,
    description,
):
    """
    Measure reduced-mesh vertex distance from the original
    master surface.

    This is a reduced->master surface deviation, not a fully
    symmetric Hausdorff distance.
    """

    distance_mesh = (
        reduced.compute_implicit_distance(
            master,
            inplace=False,
        )
    )

    distance = np.abs(
        np.asarray(
            distance_mesh[
                "implicit_distance"
            ]
        )
    )


    print(f"\n{description}")
    print("-" * 72)

    print(
        f"minimum deviation : "
        f"{distance.min():.6f} mm"
    )

    print(
        f"median deviation  : "
        f"{np.median(distance):.6f} mm"
    )

    print(
        f"mean deviation    : "
        f"{np.mean(distance):.6f} mm"
    )

    print(
        f"95% deviation     : "
        f"{np.percentile(distance, 95):.6f} mm"
    )

    print(
        f"maximum deviation : "
        f"{distance.max():.6f} mm"
    )


    return distance


# ============================================================
# Confirm paths
# ============================================================

print("\nBEM TOPOLOGY-PRESERVING DECIMATION")
print("=" * 72)

print("\nMaster directory:")
print(MASTER_DIR)

print("\nOutput directory:")
print(OUTPUT_DIR)


for name, path in MASTER_PATHS.items():

    if not path.exists():

        raise FileNotFoundError(
            f"\nMissing master surface:\n"
            f"{path}\n\n"
            "Expected files:\n"
            "  surfaces_master/inner_skull.vtk\n"
            "  surfaces_master/outer_skull.vtk\n"
            "  surfaces_master/outer_skin.vtk\n"
        )


# ============================================================
# Load master surfaces
# ============================================================

print("\n\nLOADING MASTER SURFACES")
print("=" * 72)

master = {}


for name in SURFACE_NAMES:

    master[name] = load_surface(
        MASTER_PATHS[name]
    )

    metrics = print_topology(
        f"MASTER: {name}",
        master[name],
    )

    # The master surfaces are supposed to be frozen and valid.
    # Abort if that assumption is no longer true.

    if (
        metrics["boundary_edges"] != 0
        or metrics["non_manifold_edges"] != 0
        or metrics["regions"] != 1
    ):

        raise RuntimeError(
            f"Master surface '{name}' is not "
            "closed/manifold/single-region.\n"
            "Do not decimate it."
        )


# ============================================================
# Decimate
# ============================================================

print("\n\nDECIMATING SURFACES")
print("=" * 72)

reduced = {}


for name in SURFACE_NAMES:

    print(
        f"\n{name.upper()}"
    )

    print("=" * 72)

    reduced[name] = decimate_surface(
        master[name],
        TARGET_TRIANGLES[name],
    )

    print_topology(
        f"DECIMATED: {name}",
        reduced[name],
    )


# ============================================================
# Topology validation
# ============================================================

print("\n\nTOPOLOGY VALIDATION")
print("=" * 72)

topology_results = {}


for name in SURFACE_NAMES:

    metrics = topology_metrics(
        reduced[name]
    )

    topology_results[name] = {
        "closed":
            metrics["boundary_edges"] == 0,

        "manifold":
            metrics["non_manifold_edges"] == 0,

        "single_region":
            metrics["regions"] == 1,
    }


    print(f"\n{name}:")

    print(
        f"  closed               "
        f"{'PASS' if topology_results[name]['closed'] else 'FAIL'}"
    )

    print(
        f"  manifold             "
        f"{'PASS' if topology_results[name]['manifold'] else 'FAIL'}"
    )

    print(
        f"  single_region        "
        f"{'PASS' if topology_results[name]['single_region'] else 'FAIL'}"
    )


all_topology_passed = all(
    all(result.values())
    for result in topology_results.values()
)


# ============================================================
# IMPORTANT:
#
# Do NOT attempt containment on invalid surfaces.
# This avoids the crash from the previous script and, more
# importantly, prevents us from hiding topology failures with
# check_surface=False.
# ============================================================

if not all_topology_passed:

    print("\n" + "=" * 72)

    print(
        "DECIMATION TOPOLOGY VALIDATION: FAIL"
    )

    print("=" * 72)

    print(
        "\nAt least one decimated surface is not "
        "closed/manifold/single-region."
    )

    print(
        "\nNo nesting test was performed."
    )

    print(
        "No MNE validation should be performed."
    )

    print(
        "\nThe frozen surfaces_master files were not modified."
    )

    raise SystemExit(1)


# ============================================================
# Nesting validation
# ============================================================

print("\n\nNESTING VALIDATION")
print("=" * 72)


inner_outer = containment_test(
    reduced["inner_skull"],
    reduced["outer_skull"],
    "Inner skull inside outer skull",
)


outer_skin = containment_test(
    reduced["outer_skull"],
    reduced["outer_skin"],
    "Outer skull inside outer skin",
)


# ============================================================
# Inner -> outer skull separation
# ============================================================

print(
    "\n\nINNER -> OUTER SKULL SEPARATION"
)

print("=" * 72)


inner_outer_distance = surface_distance(
    reduced["inner_skull"],
    reduced["outer_skull"],
    "Decimated inner-skull -> outer-skull distance",
)


thresholds = (
    0.10,
    0.25,
    0.50,
    1.00,
    2.00,
    3.00,
)


print("\nSeparation distribution:")


for threshold in thresholds:

    count = int(
        np.sum(
            inner_outer_distance
            <= threshold
        )
    )

    percent = (
        100.0
        * count
        / len(inner_outer_distance)
    )

    print(
        f"<= {threshold:4.2f} mm : "
        f"{count:7,} vertices "
        f"({percent:7.3f}%)"
    )


min_skull_separation = float(
    inner_outer_distance.min()
)


# ============================================================
# Geometric deviation from frozen master surfaces
# ============================================================

print(
    "\n\nGEOMETRIC DEVIATION FROM MASTER"
)

print("=" * 72)


geometry_errors = {}


for name in SURFACE_NAMES:

    geometry_errors[name] = (
        geometric_error_against_master(
            reduced[name],
            master[name],
            (
                f"{name}: "
                "decimated -> master deviation"
            ),
        )
    )


# ============================================================
# Final validation
# ============================================================

print(
    "\n\nFINAL DECIMATION VALIDATION"
)

print("=" * 72)


checks = {}


for name in SURFACE_NAMES:

    checks[
        f"{name}: closed"
    ] = topology_results[name]["closed"]

    checks[
        f"{name}: manifold"
    ] = topology_results[name]["manifold"]

    checks[
        f"{name}: single region"
    ] = topology_results[name]["single_region"]


checks[
    "inner skull inside outer skull"
] = inner_outer["passed"]


checks[
    "outer skull inside outer skin"
] = outer_skin["passed"]


checks[
    "positive inner -> outer skull separation"
] = (
    min_skull_separation
    > MIN_REQUIRED_SKULL_SEPARATION_MM
)


for label, passed in checks.items():

    print(
        f"{label:<52} "
        f"{'PASS' if passed else 'FAIL'}"
    )


all_passed = all(
    checks.values()
)


# ============================================================
# Save only valid computational surfaces
#
# This is intentional:
# invalid decimated surfaces are NOT written into surfaces_mne.
# ============================================================

if all_passed:

    print(
        "\n\nSAVING VALID COMPUTATIONAL BEM SURFACES"
    )

    print("=" * 72)


    for name in SURFACE_NAMES:

        output_path = OUTPUT_PATHS[name]

        reduced[name].save(
            output_path
        )

        print(
            f"{name:<12}: "
            f"{output_path}"
        )

else:

    print(
        "\nDecimated surfaces were NOT saved because "
        "validation failed."
    )


# ============================================================
# Visualization
# ============================================================

print(
    "\n\nOPENING DECIMATED BEM VISUALIZATION"
)

print("=" * 72)


plotter = pv.Plotter()


plotter.add_mesh(
    reduced["outer_skin"],
    color="lightgray",
    opacity=0.10,
    smooth_shading=True,
    label="Outer skin",
)


plotter.add_mesh(
    reduced["outer_skull"],
    color="orange",
    opacity=0.20,
    smooth_shading=True,
    label="Outer skull",
)


plotter.add_mesh(
    reduced["inner_skull"],
    color="royalblue",
    opacity=0.35,
    smooth_shading=True,
    label="Inner skull",
)


# ------------------------------------------------------------
# Show any containment violations
# ------------------------------------------------------------

if inner_outer["outside"] > 0:

    bad_inner = pv.PolyData(
        inner_outer["outside_points"]
    )

    plotter.add_mesh(
        bad_inner,
        color="yellow",
        point_size=10,
        render_points_as_spheres=True,
        label="Inner outside outer",
    )


if outer_skin["outside"] > 0:

    bad_outer = pv.PolyData(
        outer_skin["outside_points"]
    )

    plotter.add_mesh(
        bad_outer,
        color="magenta",
        point_size=10,
        render_points_as_spheres=True,
        label="Outer outside skin",
    )


plotter.add_legend()
plotter.add_axes()
plotter.show_grid()
plotter.show()


# ============================================================
# Final message
# ============================================================

print("\n" + "=" * 72)


if all_passed:

    print(
        "TOPOLOGY-PRESERVING COMPUTATIONAL BEM: "
        "PRELIMINARY PASS"
    )

    print(
        "\nThe reduced surfaces passed:"
    )

    print(
        "  - closedness"
    )

    print(
        "  - manifoldness"
    )

    print(
        "  - single-component topology"
    )

    print(
        "  - inner -> outer skull containment"
    )

    print(
        "  - outer skull -> outer skin containment"
    )

    print(
        "  - positive inner -> outer skull separation"
    )

    print(
        "\nNext step:"
    )

    print(
        "Use surfaces_mne for MNE-native BEM validation."
    )

else:

    print(
        "TOPOLOGY-PRESERVING COMPUTATIONAL BEM: "
        "VALIDATION FAILURE"
    )

    print(
        "\nDo NOT run MNE BEM validation or a BEM solution."
    )


print("=" * 72)