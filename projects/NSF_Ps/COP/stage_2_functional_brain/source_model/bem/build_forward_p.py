from pathlib import Path
import json

import mne
import numpy as np
import pandas as pd


# =============================================================================
# CONFIGURATION
# =============================================================================

P = 10000

BEM_ROOT = Path(__file__).resolve().parent
COP_ROOT = BEM_ROOT.parents[2]

SRC_PATH = (
    BEM_ROOT
    / f"icbm152-discrete-p{P}-src.fif"
)

BEM_SOL_PATH = (
    BEM_ROOT
    / "icbm152-ico4-bem-sol.fif"
)

TRANS_PATH = (
    BEM_ROOT
    / "sub-1_ses-0-head-mri-trans.fif"
)

CAPTRAK_PATH = (
    COP_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "source_localization"
    / "sub-1_ses-0_captrak_sensor_geometry.csv"
)

REGISTERED_PATH = (
    COP_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "source_localization"
    / "sub-1_ses-0_captrak_registered_mni152.csv"
)

OUTPUT_DIR = (
    BEM_ROOT
    / "forward_models"
    / f"p{P}"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

FWD_PATH = (
    OUTPUT_DIR
    / f"sub-1_p{P}-eeg-fwd.fif"
)

SUMMARY_PATH = (
    OUTPUT_DIR
    / f"forward_p{P}_qc_summary.txt"
)

QC_CSV_PATH = (
    OUTPUT_DIR
    / f"forward_p{P}_source_norms.csv"
)


# =============================================================================
# HELPERS
# =============================================================================

def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def find_column(df, candidates):
    """
    Find a column name using case-insensitive matching.
    """
    lower_map = {
        str(c).lower(): c
        for c in df.columns
    }

    for candidate in candidates:
        key = candidate.lower()

        if key in lower_map:
            return lower_map[key]

    return None


def detect_name_column(df):
    """
    Detect electrode/channel-name column.
    """

    candidates = [
        "name",
        "channel",
        "channel_name",
        "ch_name",
        "electrode",
        "label",
    ]

    col = find_column(
        df,
        candidates,
    )

    if col is None:
        raise RuntimeError(
            "Could not detect electrode-name column.\n"
            f"Available columns:\n{list(df.columns)}"
        )

    return col


def detect_xyz_columns(df):
    """
    Detect Cartesian coordinate columns.

    The original CapTrak geometry is expected to be in meters.
    """

    candidate_sets = [
        ("x", "y", "z"),
        ("x_m", "y_m", "z_m"),
        ("head_x", "head_y", "head_z"),
        ("head_x_m", "head_y_m", "head_z_m"),
        ("r", "a", "s"),
    ]

    lower_map = {
        str(c).lower(): c
        for c in df.columns
    }

    for candidate_set in candidate_sets:

        if all(
            c.lower() in lower_map
            for c in candidate_set
        ):

            return tuple(
                lower_map[c.lower()]
                for c in candidate_set
            )

    raise RuntimeError(
        "Could not identify XYZ coordinate columns.\n"
        f"Available columns:\n{list(df.columns)}"
    )


# =============================================================================
# HEADER
# =============================================================================

section(
    f"BUILD EEG FORWARD MODEL: P={P}"
)

print(
    """
Purpose:

    Build the first validated EEG forward operator
    using the frozen geometry.

Inputs:

    1. P=2500 MNE discrete source space
    2. ico4 three-layer BEM solution
    3. original 128-channel HEAD-frame CapTrak geometry
    4. frozen HEAD -> MRI transform

Output:

    G_2500

Orientation:

    FREE orientation

No inverse solution is calculated in this script.
"""
)


# =============================================================================
# 1. CHECK INPUT FILES
# =============================================================================

section(
    "CHECK INPUT FILES"
)

required_files = [
    SRC_PATH,
    BEM_SOL_PATH,
    TRANS_PATH,
    CAPTRAK_PATH,
]

for path in required_files:

    if not path.exists():

        raise FileNotFoundError(
            f"Missing required file:\n{path}"
        )

    print(
        f"PASS  {path.name}"
    )


# =============================================================================
# 2. LOAD SOURCE SPACE
# =============================================================================

section(
    "LOAD SOURCE SPACE"
)

src = mne.read_source_spaces(
    SRC_PATH,
    verbose=False,
)

if len(src) != 1:

    raise RuntimeError(
        f"Expected one discrete source space, "
        f"found {len(src)}."
    )

src0 = src[0]

print(
    f"\nType        : {src0['type']}"
)

print(
    f"Total points: {src0['np']:,}"
)

print(
    f"Used points : {src0['nuse']:,}"
)

print(
    f"Coord frame : {src0['coord_frame']}"
)


if src0["type"] != "discrete":

    raise RuntimeError(
        "Expected a discrete source space."
    )


if src0["nuse"] != P:

    raise RuntimeError(
        f"Expected {P:,} active sources, "
        f"found {src0['nuse']:,}."
    )


MRI_FRAME = (
    mne.io.constants.FIFF
    .FIFFV_COORD_MRI
)

if (
    src0["coord_frame"]
    != MRI_FRAME
):

    raise RuntimeError(
        "Source space is not in MRI coordinates."
    )


print(
    "\nSource-space validation: PASS"
)


# =============================================================================
# 3. LOAD BEM SOLUTION
# =============================================================================

section(
    "LOAD BEM SOLUTION"
)

bem = mne.read_bem_solution(
    BEM_SOL_PATH,
    verbose=False,
)

print(
    "\nBEM solution loaded successfully."
)


# Inspect available surfaces
if "surfs" in bem:

    print(
        f"BEM surfaces : {len(bem['surfs'])}"
    )

    for i, surf in enumerate(
        bem["surfs"]
    ):

        print(
            f"  Surface {i + 1}: "
            f"{surf['np']:,} vertices, "
            f"{surf['ntri']:,} triangles"
        )


# Validate numerical solution if exposed
if "solution" in bem:

    bem_solution = np.asarray(
        bem["solution"]
    )

    print(
        f"\nBEM solution shape : "
        f"{bem_solution.shape}"
    )

    if not np.isfinite(
        bem_solution
    ).all():

        raise RuntimeError(
            "BEM solution contains NaN or Inf."
        )

    print(
        "BEM numerical values finite: PASS"
    )


# =============================================================================
# 4. LOAD HEAD -> MRI TRANSFORM
# =============================================================================

section(
    "LOAD HEAD -> MRI TRANSFORM"
)

trans = mne.read_trans(
    TRANS_PATH
)

print(
    "\nLoaded transform:"
)

print(
    trans
)


HEAD_FRAME = (
    mne.io.constants.FIFF
    .FIFFV_COORD_HEAD
)

if (
    trans["from"]
    != HEAD_FRAME
    or
    trans["to"]
    != MRI_FRAME
):

    raise RuntimeError(
        "Transform is not HEAD -> MRI."
    )


T = np.asarray(
    trans["trans"],
    dtype=float,
)

if not np.isfinite(T).all():

    raise RuntimeError(
        "Transform contains non-finite values."
    )


print(
    "\nHEAD -> MRI transform: PASS"
)


# =============================================================================
# 5. LOAD ORIGINAL CAPTRAK SENSOR GEOMETRY
# =============================================================================

section(
    "LOAD ORIGINAL CAPTRAK ELECTRODES"
)

captrak = pd.read_csv(
    CAPTRAK_PATH
)

print(
    f"\nRows    : {len(captrak):,}"
)

print(
    f"Columns : {list(captrak.columns)}"
)


if len(captrak) != 128:

    raise RuntimeError(
        "Expected exactly 128 CapTrak electrodes, "
        f"found {len(captrak)}."
    )


name_col = detect_name_column(
    captrak
)

xyz_cols = detect_xyz_columns(
    captrak
)


print(
    f"\nChannel-name column : {name_col}"
)

print(
    f"Coordinate columns  : {xyz_cols}"
)


ch_names = (
    captrak[name_col]
    .astype(str)
    .str.strip()
    .tolist()
)


if len(set(ch_names)) != 128:

    raise RuntimeError(
        "Channel names are not unique."
    )


head_xyz_m = (
    captrak[
        list(xyz_cols)
    ]
    .to_numpy(dtype=float)
)


if not np.isfinite(
    head_xyz_m
).all():

    raise RuntimeError(
        "CapTrak coordinates contain NaN or Inf."
    )


print(
    "\nOriginal coordinate frame : HEAD"
)

print(
    "Original coordinate units : meters"
)


print(
    "\nHEAD coordinate bounds [m]:"
)

print(
    f"  x : "
    f"{head_xyz_m[:,0].min():.6f} "
    f"to "
    f"{head_xyz_m[:,0].max():.6f}"
)

print(
    f"  y : "
    f"{head_xyz_m[:,1].min():.6f} "
    f"to "
    f"{head_xyz_m[:,1].max():.6f}"
)

print(
    f"  z : "
    f"{head_xyz_m[:,2].min():.6f} "
    f"to "
    f"{head_xyz_m[:,2].max():.6f}"
)


# Sanity check against accidental mm input.
max_abs_head = np.abs(
    head_xyz_m
).max()

if max_abs_head > 1.0:

    raise RuntimeError(
        "CapTrak coordinates appear too large for meters.\n"
        "Possible mm/m unit mismatch."
    )


print(
    "\nCapTrak units sanity check: PASS"
)


# =============================================================================
# 6. CREATE MNE DIGITIZATION MONTAGE
# =============================================================================

section(
    "CREATE MNE EEG MONTAGE"
)


ch_pos = {
    name: xyz
    for name, xyz in zip(
        ch_names,
        head_xyz_m,
    )
}


montage = mne.channels.make_dig_montage(
    ch_pos=ch_pos,
    coord_frame="head",
)


# sfreq is not physically relevant to the static forward operator.
# We use the actual EEG recording rate for consistency.
SFREQ = 500.0


info = mne.create_info(
    ch_names=ch_names,
    sfreq=SFREQ,
    ch_types=["eeg"] * len(ch_names),
)


info.set_montage(
    montage,
    on_missing="raise",
)


print(
    f"\nMNE EEG channels : "
    f"{len(info['ch_names'])}"
)

print(
    f"Sampling rate    : "
    f"{info['sfreq']:.1f} Hz"
)


eeg_picks = mne.pick_types(
    info,
    eeg=True,
    meg=False,
    exclude=[],
)


if len(eeg_picks) != 128:

    raise RuntimeError(
        f"Expected 128 EEG channels in Info, "
        f"found {len(eeg_picks)}."
    )


print(
    "\n128 EEG channels recognized: PASS"
)


# =============================================================================
# 7. VERIFY DIGITIZED ELECTRODE COORDINATES
# =============================================================================

section(
    "VERIFY MNE ELECTRODE GEOMETRY"
)


info_xyz_m = np.array(
    [
        info["chs"][idx]["loc"][:3]
        for idx in eeg_picks
    ],
    dtype=float,
)


if not np.isfinite(
    info_xyz_m
).all():

    raise RuntimeError(
        "MNE Info contains non-finite "
        "electrode coordinates."
    )


geometry_error_m = np.linalg.norm(
    info_xyz_m
    - head_xyz_m,
    axis=1,
)

geometry_error_mm = (
    geometry_error_m
    * 1000.0
)


print(
    f"\nMean geometry reconstruction error : "
    f"{geometry_error_mm.mean():.12e} mm"
)

print(
    f"Max geometry reconstruction error  : "
    f"{geometry_error_mm.max():.12e} mm"
)


if geometry_error_mm.max() > 1e-8:

    raise RuntimeError(
        "MNE Info does not preserve the "
        "CapTrak electrode coordinates."
    )


print(
    "\nMNE electrode geometry: PASS"
)


# =============================================================================
# 8. OPTIONAL CROSS-CHECK AGAINST SAVED REGISTERED MNI COORDINATES
# =============================================================================

section(
    "HEAD -> MRI ELECTRODE CROSS-CHECK"
)


head_homogeneous = np.column_stack(
    [
        head_xyz_m,
        np.ones(
            len(head_xyz_m)
        ),
    ]
)


transformed_xyz_m = (
    T
    @ head_homogeneous.T
).T[:, :3]


transformed_xyz_mm = (
    transformed_xyz_m
    * 1000.0
)


print(
    "\nTransformed electrode bounds [mm]:"
)

print(
    f"  x : "
    f"{transformed_xyz_mm[:,0].min():.3f} "
    f"to "
    f"{transformed_xyz_mm[:,0].max():.3f}"
)

print(
    f"  y : "
    f"{transformed_xyz_mm[:,1].min():.3f} "
    f"to "
    f"{transformed_xyz_mm[:,1].max():.3f}"
)

print(
    f"  z : "
    f"{transformed_xyz_mm[:,2].min():.3f} "
    f"to "
    f"{transformed_xyz_mm[:,2].max():.3f}"
)


if REGISTERED_PATH.exists():

    registered = pd.read_csv(
        REGISTERED_PATH
    )

    registered_name_col = detect_name_column(
        registered
    )

    # Try likely registered-coordinate conventions.
    registered_xyz_candidates = [
        (
            "mni152_r",
            "mni152_a",
            "mni152_s",
        ),
        (
            "x_mni_mm",
            "y_mni_mm",
            "z_mni_mm",
        ),
        (
            "x",
            "y",
            "z",
        ),
    ]

    registered_xyz_cols = None

    lower_map = {
        str(c).lower(): c
        for c in registered.columns
    }

    for candidate_set in registered_xyz_candidates:

        if all(
            c.lower() in lower_map
            for c in candidate_set
        ):

            registered_xyz_cols = tuple(
                lower_map[
                    c.lower()
                ]
                for c in candidate_set
            )

            break


    if registered_xyz_cols is not None:

        reg_lookup = {}

        for _, row in registered.iterrows():

            reg_lookup[
                str(
                    row[
                        registered_name_col
                    ]
                ).strip()
            ] = np.array(
                [
                    row[
                        registered_xyz_cols[0]
                    ],
                    row[
                        registered_xyz_cols[1]
                    ],
                    row[
                        registered_xyz_cols[2]
                    ],
                ],
                dtype=float,
            )


        common_names = [
            name
            for name in ch_names
            if name in reg_lookup
        ]


        if len(common_names) == 128:

            registered_xyz_mm = np.vstack(
                [
                    reg_lookup[name]
                    for name in ch_names
                ]
            )


            # Determine whether registered file is in m or mm.
            if (
                np.abs(
                    registered_xyz_mm
                ).max()
                < 1.0
            ):

                registered_xyz_mm *= 1000.0


            transform_error_mm = np.linalg.norm(
                transformed_xyz_mm
                - registered_xyz_mm,
                axis=1,
            )


            print(
                "\nSaved registered-MNI cross-check:"
            )

            print(
                f"  mean : "
                f"{transform_error_mm.mean():.9f} mm"
            )

            print(
                f"  max  : "
                f"{transform_error_mm.max():.9f} mm"
            )

        else:

            print(
                "\nWARNING:"
            )

            print(
                "Registered-MNI table did not contain "
                "all 128 channel names."
            )

    else:

        print(
            "\nWARNING:"
        )

        print(
            "Could not detect coordinate columns in "
            "registered-MNI file."
        )

else:

    print(
        "\nRegistered-MNI file not found."
    )

    print(
        "Skipping optional transform replay cross-check."
    )


# =============================================================================
# 9. BUILD FORWARD SOLUTION
# =============================================================================

section(
    "BUILD G_2500"
)

print(
    f"""
Forward-model configuration:

    EEG channels       : 128
    Source locations   : {P:,}
    Orientation        : FREE
    Expected components: {3 * P:,}

    Source space:
        {SRC_PATH.name}

    BEM:
        {BEM_SOL_PATH.name}

    Transform:
        {TRANS_PATH.name}

Computing forward solution...
"""
)


fwd = mne.make_forward_solution(
    info=info,
    trans=trans,
    src=src,
    bem=bem,
    meg=False,
    eeg=True,
    mindist=0.0,
    n_jobs=-1,
    verbose=True,
)


print(
    "\nForward solution created."
)


# =============================================================================
# 10. BASIC FORWARD STRUCTURE
# =============================================================================

section(
    "FORWARD STRUCTURAL VALIDATION"
)


print(
    f"\nForward channels : "
    f"{fwd['nchan']:,}"
)

print(
    f"Forward sources  : "
    f"{fwd['nsource']:,}"
)


if fwd["nchan"] != 128:

    raise RuntimeError(
        f"Expected 128 forward channels, "
        f"found {fwd['nchan']}."
    )


if fwd["nsource"] != P:

    raise RuntimeError(
        f"Expected {P:,} forward sources, "
        f"found {fwd['nsource']:,}."
    )


print(
    "\nForward channel/source counts: PASS"
)


# =============================================================================
# 11. EXTRACT GAIN MATRIX
# =============================================================================

section(
    "GAIN MATRIX VALIDATION"
)


G = np.asarray(
    fwd["sol"]["data"],
    dtype=float,
)


print(
    f"\nGain matrix shape:"
)

print(
    f"    G = {G.shape}"
)


expected_shape = (
    128,
    3 * P,
)


if G.shape != expected_shape:

    raise RuntimeError(
        "Unexpected gain-matrix dimensions.\n"
        f"Expected {expected_shape}, "
        f"found {G.shape}."
    )


print(
    "\nExpected free-orientation dimensions: PASS"
)


# =============================================================================
# 12. FINITE VALUE CHECK
# =============================================================================

n_total = G.size

n_finite = int(
    np.isfinite(G).sum()
)

n_nan = int(
    np.isnan(G).sum()
)

n_inf = int(
    np.isinf(G).sum()
)


print(
    f"\nTotal entries : "
    f"{n_total:,}"
)

print(
    f"Finite entries: "
    f"{n_finite:,}"
)

print(
    f"NaN entries   : "
    f"{n_nan:,}"
)

print(
    f"Inf entries   : "
    f"{n_inf:,}"
)


if n_finite != n_total:

    raise RuntimeError(
        "Gain matrix contains NaN or Inf."
    )


print(
    "\nAll gain-matrix entries finite: PASS"
)


# =============================================================================
# 13. NUMERICAL RANGE
# =============================================================================

print(
    "\nGain-matrix numerical summary:"
)

print(
    f"  min    : "
    f"{G.min():.12e}"
)

print(
    f"  max    : "
    f"{G.max():.12e}"
)

print(
    f"  mean   : "
    f"{G.mean():.12e}"
)

print(
    f"  std    : "
    f"{G.std():.12e}"
)

print(
    f"  abs max: "
    f"{np.abs(G).max():.12e}"
)


# =============================================================================
# 14. COLUMN NORMS
#
# Each source has three columns:
#
#     x, y, z dipole components
#
# We examine both component-wise column norms and a combined
# source sensitivity norm.
# =============================================================================

section(
    "SOURCE SENSITIVITY QC"
)


component_norms = np.linalg.norm(
    G,
    axis=0,
)


if len(component_norms) != 3 * P:

    raise RuntimeError(
        "Unexpected number of component norms."
    )


source_component_norms = (
    component_norms
    .reshape(
        P,
        3,
    )
)


source_combined_norm = np.linalg.norm(
    source_component_norms,
    axis=1,
)


print(
    "\nComponent-column norms:"
)

print(
    f"  minimum : "
    f"{component_norms.min():.12e}"
)

print(
    f"  median  : "
    f"{np.median(component_norms):.12e}"
)

print(
    f"  mean    : "
    f"{component_norms.mean():.12e}"
)

print(
    f"  maximum : "
    f"{component_norms.max():.12e}"
)


print(
    "\nCombined source sensitivity norms:"
)

print(
    f"  minimum : "
    f"{source_combined_norm.min():.12e}"
)

print(
    f"  median  : "
    f"{np.median(source_combined_norm):.12e}"
)

print(
    f"  mean    : "
    f"{source_combined_norm.mean():.12e}"
)

print(
    f"  maximum : "
    f"{source_combined_norm.max():.12e}"
)


zero_component_columns = np.where(
    component_norms == 0.0
)[0]


zero_sources = np.where(
    source_combined_norm == 0.0
)[0]


print(
    f"\nExactly zero component columns : "
    f"{len(zero_component_columns):,}"
)

print(
    f"Exactly zero sources           : "
    f"{len(zero_sources):,}"
)


if len(zero_sources) > 0:

    raise RuntimeError(
        "One or more source locations have "
        "zero lead-field sensitivity."
    )


print(
    "\nNo zero-sensitivity sources: PASS"
)


# =============================================================================
# 15. CHECK FOR NON-FINITE OR PATHOLOGICAL SOURCE NORMS
# =============================================================================

if not np.isfinite(
    source_combined_norm
).all():

    raise RuntimeError(
        "Non-finite source sensitivity norms."
    )


if (
    source_combined_norm <= 0
).any():

    raise RuntimeError(
        "Non-positive source sensitivity detected."
    )


print(
    "All source sensitivity norms finite and positive: PASS"
)


# =============================================================================
# 16. CHANNEL VALIDATION
# =============================================================================

section(
    "FORWARD CHANNEL VALIDATION"
)


forward_ch_names = list(
    fwd["sol"]["row_names"]
)


if len(forward_ch_names) != 128:

    raise RuntimeError(
        "Unexpected number of forward channel names."
    )


if forward_ch_names != ch_names:

    print(
        "\nWARNING:"
    )

    print(
        "Forward channel order differs from "
        "the original CapTrak order."
    )

    print(
        "Checking channel-name set..."
    )


    if set(
        forward_ch_names
    ) != set(
        ch_names
    ):

        raise RuntimeError(
            "Forward model channel names do not "
            "match the CapTrak channel set."
        )


    print(
        "Channel-name set matches: PASS"
    )

else:

    print(
        "\nForward channel names and order: PASS"
    )


# =============================================================================
# 17. VERIFY FREE ORIENTATION
# =============================================================================

section(
    "ORIENTATION VALIDATION"
)


source_ori = fwd[
    "source_ori"
]


FREE_ORI = (
    mne.io.constants.FIFF
    .FIFFV_MNE_FREE_ORI
)


print(
    f"\nForward source_ori code : "
    f"{source_ori}"
)


if source_ori != FREE_ORI:

    raise RuntimeError(
        "Forward solution is not free orientation."
    )


print(
    "Forward orientation = FREE: PASS"
)

print(
    f"\n{P:,} source locations"
)

print(
    f"{3 * P:,} dipole components"
)


# =============================================================================
# 18. SOURCE POSITION CONSISTENCY
#
# IMPORTANT:
#
# The original discrete source space is stored in MRI coordinates.
#
# During mne.make_forward_solution(), MNE transforms the source locations
# into HEAD coordinates. Therefore:
#
#     src0["rr"]        -> MRI coordinates
#     fwd["source_rr"]  -> HEAD coordinates
#
# They must NOT be compared directly.
#
# We independently transform the original MRI source coordinates into
# HEAD coordinates using the inverse of the frozen HEAD -> MRI transform,
# and compare those coordinates against fwd["source_rr"].
# =============================================================================

section(
    "FORWARD SOURCE POSITION CONSISTENCY"
)


# -------------------------------------------------------------------------
# Source positions stored by the forward solution
# -------------------------------------------------------------------------

forward_rr_head_m = np.asarray(
    fwd["source_rr"],
    dtype=float,
)


print(
    f"\nForward source_rr shape : "
    f"{forward_rr_head_m.shape}"
)


if forward_rr_head_m.shape != (
    P,
    3,
):

    raise RuntimeError(
        "Unexpected forward source_rr shape."
    )


if not np.isfinite(
    forward_rr_head_m
).all():

    raise RuntimeError(
        "Forward source positions contain NaN or Inf."
    )


print(
    "Forward source coordinate frame : HEAD"
)


# -------------------------------------------------------------------------
# Original source-space positions
# -------------------------------------------------------------------------

src_vertno = np.asarray(
    src0["vertno"],
    dtype=int,
)


original_rr_mri_m = np.asarray(
    src0["rr"],
    dtype=float,
)[src_vertno]


if original_rr_mri_m.shape != (
    P,
    3,
):

    raise RuntimeError(
        "Unexpected original source-position shape."
    )


print(
    "Original source coordinate frame: MRI"
)


# -------------------------------------------------------------------------
# Convert original MRI coordinates -> HEAD
#
# trans is:
#
#     HEAD -> MRI
#
# Therefore:
#
#     MRI -> HEAD = inverse(HEAD -> MRI)
# -------------------------------------------------------------------------

mri_to_head = np.linalg.inv(
    T
)


original_rr_mri_homogeneous = np.column_stack(
    [
        original_rr_mri_m,
        np.ones(
            P,
            dtype=float,
        ),
    ]
)


expected_rr_head_m = (
    mri_to_head
    @ original_rr_mri_homogeneous.T
).T[:, :3]


# -------------------------------------------------------------------------
# Compare in the SAME coordinate frame
# -------------------------------------------------------------------------

source_position_error_mm = (
    np.linalg.norm(
        forward_rr_head_m
        - expected_rr_head_m,
        axis=1,
    )
    * 1000.0
)


print(
    "\nMRI -> HEAD source-position reconstruction:"
)

print(
    f"  minimum : "
    f"{source_position_error_mm.min():.12e} mm"
)

print(
    f"  median  : "
    f"{np.median(source_position_error_mm):.12e} mm"
)

print(
    f"  mean    : "
    f"{source_position_error_mm.mean():.12e} mm"
)

print(
    f"  maximum : "
    f"{source_position_error_mm.max():.12e} mm"
)


# -------------------------------------------------------------------------
# Numerical tolerance
#
# We expect only floating-point numerical differences.
# -------------------------------------------------------------------------

SOURCE_POSITION_TOL_MM = 1e-6


if (
    source_position_error_mm.max()
    > SOURCE_POSITION_TOL_MM
):

    raise RuntimeError(
        "Forward source positions do not reproduce "
        "the expected MRI -> HEAD transformed "
        "source coordinates within tolerance."
    )


print(
    "\nForward source positions preserved "
    "after MRI -> HEAD transformation: PASS"
)


# -------------------------------------------------------------------------
# Additional round-trip check:
#
# HEAD -> MRI using the frozen transform should reproduce the original
# source-space coordinates.
# -------------------------------------------------------------------------

forward_rr_head_homogeneous = np.column_stack(
    [
        forward_rr_head_m,
        np.ones(
            P,
            dtype=float,
        ),
    ]
)


forward_rr_back_mri_m = (
    T
    @ forward_rr_head_homogeneous.T
).T[:, :3]


roundtrip_error_mm = (
    np.linalg.norm(
        forward_rr_back_mri_m
        - original_rr_mri_m,
        axis=1,
    )
    * 1000.0
)


print(
    "\nHEAD -> MRI round-trip check:"
)

print(
    f"  minimum : "
    f"{roundtrip_error_mm.min():.12e} mm"
)

print(
    f"  median  : "
    f"{np.median(roundtrip_error_mm):.12e} mm"
)

print(
    f"  mean    : "
    f"{roundtrip_error_mm.mean():.12e} mm"
)

print(
    f"  maximum : "
    f"{roundtrip_error_mm.max():.12e} mm"
)


if (
    roundtrip_error_mm.max()
    > SOURCE_POSITION_TOL_MM
):

    raise RuntimeError(
        "HEAD -> MRI source-position round-trip "
        "failed tolerance."
    )


print(
    "\nForward source-position round-trip: PASS"
)
# =============================================================================
# 19. SAVE SOURCE-NORM QC TABLE
# =============================================================================

section(
    "SAVE SOURCE-SENSITIVITY QC"
)


qc_df = pd.DataFrame(
    {
        "source_index":
            np.arange(
                P,
                dtype=int,
            ),

        "x_component_norm":
            source_component_norms[:, 0],

        "y_component_norm":
            source_component_norms[:, 1],

        "z_component_norm":
            source_component_norms[:, 2],

        "combined_source_norm":
            source_combined_norm,
    }
)


qc_df.to_csv(
    QC_CSV_PATH,
    index=False,
)


print(
    f"\nSaved:\n{QC_CSV_PATH}"
)


# =============================================================================
# 20. SAVE FORWARD SOLUTION
# =============================================================================

section(
    "SAVE FORWARD SOLUTION"
)


mne.write_forward_solution(
    FWD_PATH,
    fwd,
    overwrite=True,
    verbose=True,
)


print(
    f"\nSaved:\n{FWD_PATH}"
)


# =============================================================================
# 21. READ-BACK VALIDATION
# =============================================================================

section(
    "FORWARD FIF READ-BACK VALIDATION"
)


fwd_loaded = mne.read_forward_solution(
    FWD_PATH,
    verbose=False,
)


G_loaded = np.asarray(
    fwd_loaded["sol"]["data"],
    dtype=float,
)


print(
    f"\nRead-back gain matrix shape : "
    f"{G_loaded.shape}"
)


if G_loaded.shape != G.shape:

    raise RuntimeError(
        "Gain-matrix shape changed after FIF save/read."
    )


if not np.isfinite(
    G_loaded
).all():

    raise RuntimeError(
        "Read-back forward matrix contains "
        "NaN or Inf."
    )


readback_abs_difference = np.abs(
    G_loaded
    - G
)


print(
    "\nForward-matrix read-back difference:"
)

print(
    f"  mean absolute : "
    f"{readback_abs_difference.mean():.12e}"
)

print(
    f"  max absolute  : "
    f"{readback_abs_difference.max():.12e}"
)


# FIF serialization may introduce tiny floating-point changes.
relative_denominator = max(
    np.abs(G).max(),
    np.finfo(float).eps,
)

relative_max_difference = (
    readback_abs_difference.max()
    / relative_denominator
)


print(
    f"  relative max  : "
    f"{relative_max_difference:.12e}"
)


if relative_max_difference > 1e-5:

    raise RuntimeError(
        "Forward solution changed beyond expected "
        "numerical serialization tolerance."
    )


print(
    "\nForward FIF read-back: PASS"
)


# =============================================================================
# 22. SAVE QC SUMMARY
# =============================================================================

section(
    "SAVE QC SUMMARY"
)


summary_lines = [

    "EEG FORWARD MODEL QC",
    "=" * 70,
    "",

    f"Density: P={P:,}",
    "",

    "INPUTS",
    "-" * 70,
    f"Source space: {SRC_PATH}",
    f"BEM solution: {BEM_SOL_PATH}",
    f"HEAD -> MRI transform: {TRANS_PATH}",
    f"CapTrak geometry: {CAPTRAK_PATH}",
    "",

    "FORWARD MODEL",
    "-" * 70,
    f"EEG channels: {fwd['nchan']:,}",
    f"Source locations: {fwd['nsource']:,}",
    "Orientation: FREE",
    f"Dipole components: {3 * P:,}",
    f"Gain matrix shape: {G.shape}",
    "",

    "GAIN MATRIX",
    "-" * 70,
    f"Finite entries: {n_finite:,}/{n_total:,}",
    f"Minimum: {G.min():.12e}",
    f"Maximum: {G.max():.12e}",
    f"Mean: {G.mean():.12e}",
    f"Std: {G.std():.12e}",
    "",

    "SOURCE SENSITIVITY",
    "-" * 70,
    (
        "Component norm minimum: "
        f"{component_norms.min():.12e}"
    ),
    (
        "Component norm median: "
        f"{np.median(component_norms):.12e}"
    ),
    (
        "Component norm maximum: "
        f"{component_norms.max():.12e}"
    ),
    "",
    (
        "Combined source norm minimum: "
        f"{source_combined_norm.min():.12e}"
    ),
    (
        "Combined source norm median: "
        f"{np.median(source_combined_norm):.12e}"
    ),
    (
        "Combined source norm maximum: "
        f"{source_combined_norm.max():.12e}"
    ),
    "",
    (
        "Zero-sensitivity sources: "
        f"{len(zero_sources):,}"
    ),
    "",

    "SOURCE POSITION PRESERVATION",
    "-" * 70,
    (
        "Median error [mm]: "
        f"{np.median(source_position_error_mm):.12e}"
    ),
    (
        "Mean error [mm]: "
        f"{source_position_error_mm.mean():.12e}"
    ),
    (
        "Maximum error [mm]: "
        f"{source_position_error_mm.max():.12e}"
    ),
    "",

    "FIF READ-BACK",
    "-" * 70,
    (
        "Mean absolute matrix difference: "
        f"{readback_abs_difference.mean():.12e}"
    ),
    (
        "Maximum absolute matrix difference: "
        f"{readback_abs_difference.max():.12e}"
    ),
    (
        "Relative maximum difference: "
        f"{relative_max_difference:.12e}"
    ),
    "",

    "OUTPUTS",
    "-" * 70,
    f"Forward solution: {FWD_PATH}",
    f"Source sensitivity QC: {QC_CSV_PATH}",
    "",

    "STATUS",
    "-" * 70,
    f"G_{P}: PASS",
]


with open(
    SUMMARY_PATH,
    "w",
    encoding="utf-8",
) as f:

    f.write(
        "\n".join(
            summary_lines
        )
    )


print(
    f"\nSaved:\n{SUMMARY_PATH}"
)


# =============================================================================
# FINAL SUMMARY
# =============================================================================

section(
    "FINAL SUMMARY"
)


print(
    f"""
Forward model:

    G_{P}

EEG channels:

    128

Cortical source locations:

    {P:,}

Orientation:

    FREE

Dipole components:

    {3 * P:,}

Gain matrix:

    {G.shape[0]:,} x {G.shape[1]:,}

All matrix values finite:

    YES

Zero-sensitivity sources:

    {len(zero_sources):,}

Source-position maximum error:

    {source_position_error_mm.max():.12e} mm

Forward FIF read-back:

    PASS

Saved forward solution:

    {FWD_PATH}

Saved QC table:

    {QC_CSV_PATH}

Saved QC summary:

    {SUMMARY_PATH}

NEXT SCIENTIFIC STEP:

    Inspect G_{P} QC results.

    Do NOT calculate the inverse yet.

    After G_{P} is accepted, reproduce the same
    validated architecture for P=5000 and P=10000.
"""
)


print(
    f"G_{P}: PASS"
)

print("=" * 78)