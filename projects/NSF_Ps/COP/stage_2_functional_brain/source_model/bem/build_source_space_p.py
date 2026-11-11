from pathlib import Path

import mne
import numpy as np
import pandas as pd
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

P = 25000

BEM_ROOT = Path(__file__).resolve().parent

SOURCE_CSV = (
    BEM_ROOT
    / "source_space_candidates"
    / f"source_space_p{P}.csv"
)

INNER_SKULL_PATH = (
    BEM_ROOT
    / "surfaces_mne_ico4"
    / "inner_skull_5120.vtk"
)

OUTPUT_SRC = (
    BEM_ROOT
    / f"icbm152-discrete-p{P}-src.fif"
)


# ============================================================
# Header
# ============================================================

print("=" * 78)
print(f"BUILD MNE DISCRETE SOURCE SPACE: P={P}")
print("=" * 78)


# ============================================================
# 1. Check files
# ============================================================

for path in [
    SOURCE_CSV,
    INNER_SKULL_PATH,
]:

    if not path.exists():

        raise FileNotFoundError(
            f"Missing required file:\n{path}"
        )

    print(f"PASS  {path.name}")


# ============================================================
# 2. Load cortical candidate table
# ============================================================

sources = pd.read_csv(
    SOURCE_CSV
)

print("\n" + "=" * 78)
print("SOURCE TABLE")
print("=" * 78)

print(
    f"\nRows    : {len(sources):,}"
)

print(
    f"Columns : {list(sources.columns)}"
)


required_columns = {
    "source_index",
    "vertex",
    "fsaverage_vertex",
    "hemisphere",
    "parcel",
    "mni152_r",
    "mni152_a",
    "mni152_s",
}

missing = (
    required_columns
    - set(sources.columns)
)

if missing:

    raise RuntimeError(
        "Source table is missing required columns:\n"
        f"{sorted(missing)}"
    )


if len(sources) != P:

    raise RuntimeError(
        f"Expected {P:,} sources, "
        f"found {len(sources):,}."
    )


# ============================================================
# 3. Load source coordinates
#
# CSV:
#     MNI152 coordinates in millimeters
#
# MNE:
#     MRI coordinates in meters
# ============================================================

source_xyz_mm = (
    sources[
        [
            "mni152_r",
            "mni152_a",
            "mni152_s",
        ]
    ]
    .to_numpy(dtype=float)
)


if not np.isfinite(
    source_xyz_mm
).all():

    raise RuntimeError(
        "Non-finite source coordinates detected."
    )


source_xyz_m = (
    source_xyz_mm
    / 1000.0
)


print("\nCoordinate system:")
print(
    "  source CSV : ICBM152/MNI152 anatomical coordinates"
)

print(
    "  CSV units  : millimeters"
)

print(
    "  MNE units  : meters"
)


print("\nSource coordinate bounds [mm]:")

print(
    f"  x : "
    f"{source_xyz_mm[:, 0].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 0].max():.3f}"
)

print(
    f"  y : "
    f"{source_xyz_mm[:, 1].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 1].max():.3f}"
)

print(
    f"  z : "
    f"{source_xyz_mm[:, 2].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 2].max():.3f}"
)


# ============================================================
# 4. Validate source uniqueness
# ============================================================

unique_coordinates = np.unique(
    source_xyz_mm,
    axis=0,
)

print(
    f"\nUnique coordinates : "
    f"{len(unique_coordinates):,}"
)

if len(unique_coordinates) != P:

    raise RuntimeError(
        "Duplicate source coordinates detected."
    )


# ============================================================
# 5. Hemisphere validation
# ============================================================

hemisphere = (
    sources["hemisphere"]
    .astype(str)
    .str.upper()
    .to_numpy()
)

lh_mask = np.array(
    [
        value.startswith("L")
        for value in hemisphere
    ]
)

rh_mask = np.array(
    [
        value.startswith("R")
        for value in hemisphere
    ]
)


n_lh = int(
    lh_mask.sum()
)

n_rh = int(
    rh_mask.sum()
)


print("\nHemisphere counts:")

print(
    f"  LH : {n_lh:,}"
)

print(
    f"  RH : {n_rh:,}"
)


if (
    n_lh
    + n_rh
    != P
):

    raise RuntimeError(
        "Some sources do not have recognizable "
        "LH/RH hemisphere labels."
    )


# ============================================================
# 6. Validate source_index
# ============================================================

source_index = (
    sources["source_index"]
    .to_numpy(dtype=int)
)

expected_index = np.arange(
    P,
    dtype=int,
)

