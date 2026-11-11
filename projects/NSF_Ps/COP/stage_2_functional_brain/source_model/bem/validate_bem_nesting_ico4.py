from pathlib import Path

import numpy as np
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent
SURFACE_DIR = ROOT / "surfaces_mne_ico4"

INNER_PATH = SURFACE_DIR / "inner_skull_5120.vtk"
OUTER_PATH = SURFACE_DIR / "outer_skull_5120.vtk"
SKIN_PATH = SURFACE_DIR / "outer_skin_5120.vtk"


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
        signed_distances(
            source,
            target,
        )
    )


def containment_report(inner, outer, name):

    result = inner.select_enclosed_points(
        outer,
        tolerance=1e-6,
        check_surface=True,
    )

    selected = np.asarray(
        result["SelectedPoints"]
    ).astype(bool)

    inside = int(
        np.count_nonzero(selected)
    )

    outside = int(
        len(selected) - inside
    )

    pct_inside = (
        100.0
        * inside
        / len(selected)
    )

    print("\n" + "=" * 72)
    print(name)
    print("=" * 72)

    print(
        f"Tested vertices : "
        f"{len(selected):,}"
    )

    print(
        f"Inside          : "
        f"{inside:,}"
    )

    print(
        f"Outside         : "
        f"{outside:,}"
    )

    print(
        f"Containment     : "
        f"{pct_inside:.6f}%"
    )

    return {
        "inside": inside,
        "outside": outside,
        "percent_inside": pct_inside,
        "mask": selected,
    }


def separation_report(inner, outer, name):

    d = absolute_surface_distances(
        inner,
        outer,
    )

    print("\n" + "=" * 72)
    print(name)
    print("=" * 72)

    print(
        f"Samples  : "
        f"{len(d):,}"
    )

    print(
        f"Minimum  : "
        f"{np.min(d):.6f} mm"
    )

    print(
        f"Median   : "
        f"{np.median(d):.6f} mm"
    )

    print(
        f"Mean     : "
        f"{np.mean(d):.6f} mm"
    )

    print(
        f"5th pct  : "
        f"{np.percentile(d, 5):.6f} mm"
    )

    print(
        f"1st pct  : "
        f"{np.percentile(d, 1):.6f} mm"
    )

    print(
        f"Maximum  : "
        f"{np.max(d):.6f} mm"
    )

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
            np.count_nonzero(
                d <= threshold
            )
        )

        pct = (
            100.0
            * count
            / len(d)
        )

        print(
            f"  <= {threshold:4.2f} mm : "
            f"{count:6,d} "
            f"({pct:8.4f}%)"
        )

    min_idx = int(
        np.argmin(d)
    )

    xyz = inner.points[min_idx]

    print(
        "\nMinimum-separation location:"
    )

    print(
        f"  Vertex index : "
        f"{min_idx}"
    )

    print(
        f"  Distance     : "
        f"{d[min_idx]:.6f} mm"
    )

    print(
        "  XYZ          : "
        f"({xyz[0]:.3f}, "
        f"{xyz[1]:.3f}, "
        f"{xyz[2]:.3f}) mm"
    )

    return d


# ============================================================
# Main
# ============================================================

print("=" * 72)
print("ICO4 BEM NESTING AND SEPARATION VALIDATION")
print("=" * 72)

print("\nLoading ico4 surfaces:")

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
# Containment tests
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

inner_in_skin = containment_report(
    inner,
    skin,
    "INNER SKULL -> OUTER SKIN CONTAINMENT",
)


# ============================================================
# Separation tests
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
# Overall result
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
print("FINAL ICO4 BEM GEOMETRY SUMMARY")
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

    print(
        "PRELIMINARY ICO4 BEM NESTING: PASS"
    )

else:

    print(
        "PRELIMINARY ICO4 BEM NESTING: FAIL"
    )

print("=" * 72)

print(
    "\nA PASS here does not yet mean that "
    "MNE has accepted the ico4 geometry."
)

print(
    "MNE-native validation remains the next gate."
)