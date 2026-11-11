from pathlib import Path

import mne
import numpy as np
import pyvista as pv


# ============================================================
# Paths
# ============================================================

# This script is located at:
#
# COP/
#   stage_2_functional_brain/
#     source_model/
#       bem/
#         prepare_mne_bem.py
#
# parents[3] therefore points to COP/
ROOT = Path(__file__).resolve().parents[3]

BEM_ROOT = (
    ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "bem"
)

# IMPORTANT:
# Use the validated 20,480-triangle computational candidates.
#
# Do NOT use surfaces_master here.
INPUT_DIR = BEM_ROOT / "surfaces_mne"


# ============================================================
# Minimal FreeSurfer-like subject structure expected by MNE
# ============================================================

SUBJECTS_DIR = BEM_ROOT / "mne_subjects"
SUBJECT = "icbm152"

SUBJECT_DIR = SUBJECTS_DIR / SUBJECT
MNE_BEM_DIR = SUBJECT_DIR / "bem"

MNE_BEM_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# Validated reduced BEM candidate surfaces
# ============================================================

SURFACES = {
    "inner_skull": INPUT_DIR / "inner_skull_20480.vtk",
    "outer_skull": INPUT_DIR / "outer_skull_20480.vtk",
    "outer_skin": INPUT_DIR / "outer_skin_20480.vtk",
}


# ============================================================
# Basic path / provenance check
# ============================================================

print("\n" + "=" * 70)
print("MNE BEM PREPARATION")
print("=" * 70)

print("\nBEM root:")
print(BEM_ROOT)

print("\nInput directory:")
print(INPUT_DIR)

print("\nCandidate surfaces:")

for name, path in SURFACES.items():

    print(
        f"  {name:<12}: {path}"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"\nValidated reduced surface not found:\n"
            f"{path}"
        )


# ============================================================
# Convert PyVista VTK -> FreeSurfer .surf
#
# IMPORTANT:
#
# The custom BEM coordinates are currently in MNI152 space
# and are expressed in millimeters.
#
# mne.write_surface() writes FreeSurfer surface geometry using
# millimeter coordinates, so no mm -> m conversion is performed
# here.
#
# Later, when MNE constructs the BEM model, MNE internally
# represents the BEM surface coordinates in meters.
# ============================================================

print("\n" + "=" * 70)
print("CONVERTING VALIDATED COMPUTATIONAL BEM SURFACES")
print("=" * 70)