if not np.array_equal(
    source_index,
    expected_index,
):

    raise RuntimeError(
        "source_index is not sequential 0..P-1."
    )


print(
    "\nsource_index 0..P-1: PASS"
)


# ============================================================
# 7. Validate containment relative to inner skull
#
# This is an independent geometry check using the ico4
# inner-skull mesh.
# ============================================================

print("\n" + "=" * 78)
print("INNER-SKULL CONTAINMENT CHECK")
print("=" * 78)


inner_skull = pv.read(
    INNER_SKULL_PATH
)

print(
    f"\nInner-skull vertices  : "
    f"{inner_skull.n_points:,}"
)

print(
    f"Inner-skull triangles : "
    f"{inner_skull.n_cells:,}"
)


source_cloud = pv.PolyData(
    source_xyz_mm
)


# ------------------------------------------------------------
# Use PyVista enclosed-point test
#
# The inner skull is already a validated closed surface.
# ------------------------------------------------------------

selection = (
    source_cloud
    .select_enclosed_points(
        inner_skull,
        tolerance=0.0,
        check_surface=True,
    )
)


inside = (
    selection[
        "SelectedPoints"
    ]
    .astype(bool)
)


n_inside = int(
    inside.sum()
)

n_outside = int(
    (~inside).sum()
)


print(
    f"\nInside inner skull : "
    f"{n_inside:,} / {P:,}"
)

print(
    f"Outside inner skull: "
    f"{n_outside:,}"
)


if n_outside > 0:

    outside_indices = np.where(
        ~inside
    )[0]

    print(
        "\nOutside source indices:"
    )

    print(
        outside_indices[:50]
    )

    raise RuntimeError(
        f"{n_outside} cortical sources lie "
        "outside the inner skull."
    )


print(
    "\nInner-skull containment: PASS"
)


# ============================================================
# 8. Source orientation strategy
#
# IMPORTANT:
#
# We do NOT currently have validated anatomical cortical
# normals for these custom source points.
#
# Therefore:
#
#   - do NOT invent radial normals
#   - do NOT constrain sources to arbitrary directions
#   - construct a FREE-ORIENTATION discrete source space
#
# For MNE discrete source-space construction, a direction
# array is required. We provide a normalized placeholder
# direction only to define the discrete source-space geometry.
#
# The subsequent forward model will be kept FREE orientation,
# so the physical forward operator will retain three
# orthogonal dipole components per source.
#
# These placeholder directions must NOT later be interpreted
# as cortical normals.
# ============================================================

print("\n" + "=" * 78)
print("SOURCE ORIENTATION STRATEGY")
print("=" * 78)

print(
    """
No validated cortical normals are currently available.

Strategy:

    source geometry : discrete cortical points
    inverse geometry: custom ICBM152/MNI152
    orientation     : FREE

No radial-normal assumption will be made.
No fixed-orientation constraint will be applied.
"""
)


# ============================================================
# 9. Placeholder direction vectors
#
# mne.setup_volume_source_space(pos=dict(...)) expects:
#
#     rr : source positions [m]
#     nn : unit vectors
#
# We use a constant unit vector ONLY as required metadata for
# discrete source-space construction.
#
# It is not being asserted as the anatomical orientation.
# ============================================================

placeholder_nn = np.zeros(
    (
        P,
        3,
    ),
    dtype=float,
)

placeholder_nn[:, 2] = 1.0


norms = np.linalg.norm(
    placeholder_nn,
    axis=1,
)


if not np.allclose(
    norms,
    1.0,
):

    raise RuntimeError(
        "Placeholder direction vectors are not unit length."
    )


print(
    "Placeholder direction-vector norms: PASS"
)


# ============================================================
# 10. Construct MNE discrete source space
#
# Using pos=dict(rr=..., nn=...) tells MNE to use the
# explicitly supplied source positions rather than generate
# a regular volumetric grid.
#
# sphere=None:
#     We are not using a spherical volume model to generate
#     positions.
#
# bem=None:
#     We already independently validated the candidate
#     positions relative to the inner skull.
#
# mindist=0:
#     Do not remove any of our validated cortical candidates.
# ============================================================

print("\n" + "=" * 78)
print("CONSTRUCT MNE SOURCE SPACE")
print("=" * 78)


pos = {
    "rr": source_xyz_m,
    "nn": placeholder_nn,
}


src = mne.setup_volume_source_space(
    subject=None,
    pos=pos,
    mri=None,
    sphere=None,
    bem=None,
    surface=None,
    mindist=0.0,
    exclude=0.0,
    verbose=True,
)


