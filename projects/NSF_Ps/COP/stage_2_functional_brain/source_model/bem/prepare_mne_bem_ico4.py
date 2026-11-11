from pathlib import Path

import mne
import numpy as np
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

# This script lives in:
# COP/stage_2_functional_brain/source_model/bem/
#
# parents[3] -> COP/
ROOT = Path(__file__).resolve().parents[3]

BEM_ROOT = (
    ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "bem"
)

# Validated ico4 computational candidates
INPUT_DIR = BEM_ROOT / "surfaces_mne_ico4"

# ------------------------------------------------------------
# IMPORTANT:
# Use a separate MNE subject for ico4 so that the previously
# validated ico5 FreeSurfer surfaces are never overwritten.
# ------------------------------------------------------------

SUBJECTS_DIR = BEM_ROOT / "mne_subjects"

SUBJECT = "icbm152_ico4"

SUBJECT_DIR = SUBJECTS_DIR / SUBJECT

MNE_BEM_DIR = SUBJECT_DIR / "bem"

MNE_BEM_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# ico4 input surfaces
# ============================================================

SURFACES = {
    "inner_skull": (
        INPUT_DIR
        / "inner_skull_5120.vtk"
    ),
    "outer_skull": (
        INPUT_DIR
        / "outer_skull_5120.vtk"
    ),
    "outer_skin": (
        INPUT_DIR
        / "outer_skin_5120.vtk"
    ),
}


# ============================================================
# Expected ico4 resolution
# ============================================================

EXPECTED_VERTICES = 2_562
EXPECTED_TRIANGLES = 5_120


# ============================================================
# Conductivities [S/m]
# ============================================================

CONDUCTIVITY = (
    0.3,    # brain / inner-skull compartment
    0.006,  # skull
    0.3,    # scalp
)


# ============================================================
# Output BEM surface model
# ============================================================

BEM_SURFACE_MODEL_PATH = (
    BEM_ROOT
    / "icbm152-ico4-bem.fif"
)


# ============================================================
# Helper: load and orient a VTK surface
# ============================================================

