from pathlib import Path

import numpy as np
import pyvista as pv


# ============================================================
# Paths
# ============================================================

BEM_ROOT = Path(__file__).resolve().parent
COP_ROOT = BEM_ROOT.parents[2]
ANATOMY_DIR = COP_ROOT / "hm_icbm152"

HIGH_MNI = ANATOMY_DIR / "cortex_pial_high_mni152.obj"
HIGH_ORIGINAL = ANATOMY_DIR / "cortex_pial_high.obj"
INFLATED = ANATOMY_DIR / "cortex_pial_inflated.obj"
VERTEX_CSV = ANATOMY_DIR / "brain_vertex_coordinates.csv"


# ============================================================
# Header
# ============================================================

print("=" * 76)
print("CORTICAL REPRESENTATION INSPECTION")
print("=" * 76)

print(f"\nAnatomy directory:\n{ANATOMY_DIR}")


# ============================================================
# File check
# ============================================================

files = {
    "High-resolution MNI cortex": HIGH_MNI,
    "High-resolution original cortex": HIGH_ORIGINAL,
    "Inflated computational cortex": INFLATED,
    "Brain vertex coordinates": VERTEX_CSV,
}

print("\n" + "=" * 76)
print("FILE CHECK")
print("=" * 76)

for name, path in files.items():
    status = "PASS" if path.exists() else "MISSING"
    print(f"{status:8s} {name}")
    print(f"         {path}")


# ============================================================
# Mesh inspection
# ============================================================

def inspect_mesh(name, path):

    if not path.exists():
        return None

    mesh = pv.read(path).triangulate().clean()

    print("\n" + "=" * 76)
    print(name.upper())
    print("=" * 76)

    print(f"Vertices : {mesh.n_points:,}")
    print(f"Triangles: {mesh.n_cells:,}")

    b = mesh.bounds

    print("\nBounds [native file units]:")
    print(f"  x: {b[0]:.3f} to {b[1]:.3f}")
    print(f"  y: {b[2]:.3f} to {b[3]:.3f}")
    print(f"  z: {b[4]:.3f} to {b[5]:.3f}")

    center = np.asarray(mesh.center)

    print("\nCenter:")
    print(
        f"  ({center[0]:.3f}, "
        f"{center[1]:.3f}, "
        f"{center[2]:.3f})"
    )

    return mesh


high_mni = inspect_mesh(
    "High-resolution MNI cortex",
    HIGH_MNI,
)

high_original = inspect_mesh(
    "High-resolution original cortex",
    HIGH_ORIGINAL,
)

inflated = inspect_mesh(
    "Inflated computational cortex",
    INFLATED,
)


# ============================================================
# CSV inspection
# ============================================================

if VERTEX_CSV.exists():

    print("\n" + "=" * 76)
    print("BRAIN VERTEX COORDINATES CSV")
    print("=" * 76)

    # First inspect the raw text so we do not make assumptions
    # about delimiters or column names.
    with open(
        VERTEX_CSV,
        "r",
        encoding="utf-8",
        errors="replace",
    ) as f:

        lines = []

        for _ in range(6):
            line = f.readline()

            if not line:
                break

            lines.append(line.rstrip())

    print("\nFirst lines:")

    for line in lines:
        print(f"  {line}")


# ============================================================
# Important count comparison
# ============================================================

print("\n" + "=" * 76)
print("VERTEX COUNT RELATIONSHIP")
print("=" * 76)

if high_mni is not None:
    print(
        f"High-resolution physical MNI cortex : "
        f"{high_mni.n_points:,}"
    )

if inflated is not None:
    print(
        f"Inflated computational cortex       : "
        f"{inflated.n_points:,}"
    )


if (
    high_mni is not None
    and inflated is not None
):

    ratio = (
        high_mni.n_points
        / inflated.n_points
    )

    print(
        f"\nHigh-resolution / inflated ratio    : "
        f"{ratio:.3f}"
    )


# ============================================================
# Explanation
# ============================================================

print("\n" + "=" * 76)
print("WHY WE ARE DOING THIS")
print("=" * 76)

print(
    """
We currently need to distinguish two concepts:

1. PHYSICAL CORTICAL GEOMETRY

   This is the cortex whose XYZ positions can potentially be
   used to place EEG current sources inside the BEM.

2. COMPUTATIONAL / FUNCTIONAL CORTICAL REPRESENTATION

   This may be a lower-resolution representation used for
   parcellation, visualization, functional signals, or later
   mapping.

Before selecting P = 2,500, 5,000, or 10,000 source locations,
we need to establish whether the existing 25,000-vertex
representation has a known physical correspondence with the
high-resolution MNI cortex.

We will NOT assume that correspondence from vertex counts alone.
"""
)

print("=" * 76)