print(
    "\nMNE source-space object created."
)

print(
    src
)


# ============================================================
# 11. Basic structural validation
# ============================================================

print("\n" + "=" * 78)
print("MNE SOURCE-SPACE STRUCTURAL VALIDATION")
print("=" * 78)


if len(src) != 1:

    raise RuntimeError(
        f"Expected one discrete source-space entry, "
        f"found {len(src)}."
    )


src0 = src[0]


print(
    f"\nSource-space type : "
    f"{src0.get('type', 'UNKNOWN')}"
)

print(
    f"np                : "
    f"{src0['np']:,}"
)

print(
    f"nuse              : "
    f"{src0['nuse']:,}"
)


if src0["nuse"] != P:

    raise RuntimeError(
        f"MNE retained {src0['nuse']:,} sources "
        f"instead of {P:,}."
    )


print(
    "\nMNE retained all candidate sources: PASS"
)


# ============================================================
# 12. Extract active MNE positions
# ============================================================

vertno = np.asarray(
    src0["vertno"],
    dtype=int,
)


mne_xyz_m = (
    np.asarray(
        src0["rr"],
        dtype=float,
    )[vertno]
)


mne_xyz_mm = (
    mne_xyz_m
    * 1000.0
)


print(
    f"\nActive MNE positions : "
    f"{len(mne_xyz_mm):,}"
)


# ============================================================
# 13. Validate coordinate preservation
#
# Because this is an explicitly supplied discrete source
# space, the MNE coordinates should reproduce our candidate
# coordinates.
#
# We compare point-by-point first.
# ============================================================

if mne_xyz_mm.shape != source_xyz_mm.shape:

    raise RuntimeError(
        "MNE active-coordinate array has an "
        "unexpected shape."
    )


pointwise_error_mm = np.linalg.norm(
    mne_xyz_mm
    - source_xyz_mm,
    axis=1,
)


print("\nCoordinate preservation:")

print(
    f"  median error : "
    f"{np.median(pointwise_error_mm):.12e} mm"
)

print(
    f"  mean error   : "
    f"{pointwise_error_mm.mean():.12e} mm"
)

print(
    f"  max error    : "
    f"{pointwise_error_mm.max():.12e} mm"
)


# Allow extremely small floating-point differences.
COORD_TOL_MM = 1e-8


if (
    pointwise_error_mm.max()
    > COORD_TOL_MM
):

    raise RuntimeError(
        "MNE source-space coordinates do not "
        "reproduce the candidate coordinates "
        "within tolerance."
    )


print(
    "\nCoordinate preservation: PASS"
)


# ============================================================
# 14. Coordinate-frame validation
# ============================================================

coord_frame = src0[
    "coord_frame"
]


print(
    f"\nMNE coordinate-frame code : "
    f"{coord_frame}"
)


# MNE FIFF coordinate-frame constant for MRI.
MRI_FRAME = (
    mne.io.constants.FIFF
    .FIFFV_COORD_MRI
)


if coord_frame != MRI_FRAME:

    raise RuntimeError(
        "Discrete source space is not in the "
        "MRI coordinate frame."
    )


print(
    "MNE coordinate frame = MRI: PASS"
)


# ============================================================
# 15. Validate direction metadata
# ============================================================

mne_nn = np.asarray(
    src0["nn"],
    dtype=float,
)[vertno]


nn_norm = np.linalg.norm(
    mne_nn,
    axis=1,
)


print("\nDirection metadata:")

print(
    f"  min norm : "
    f"{nn_norm.min():.12f}"
)

print(
    f"  max norm : "
    f"{nn_norm.max():.12f}"
)


if not np.allclose(
    nn_norm,
    1.0,
    atol=1e-12,
):

    raise RuntimeError(
        "MNE source direction metadata contains "
        "non-unit vectors."
    )


print(
    "Direction metadata unit length: PASS"
)

print(
    "\nIMPORTANT:"
)

print(
    "These direction vectors are placeholder metadata."
)

print(
    "They are NOT validated cortical normals."
)

print(
    "The forward model must remain FREE orientation."
)


# ============================================================
# 16. Save source space
# ============================================================

print("\n" + "=" * 78)
print("SAVE SOURCE SPACE")
print("=" * 78)


mne.write_source_spaces(
    OUTPUT_SRC,
    src,
    overwrite=True,
)


print(
    f"\nSaved:\n{OUTPUT_SRC}"
)


# ============================================================
# 17. Read-back validation
# ============================================================