def load_and_prepare_surface(path, name):
    """
    Load an ico4 VTK surface and prepare it for writing
    as a FreeSurfer-compatible surface.

    The geometry has already passed our independent:
        - topology validation
        - nesting validation
        - interface-separation validation

    This function does not decimate or otherwise alter
    the spatial resolution.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"{name} surface does not exist:\n"
            f"{path}"
        )

    mesh = pv.read(path)

    # Ensure triangle representation.
    mesh = mesh.triangulate()

    # Remove duplicate / unused points if present.
    mesh = mesh.clean()

    # --------------------------------------------------------
    # Orient normals consistently and outward.
    #
    # This was important during the earlier BEM preparation:
    # MNE requires correctly oriented closed surfaces.
    # --------------------------------------------------------

    mesh = mesh.compute_normals(
        cell_normals=True,
        point_normals=True,
        consistent_normals=True,
        auto_orient_normals=True,
        split_vertices=False,
        inplace=False,
    )

    # --------------------------------------------------------
    # Extract vertices
    # --------------------------------------------------------

    points = np.asarray(
        mesh.points,
        dtype=np.float64,
    )

    # --------------------------------------------------------
    # Extract triangular faces
    # --------------------------------------------------------

    faces_raw = np.asarray(
        mesh.faces
    )

    if len(faces_raw) % 4 != 0:
        raise RuntimeError(
            f"{name}: unexpected PyVista face array."
        )

    faces = (
        faces_raw
        .reshape(-1, 4)[:, 1:4]
        .astype(np.int32)
    )

    # --------------------------------------------------------
    # Resolution checks
    # --------------------------------------------------------

    if len(faces) != EXPECTED_TRIANGLES:
        raise RuntimeError(
            f"{name}: expected "
            f"{EXPECTED_TRIANGLES:,} triangles, "
            f"but found {len(faces):,}."
        )

    if len(points) != EXPECTED_VERTICES:
        raise RuntimeError(
            f"{name}: expected "
            f"{EXPECTED_VERTICES:,} vertices, "
            f"but found {len(points):,}."
        )

    return points, faces


# ============================================================
# Header
# ============================================================

print()
print("=" * 70)
print("MNE ICO4 BEM PREPARATION")
print("=" * 70)

print("\nBEM root:")
print(BEM_ROOT)

print("\nInput directory:")
print(INPUT_DIR)

print("\nMNE subject:")
print(SUBJECT)

print("\nMNE subjects directory:")
print(SUBJECTS_DIR)

print("\nCandidate ico4 surfaces:")

for name, path in SURFACES.items():
    print(
        f"  {name:12s}: {path}"
    )


# ============================================================
# Verify all inputs before writing anything
# ============================================================

print()
print("=" * 70)
print("INPUT CHECK")
print("=" * 70)

missing = []

for name, path in SURFACES.items():

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

    print(
        "\nOne or more required ico4 "
        "surfaces are missing."
    )

    raise FileNotFoundError(
        "Cannot continue with "
        "MNE ico4 BEM preparation."
    )


# ============================================================
# Convert VTK -> FreeSurfer .surf
# ============================================================

print()
print("=" * 70)
print("CONVERTING VALIDATED ICO4 COMPUTATIONAL SURFACES")
print("=" * 70)


for name, input_path in SURFACES.items():

    print()
    print("-" * 70)
    print(name.upper())
    print("-" * 70)

    points, faces = load_and_prepare_surface(
        input_path,
        name,
    )

    print(
        f"Input vertices : "
        f"{len(points):,}"
    )

    print(
        f"Input triangles: "
        f"{len(faces):,}"
    )

    # --------------------------------------------------------
    # Bounds
    #
    # Custom surfaces are currently represented in MNI152
    # coordinates in millimeters.
    # FreeSurfer surface geometry is also written in mm.
    # --------------------------------------------------------

    mins = points.min(axis=0)
    maxs = points.max(axis=0)

    print("\nInput bounds [mm]:")

    print(
        f"  x: "
        f"{mins[0]:.3f} to "
        f"{maxs[0]:.3f}"
    )

    print(
        f"  y: "
        f"{mins[1]:.3f} to "
        f"{maxs[1]:.3f}"
    )

    print(
        f"  z: "
        f"{mins[2]:.3f} to "
        f"{maxs[2]:.3f}"
    )

    # --------------------------------------------------------
    # FreeSurfer surface output
    # --------------------------------------------------------

    output_path = (
        MNE_BEM_DIR
        / f"{name}.surf"
    )

    mne.write_surface(
        output_path,
        points,
        faces,
        overwrite=True,
    )

    print("\nWritten:")
    print(output_path)


# ============================================================
# MNE read-back validation
# ============================================================

print()
print()
print("=" * 70)
print("MNE READ-BACK CHECK")
print("=" * 70)


for name in SURFACES:

    surf_path = (
        MNE_BEM_DIR
        / f"{name}.surf"
    )

    rr, tris = mne.read_surface(
        surf_path,
        verbose=False,
    )

    print(
        f"{name:12s}  "
        f"vertices={len(rr):8,d}   "
        f"triangles={len(tris):8,d}"
    )

    if len(rr) != EXPECTED_VERTICES:
        raise RuntimeError(
            f"{name}: read-back vertex "
            f"count changed."
        )

    if len(tris) != EXPECTED_TRIANGLES:
        raise RuntimeError(
            f"{name}: read-back triangle "
            f"count changed."
        )


# ============================================================
# MNE-native BEM geometry validation
# ============================================================

print()
print()
print("=" * 70)
print("MNE ICO4 BEM MODEL VALIDATION")
print("=" * 70)


try:

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # ico=None is deliberate.
    #
    # These surfaces have ALREADY been reduced to ico4
    # resolution using FreeSurfer spherical decimation.
    #
    # We therefore do NOT ask make_bem_model() to perform
    # another ico downsampling operation.
    #
    # This is especially important because our original
    # surfaces are custom voxel-derived ICBM152 boundaries,
    # rather than native FreeSurfer icosahedral surfaces.
    # --------------------------------------------------------

    model = mne.make_bem_model(
        subject=SUBJECT,
        ico=None,
        conductivity=CONDUCTIVITY,
        subjects_dir=SUBJECTS_DIR,
        verbose=True,
    )

except Exception as exc:

    print()
    print("=" * 70)
    print("MNE ICO4 BEM VALIDATION: FAIL")
    print("=" * 70)

    print("\nMNE rejected the ico4 geometry.")

    print("\nError:")
    print(repr(exc))

    print(
        "\nDo NOT compute a BEM solution "
        "and do NOT modify the surfaces yet."
    )

    raise


# ============================================================
# MNE accepted geometry
# ============================================================

print()
print()
print("=" * 70)
print("MNE ICO4 BEM VALIDATION: PASS")
print("=" * 70)

print(
    f"\nNumber of BEM surfaces: "
    f"{len(model)}"
)


# ============================================================
# Inspect MNE's internal representation
# ============================================================

for index, surf in enumerate(
    model,
    start=1,
):

    print()
    print("-" * 70)
    print(f"Surface {index}")

    sigma = surf.get(
        "sigma",
        np.nan,
    )

    rr = np.asarray(
        surf["rr"]
    )

    tris = np.asarray(
        surf["tris"]
    )

    print(
        f"  conductivity: "
        f"{sigma} S/m"
    )

    print(
        f"  vertices: "
        f"{len(rr):,}"
    )

    print(
        f"  triangles: "
        f"{len(tris):,}"
    )

    # --------------------------------------------------------
    # MNE's BEM representation is now in meters.
    # --------------------------------------------------------

    mins = rr.min(axis=0)
    maxs = rr.max(axis=0)

    print(
        "  bounds [m]:"
    )

    print(
        f"    x: "
        f"{mins[0]:.6f} to "
        f"{maxs[0]:.6f}"
    )

    print(
        f"    y: "
        f"{mins[1]:.6f} to "
        f"{maxs[1]:.6f}"
    )

    print(
        f"    z: "
        f"{mins[2]:.6f} to "
        f"{maxs[2]:.6f}"
    )


# ============================================================
# Save MNE BEM surface model
# ============================================================

mne.write_bem_surfaces(
    BEM_SURFACE_MODEL_PATH,
    model,
    overwrite=True,
)


print()
print("=" * 70)
print("VALIDATED ICO4 BEM SURFACE MODEL SAVED")
print("=" * 70)

print("\nOutput:")
print(BEM_SURFACE_MODEL_PATH)


# ============================================================
# Deliberate stopping point
# ============================================================

print()
print("=" * 70)
print("ICO4 GEOMETRY STAGE COMPLETE")
print("=" * 70)

print(
    "\nMNE accepted the three ico4 "
    "computational BEM surfaces."
)

print(
    "\nBEM numerical solution "
    "NOT computed yet."
)

print(
    "\nThe existing ico5 geometry and "
    "MNE model were NOT overwritten."
)

print(
    "\nNext step:"
)

print(
    "Review this output. If MNE-native "
    "validation passes cleanly, compute "
    "and validate the ico4 numerical "
    "BEM solution."
)

print("=" * 70)