for name, input_path in SURFACES.items():

    print("\n" + "-" * 70)
    print(name.upper())
    print("-" * 70)

    # --------------------------------------------------------
    # Load surface
    # --------------------------------------------------------

    mesh = pv.read(input_path)

    # Ensure triangular, clean geometry.
    mesh = mesh.triangulate().clean()

    # --------------------------------------------------------
    # Orient triangle normals consistently outward.
    #
    # MNE requires closed BEM surfaces with consistent
    # orientation.
    #
    # VTK / marching-cubes triangle orientation is not
    # automatically guaranteed to match MNE's convention.
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
    #
    # PyVista triangular face representation:
    #
    # [3, i, j, k,
    #  3, i, j, k,
    #  ...]
    # --------------------------------------------------------

    faces_raw = mesh.faces.reshape(-1, 4)

    if not np.all(
        faces_raw[:, 0] == 3
    ):
        raise RuntimeError(
            f"{name} contains non-triangular faces."
        )

    faces = np.asarray(
        faces_raw[:, 1:4],
        dtype=np.int32,
    )

    # --------------------------------------------------------
    # Expected computational resolution
    # --------------------------------------------------------

    if len(faces) != 20_480:
        raise RuntimeError(
            f"{name} does not have the expected "
            f"20,480 triangles.\n"
            f"Found: {len(faces):,}"
        )

    if len(points) != 10_242:
        print(
            "\nWARNING:"
            f" {name} has {len(points):,} vertices "
            "instead of the expected 10,242."
        )

    # --------------------------------------------------------
    # Report input geometry
    # --------------------------------------------------------

    print(
        f"Input vertices : {len(points):,}"
    )

    print(
        f"Input triangles: {len(faces):,}"
    )

    print("\nInput bounds [mm]:")

    print(
        "  x:",
        f"{points[:, 0].min():.3f}",
        "to",
        f"{points[:, 0].max():.3f}",
    )

    print(
        "  y:",
        f"{points[:, 1].min():.3f}",
        "to",
        f"{points[:, 1].max():.3f}",
    )

    print(
        "  z:",
        f"{points[:, 2].min():.3f}",
        "to",
        f"{points[:, 2].max():.3f}",
    )

    # --------------------------------------------------------
    # Write FreeSurfer surface
    # --------------------------------------------------------

    output_path = (
        MNE_BEM_DIR / f"{name}.surf"
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
# Read surfaces back through MNE
#
# This confirms that MNE can parse the generated FreeSurfer
# surface files and that vertex / triangle counts survive
# serialization.
# ============================================================

print("\n\n" + "=" * 70)
print("MNE READ-BACK CHECK")
print("=" * 70)


for name in SURFACES:

    path = (
        MNE_BEM_DIR / f"{name}.surf"
    )

    rr, tris = mne.read_surface(
        path,
    )

    print(
        f"{name:<12} "
        f"vertices={len(rr):>8,}   "
        f"triangles={len(tris):>8,}"
    )

    if len(tris) != 20_480:
        raise RuntimeError(
            f"{name}: triangle count changed after "
            f"FreeSurfer serialization.\n"
            f"Expected 20,480; got {len(tris):,}."
        )


# ============================================================
# Ask MNE to construct the BEM surface model
#
# THIS IS THE IMPORTANT MNE-NATIVE VALIDATION STEP.
#
# ico=None:
#
# We have ALREADY performed FreeSurfer/MNE spherical ico5
# decimation ourselves.
#
# Therefore:
#
#     DO NOT use ico=5 here.
#
# These custom surfaces are not being passed to MNE for another
# round of ico downsampling.
#
#
# Conductivities:
#
#     brain / inner compartment : 0.3 S/m
#     skull                     : 0.006 S/m
#     scalp                     : 0.3 S/m
#
# ============================================================

print("\n\n" + "=" * 70)
print("MNE BEM MODEL VALIDATION")
print("=" * 70)


conductivity = (
    0.3,    # brain
    0.006,  # skull
    0.3,    # scalp
)


try:

    model = mne.make_bem_model(
        subject=SUBJECT,
        ico=None,
        conductivity=conductivity,
        subjects_dir=SUBJECTS_DIR,
        verbose=True,
    )

except Exception as exc:

    print("\n" + "=" * 70)
    print("MNE BEM VALIDATION: FAIL")
    print("=" * 70)

    print(
        "\nMNE rejected the computational "
        "BEM candidate surfaces."
    )

    print(
        "\nError type:"
    )

    print(
        type(exc).__name__
    )

    print(
        "\nError message:"
    )

    print(exc)

    print(
        "\nDo NOT compute a BEM solution."
    )

    print(
        "\nThe original master surfaces and "
        "validated VTK candidates remain unchanged."
    )

    raise


# ============================================================
# If execution reaches this point, MNE accepted the geometry.
# ============================================================

print("\n" + "=" * 70)
print("MNE BEM VALIDATION: PASS")
print("=" * 70)


print(
    "\nNumber of BEM surfaces:",
    len(model),
)


# ============================================================
# Report MNE BEM model
#
# NOTE:
#
# At this stage MNE surface coordinates are expected to be
# represented internally in meters.
# ============================================================

for idx, surf in enumerate(model):

    print("\n" + "-" * 70)

    print(
        f"Surface {idx + 1}"
    )

    print(
        "  conductivity:",
        surf["sigma"],
        "S/m",
    )

    print(
        "  vertices:",
        f"{surf['np']:,}",
    )

    print(
        "  triangles:",
        f"{surf['ntri']:,}",
    )

    rr = surf["rr"]

    print(
        "  bounds [m]:"
    )

    print(
        "    x:",
        f"{rr[:, 0].min():.6f}",
        "to",
        f"{rr[:, 0].max():.6f}",
    )

    print(
        "    y:",
        f"{rr[:, 1].min():.6f}",
        "to",
        f"{rr[:, 1].max():.6f}",
    )

    print(
        "    z:",
        f"{rr[:, 2].min():.6f}",
        "to",
        f"{rr[:, 2].max():.6f}",
    )


# ============================================================
# Save validated BEM SURFACE MODEL
#
# This file contains:
#
#     geometry
#     triangle topology
#     conductivity values
#
# It is NOT yet the numerical BEM solution.
# ============================================================

MODEL_PATH = (
    BEM_ROOT
    / "icbm152-custom-bem.fif"
)


mne.write_bem_surfaces(
    MODEL_PATH,
    model,
    overwrite=True,
)


print("\n" + "=" * 70)
print("VALIDATED BEM SURFACE MODEL SAVED")
print("=" * 70)

print(
    "\nOutput:"
)

print(
    MODEL_PATH
)


# ============================================================
# IMPORTANT
#
# These are the geometrically validated 20,480-triangle
# computational candidate surfaces.
#
# At this point:
#
#   1. Master high-resolution geometry has been preserved.
#
#   2. Spherical ico5 decimation has been performed.
#
#   3. Reduced topology has been validated.
#
#   4. Three-surface containment has been validated.
#
#   5. Positive interface separation has been validated.
#
#   6. This script has now asked MNE itself to validate the
#      custom BEM interfaces.
#
# We intentionally do NOT call:
#
#     mne.make_bem_solution()
#
# in this script.
#
# The numerical BEM solution is the next stage after reviewing
# the MNE-native validation output.
# ============================================================

print("\n" + "=" * 70)
print("GEOMETRY STAGE COMPLETE")
print("=" * 70)

print(
    "\nMNE accepted the three computational BEM surfaces."
)

print(
    "BEM numerical solution NOT computed yet."
)

print(
    "\nNext step:"
)

print(
    "Review this output, then compute and validate "
    "the numerical BEM solution."
)

print("=" * 70)