src_loaded = mne.read_source_spaces(
    OUTPUT_SRC,
    verbose=False,
)


if len(src_loaded) != 1:

    raise RuntimeError(
        "Unexpected number of source-space entries "
        "after read-back."
    )


loaded0 = src_loaded[0]


if loaded0["nuse"] != P:

    raise RuntimeError(
        "Source count changed after FIF read-back."
    )


loaded_vertno = np.asarray(
    loaded0["vertno"],
    dtype=int,
)


loaded_xyz_mm = (
    np.asarray(
        loaded0["rr"],
        dtype=float,
    )[loaded_vertno]
    * 1000.0
)


if loaded_xyz_mm.shape != source_xyz_mm.shape:

    raise RuntimeError(
        "Read-back coordinate shape mismatch."
    )


readback_error_mm = np.linalg.norm(
    loaded_xyz_mm
    - source_xyz_mm,
    axis=1,
)


print(
    "\nRead-back coordinate difference:"
)

print(
    f"  median : "
    f"{np.median(readback_error_mm):.12e} mm"
)

print(
    f"  mean   : "
    f"{readback_error_mm.mean():.12e} mm"
)

print(
    f"  max    : "
    f"{readback_error_mm.max():.12e} mm"
)


# FIF may serialize coordinates at slightly reduced numerical
# precision, as we already observed for the HEAD -> MRI
# transform.
READBACK_TOL_MM = 1e-4


if (
    readback_error_mm.max()
    > READBACK_TOL_MM
):

    raise RuntimeError(
        "Source-space coordinates changed beyond "
        "the accepted FIF serialization tolerance."
    )


print(
    "\nSource-space FIF read-back: PASS"
)


# ============================================================
# 18. Preserve source metadata mapping
#
# The FIF source-space object does not preserve all of our
# custom CSV metadata such as parcel and fsaverage_vertex.
#
# Therefore the original candidate CSV remains the canonical
# metadata table.
#
# Save a companion mapping table explicitly documenting the
# relationship between MNE source order and master vertices.
# ============================================================

MAPPING_PATH = (
    BEM_ROOT
    / f"icbm152-discrete-p{P}-source-mapping.csv"
)


mapping = pd.DataFrame(
    {
        "mne_source_index":
            np.arange(
                P,
                dtype=int,
            ),

        "candidate_source_index":
            sources[
                "source_index"
            ].to_numpy(),

        "master_vertex":
            sources[
                "vertex"
            ].to_numpy(),

        "fsaverage_vertex":
            sources[
                "fsaverage_vertex"
            ].to_numpy(),

        "hemisphere":
            sources[
                "hemisphere"
            ].to_numpy(),

        "parcel":
            sources[
                "parcel"
            ].to_numpy(),

        "mni152_r_mm":
            source_xyz_mm[:, 0],

        "mni152_a_mm":
            source_xyz_mm[:, 1],

        "mni152_s_mm":
            source_xyz_mm[:, 2],
    }
)


mapping.to_csv(
    MAPPING_PATH,
    index=False,
)


print(
    f"\nSaved source mapping:\n"
    f"{MAPPING_PATH}"
)


# ============================================================
# 19. Final summary
# ============================================================

print("\n" + "=" * 78)
print("FINAL SUMMARY")
print("=" * 78)


print(
    f"""
Source-space density:

    P = {P:,}

Master framework:

    25,000 cortical points

Nested candidate:

    S_2500

Hemisphere distribution:

    LH = {n_lh:,}
    RH = {n_rh:,}

Coordinate system:

    ICBM152 / MNI152
    MNE coordinate frame = MRI

Coordinate units:

    candidate CSV = mm
    MNE source space = m

Inner-skull containment:

    {n_inside:,} / {P:,} inside
    {n_outside:,} outside

Source orientation:

    FREE orientation planned

    3 orthogonal dipole components per source
    will be retained in the forward operator.

    Expected free-orientation source components:

        3 x {P:,} = {3 * P:,}

IMPORTANT:

    The nn vectors stored in this discrete source-space
    object are placeholder direction metadata only.

    They must NOT be interpreted as anatomical cortical
    normals.

Output source space:

    {OUTPUT_SRC}

Metadata mapping:

    {MAPPING_PATH}

Next step after this object passes validation:

    Construct and validate G_2500

Then repeat the validated architecture for:

    G_5000
    G_10000

and use the resulting inverse solutions for the
source-density convergence analysis.
"""
)


print(
    f"MNE DISCRETE SOURCE SPACE P={P}: PASS"
)

print("=" * 78)