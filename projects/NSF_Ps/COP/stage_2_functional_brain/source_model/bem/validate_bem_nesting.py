from pathlib import Path

import numpy as np
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent
SURFACE_DIR = ROOT / "surfaces_mne"

INNER_PATH = SURFACE_DIR / "inner_skull_20480.vtk"
OUTER_PATH = SURFACE_DIR / "outer_skull_20480.vtk"
SKIN_PATH = SURFACE_DIR / "outer_skin_20480.vtk"


# ============================================================
# Helpers
# ============================================================

def load_surface(path, name):
    if not path.exists():
        raise FileNotFoundError(
            f"{name} surface not found:\n{path}"
        )

    mesh = pv.read(path)
    mesh = mesh.triangulate().clean()

    print(
        f"{name:12s}: "
        f"{mesh.n_points:,} vertices, "
        f"{mesh.n_cells:,} triangles"
    )

    return mesh


def signed_distances(source, target):
    """
    Signed implicit distance from every source vertex to target surface.

    For a consistently oriented closed surface, the sign distinguishes
    the two sides of the target surface. We do NOT rely on the sign alone
    for containment; explicit point-in-surface classification is used
    below.
    """
    temp = source.copy()

    temp.compute_implicit_distance(
        target,
        inplace=True,
    )

    return np.asarray(
        temp["implicit_distance"],
        dtype=float,
    )


def absolute_surface_distances(source, target):
    return np.abs(
        signed_distances(source, target)
    )


def containment_report(inner, outer, name):
    """
    Test whether every vertex of 'inner' is enclosed by 'outer'.

    PyVista/VTK enclosed-point classification is used rather than
    assuming a particular normal orientation.
    """

    result = inner.select_enclosed_points(
        outer,
        tolerance=1e-6,
        check_surface=True,
    )

    selected = np.asarray(
        result["SelectedPoints"]
    ).astype(bool)

    inside = int(np.count_nonzero(selected))
    outside = int(len(selected) - inside)

    pct_inside = 100.0 * inside / len(selected)

    print("\n" + "=" * 72)
    print(name)
    print("=" * 72)

    print(f"Tested vertices : {len(selected):,}")
    print(f"Inside          : {inside:,}")
    print(f"Outside         : {outside:,}")
    print(f"Containment     : {pct_inside:.6f}%")

    return {
        "inside": inside,
        "outside": outside,
        "percent_inside": pct_inside,
        "mask": selected,
    }


def separation_report(inner, outer, name):
    """
    Measure vertex-to-continuous-surface distance from the inner
    interface to the outer interface.
    """

    d = absolute_surface_distances(
        inner,
        outer,
    )

    print("\n" + "=" * 72)
    print(name)
    print("=" * 72)

    print(f"Samples  : {len(d):,}")
    print(f"Minimum  : {np.min(d):.6f} mm")
    print(f"Median   : {np.median(d):.6f} mm")
    print(f"Mean     : {np.mean(d):.6f} mm")
    print(f"5th pct  : {np.percentile(d, 5):.6f} mm")
    print(f"1st pct  : {np.percentile(d, 1):.6f} mm")
    print(f"Maximum  : {np.max(d):.6f} mm")

    print("\nNear-separation counts:")

    for threshold in [
        0.10,
        0.25,
        0.50,
        1.00,
        2.00,
        3.00,
    ]:
        count = int(
            np.count_nonzero(d <= threshold)
        )

        pct = 100.0 * count / len(d)

        print(
            f"  <= {threshold:4.2f} mm : "
            f"{count:6,d} "
            f"({pct:8.4f}%)"
        )

    min_idx = int(np.argmin(d))
    xyz = inner.points[min_idx]

    print("\nMinimum-separation location:")
    print(f"  Vertex index : {min_idx}")
    print(f"  Distance     : {d[min_idx]:.6f} mm")
    print(
        f"  XYZ          : "
        f"({xyz[0]:.3f}, "
        f"{xyz[1]:.3f}, "
        f"{xyz[2]:.3f}) mm"
    )

    return d


# ============================================================
# Load reduced BEM surfaces
# ============================================================

print("=" * 72)
print("REDUCED BEM NESTING AND SEPARATION VALIDATION")
print("=" * 72)

print("\nLoading surfaces:")

inner = load_surface(
    INNER_PATH,
    "Inner skull",
)

outer = load_surface(
    OUTER_PATH,
    "Outer skull",
)

skin = load_surface(
    SKIN_PATH,
    "Outer skin",
)


# ============================================================
# Containment
# ============================================================

inner_in_outer = containment_report(
    inner,
    outer,
    "INNER SKULL -> OUTER SKULL CONTAINMENT",
)

outer_in_skin = containment_report(
    outer,
    skin,
    "OUTER SKULL -> OUTER SKIN CONTAINMENT",
)

# Also test inner directly against skin.
inner_in_skin = containment_report(
    inner,
    skin,
    "INNER SKULL -> OUTER SKIN CONTAINMENT",
)


# ============================================================
# Separation
# ============================================================

inner_outer_distance = separation_report(
    inner,
    outer,
    "INNER SKULL -> OUTER SKULL SEPARATION",
)

outer_skin_distance = separation_report(
    outer,
    skin,
    "OUTER SKULL -> OUTER SKIN SEPARATION",
)


# ============================================================
# Overall preliminary decision
# ============================================================

containment_pass = (
    inner_in_outer["outside"] == 0
    and outer_in_skin["outside"] == 0
    and inner_in_skin["outside"] == 0
)

positive_separation = (
    np.min(inner_outer_distance) > 0.0
    and np.min(outer_skin_distance) > 0.0
)


print("\n" + "=" * 72)
print("FINAL REDUCED-BEM GEOMETRY SUMMARY")
print("=" * 72)

print(
    "Inner skull inside outer skull : "
    f"{'PASS' if inner_in_outer['outside'] == 0 else 'FAIL'}"
)

print(
    "Outer skull inside outer skin  : "
    f"{'PASS' if outer_in_skin['outside'] == 0 else 'FAIL'}"
)

print(
    "Inner skull inside outer skin  : "
    f"{'PASS' if inner_in_skin['outside'] == 0 else 'FAIL'}"
)

print(
    "Positive interface separation  : "
    f"{'PASS' if positive_separation else 'FAIL'}"
)

print("-" * 72)

if containment_pass and positive_separation:
    print("PRELIMINARY REDUCED BEM NESTING: PASS")
else:
    print("PRELIMINARY REDUCED BEM NESTING: FAIL")

print("=" * 72)

print(
    "\nNOTE: A PASS here establishes geometric nesting of the reduced "
    "candidate surfaces."
)
print(
    "It does NOT yet constitute MNE-native BEM validation."
)