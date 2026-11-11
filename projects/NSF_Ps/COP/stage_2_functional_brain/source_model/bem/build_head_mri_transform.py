from pathlib import Path
import json

import mne
import numpy as np
import pandas as pd


# ============================================================
# Paths
# ============================================================

BEM_ROOT = Path(__file__).resolve().parent
COP_ROOT = BEM_ROOT.parents[2]

LANDMARKS_PATH = (
    COP_ROOT
    / "hm_icbm152"
    / "landmarks.mrk.json"
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

OUTPUT_TRANS = (
    BEM_ROOT
    / "sub-1_ses-0-head-mri-trans.fif"
)


# ============================================================
# Numerical tolerances
# ============================================================

# The reconstructed transform should reproduce the saved
# registered electrode coordinates essentially exactly.
RECONSTRUCTION_TOL_MM = 1e-8

# MNE/FIF serialization can introduce tiny numerical changes
# when the transform is written and read back.
#
# A tolerance of 1e-7 in the 4x4 transform matrix is far below
# any spatial scale relevant to EEG forward modeling.
READBACK_TOL = 1e-7


# ============================================================
# Header
# ============================================================

print("=" * 78)
print("BUILD HEAD -> MRI TRANSFORM")
print("=" * 78)


# ============================================================
# 1. File checks
# ============================================================

required_files = [
    LANDMARKS_PATH,
    CAPTRAK_PATH,
    REGISTERED_PATH,
]

for path in required_files:

    if not path.exists():
        raise FileNotFoundError(
            f"Missing required file:\n{path}"
        )

    print(f"PASS  {path.name}")


# ============================================================
# 2. Load original CapTrak geometry
# ============================================================

captrak = pd.read_csv(CAPTRAK_PATH)

required_captrak_columns = {
    "channel",
    "x",
    "y",
    "z",
}

if not required_captrak_columns.issubset(
    captrak.columns
):
    raise RuntimeError(
        "CapTrak file does not contain all required "
        "columns:\n"
        f"{sorted(required_captrak_columns)}"
    )

channel_names = (
    captrak["channel"]
    .astype(str)
    .tolist()
)

head_xyz_m = (
    captrak[
        ["x", "y", "z"]
    ]
    .to_numpy(dtype=float)
)

if not np.isfinite(head_xyz_m).all():
    raise RuntimeError(
        "Non-finite CapTrak coordinates detected."
    )

print("\nOriginal CapTrak:")
print(
    f"  electrodes : "
    f"{len(head_xyz_m):,}"
)
print("  units      : meters")
print("  frame      : head / CapTrak")


# ============================================================
# 3. Load MNI152 landmark file
# ============================================================

with open(
    LANDMARKS_PATH,
    "r",
    encoding="utf-8",
) as f:
    landmark_json = json.load(f)

markups = landmark_json.get(
    "markups",
    [],
)

if len(markups) == 0:
    raise RuntimeError(
        "No markups found in MNI landmark file."
    )

markup = markups[0]

coordinate_system = markup.get(
    "coordinateSystem"
)

coordinate_units = markup.get(
    "coordinateUnits"
)

print("\nMNI landmark file:")
print(
    f"  coordinate system : "
    f"{coordinate_system}"
)
print(
    f"  coordinate units  : "
    f"{coordinate_units}"
)

control_points = markup.get(
    "controlPoints",
    [],
)

if len(control_points) == 0:
    raise RuntimeError(
        "No control points found in landmark file."
    )

mni_landmarks_mm = {}

for cp in control_points:

    label = str(
        cp["label"]
    ).strip()

    position = np.asarray(
        cp["position"],
        dtype=float,
    )

    if position.shape != (3,):
        raise RuntimeError(
            f"Invalid landmark coordinate shape "
            f"for {label}: {position.shape}"
        )

    mni_landmarks_mm[label] = position


# ============================================================
# 4. Reproduce original common-landmark selection
# ============================================================

# These labels were explicitly excluded in the original
# registration script.
excluded_labels = {
    "Nz",
    "NAS",
    "Nasion",
    "Iz",
    "LPA",
    "RPA",
}

common_names = [
    name
    for name in channel_names
    if (
        name in mni_landmarks_mm
        and name not in excluded_labels
    )
]

print("\nRegistration landmarks:")
print(
    f"  common EEG landmarks : "
    f"{len(common_names):,}"
)

if len(common_names) < 3:
    raise RuntimeError(
        "Fewer than three common EEG landmarks "
        "were found."
    )


# ============================================================
# 5. Construct corresponding point matrices
# ============================================================

head_lookup_m = {
    name: head_xyz_m[i]
    for i, name in enumerate(channel_names)
}

# The original registration script converted the subject
# CapTrak coordinates from meters to millimeters before
# performing Kabsch registration.
subject_points_mm = np.vstack(
    [
        head_lookup_m[name] * 1000.0
        for name in common_names
    ]
)

template_points_mm = np.vstack(
    [
        mni_landmarks_mm[name]
        for name in common_names
    ]
)


# ============================================================
# 6. Reproduce original rigid Kabsch registration
#
# Find:
#
#     template ~= R @ subject + t
#
# No scaling.
# No deformation.
# Reflection is explicitly prevented.
# ============================================================

subject_centroid = (
    subject_points_mm.mean(axis=0)
)

template_centroid = (
    template_points_mm.mean(axis=0)
)

X = (
    subject_points_mm
    - subject_centroid
)

Y = (
    template_points_mm
    - template_centroid
)

H = X.T @ Y

U, singular_values, Vt = np.linalg.svd(H)

R = Vt.T @ U.T

# Prevent reflection exactly as done in the original
# registration script.
if np.linalg.det(R) < 0:

    Vt[-1, :] *= -1

    R = Vt.T @ U.T

t_mm = (
    template_centroid
    - R @ subject_centroid
)


# ============================================================
# 7. Validate rotation matrix
# ============================================================

det_R = np.linalg.det(R)

orthogonality_error = np.linalg.norm(
    R.T @ R
    - np.eye(3)
)

print("\n" + "=" * 78)
print("RECONSTRUCTED RIGID TRANSFORMATION")
print("=" * 78)

print("\nRotation matrix R:")
print(R)

print("\nTranslation t [mm]:")
print(t_mm)

print(
    f"\ndet(R) = "
    f"{det_R:.12f}"
)

print(
    f"Orthogonality error "
    f"||R^T R - I|| = "
    f"{orthogonality_error:.3e}"
)

if not np.isclose(
    det_R,
    1.0,
    atol=1e-10,
):
    raise RuntimeError(
        "Rotation matrix determinant is not +1."
    )

if orthogonality_error > 1e-10:
    raise RuntimeError(
        "Rotation matrix is not sufficiently orthogonal."
    )

print("\nRigid rotation validation: PASS")


# ============================================================
# 8. Registration error against the 63 MNI landmarks
#
# This is the anatomical/template registration error.
# It is DIFFERENT from the later 128-electrode reconstruction
# error.
# ============================================================

registered_common_mm = (
    (R @ subject_points_mm.T).T
    + t_mm
)

registration_errors_mm = np.linalg.norm(
    registered_common_mm
    - template_points_mm,
    axis=1,
)

print("\n" + "=" * 78)
print("63-LANDMARK REGISTRATION ERROR")
print("=" * 78)

print(
    f"\nMinimum error : "
    f"{registration_errors_mm.min():.3f} mm"
)

print(
    f"Median error  : "
    f"{np.median(registration_errors_mm):.3f} mm"
)

print(
    f"Mean error    : "
    f"{registration_errors_mm.mean():.3f} mm"
)

print(
    f"Maximum error : "
    f"{registration_errors_mm.max():.3f} mm"
)

print(
    f"RMS error     : "
    f"{np.sqrt(np.mean(registration_errors_mm**2)):.3f} mm"
)


# ============================================================
# 9. Convert transformation to MNE units
#
# MNE uses meters internally.
#
# Rotation is dimensionless.
# Translation therefore changes:
#
#     mm -> m
# ============================================================

t_m = (
    t_mm
    / 1000.0
)

trans_matrix = np.eye(
    4,
    dtype=float,
)

trans_matrix[:3, :3] = R
trans_matrix[:3, 3] = t_m


# ============================================================
# 10. Create MNE HEAD -> MRI transform
# ============================================================

head_mri_trans = mne.transforms.Transform(
    fro="head",
    to="mri",
    trans=trans_matrix,
)

print("\n" + "=" * 78)
print("MNE HEAD -> MRI TRANSFORM")
print("=" * 78)

print("\nTransform:")
print(head_mri_trans)

print("\n4x4 transform matrix:")
print(trans_matrix)

print("\nInterpretation:")
print(
    "  input  : CapTrak HEAD coordinates [m]"
)
print(
    "  output : ICBM152/MNI152 MRI coordinates [m]"
)


# ============================================================
# 11. Load previously saved registered coordinates
# ============================================================

registered = pd.read_csv(
    REGISTERED_PATH
)

registered_required = {
    "channel",
    "x_mni_mm",
    "y_mni_mm",
    "z_mni_mm",
}

if not registered_required.issubset(
    registered.columns
):
    raise RuntimeError(
        "Registered coordinate file does not contain "
        "all required columns."
    )

registered_names = (
    registered["channel"]
    .astype(str)
    .tolist()
)

if registered_names != channel_names:
    raise RuntimeError(
        "Channel ordering differs between original "
        "CapTrak and registered coordinate files."
    )

saved_mni_m = (
    registered[
        [
            "x_mni_mm",
            "y_mni_mm",
            "z_mni_mm",
        ]
    ]
    .to_numpy(dtype=float)
    / 1000.0
)

if not np.isfinite(
    saved_mni_m
).all():
    raise RuntimeError(
        "Non-finite registered MNI coordinates detected."
    )


# ============================================================
# 12. Apply reconstructed HEAD -> MRI transform to all
#     128 electrodes
# ============================================================

homogeneous_head = np.column_stack(
    [
        head_xyz_m,
        np.ones(
            len(head_xyz_m),
            dtype=float,
        ),
    ]
)

reconstructed_mni_m = (
    trans_matrix
    @ homogeneous_head.T
).T[:, :3]


# ============================================================
# 13. Compare reconstructed positions with the previously
#     saved registered MNI positions
#
# This tests whether we reproduced the ORIGINAL transform.
# It does NOT measure anatomical registration quality.
# ============================================================

errors_m = np.linalg.norm(
    reconstructed_mni_m
    - saved_mni_m,
    axis=1,
)

errors_mm = (
    errors_m
    * 1000.0
)

print("\n" + "=" * 78)
print("128-ELECTRODE RECONSTRUCTION VALIDATION")
print("=" * 78)

print(
    f"\nElectrodes tested : "
    f"{len(errors_mm):,}"
)

print(
    f"Minimum error     : "
    f"{errors_mm.min():.12e} mm"
)

print(
    f"Median error      : "
    f"{np.median(errors_mm):.12e} mm"
)

print(
    f"Mean error        : "
    f"{errors_mm.mean():.12e} mm"
)

print(
    f"Maximum error     : "
    f"{errors_mm.max():.12e} mm"
)

print(
    f"RMS error         : "
    f"{np.sqrt(np.mean(errors_mm**2)):.12e} mm"
)


# ============================================================
# 14. Show worst reconstruction matches
# ============================================================

worst = np.argsort(
    errors_mm
)[-10:][::-1]

print("\nWorst 10 reconstruction errors:")

for idx in worst:

    print(
        f"  {channel_names[idx]:>7s} : "
        f"{errors_mm[idx]:.12e} mm"
    )


# ============================================================
# 15. Strict reconstruction validation
# ============================================================

print(
    f"\nReconstruction tolerance : "
    f"{RECONSTRUCTION_TOL_MM:.1e} mm"
)

if (
    errors_mm.max()
    > RECONSTRUCTION_TOL_MM
):
    raise RuntimeError(
        "\nReconstructed transform does not reproduce "
        "the previously saved registered electrode "
        "coordinates within tolerance.\n"
        f"Maximum error = "
        f"{errors_mm.max():.12e} mm"
    )

print(
    "\nSaved registered electrode coordinates "
    "reproduced: PASS"
)


# ============================================================
# 16. Save MNE transform
# ============================================================

print("\n" + "=" * 78)
print("SAVE TRANSFORM")
print("=" * 78)

mne.write_trans(
    OUTPUT_TRANS,
    head_mri_trans,
    overwrite=True,
)

print(
    f"\nSaved:\n{OUTPUT_TRANS}"
)


# ============================================================
# 17. Read transform back from FIF
# ============================================================

loaded_trans = mne.read_trans(
    OUTPUT_TRANS
)

if (
    loaded_trans["from"]
    != head_mri_trans["from"]
):
    raise RuntimeError(
        "Read-back transform has incorrect "
        "source coordinate frame."
    )

if (
    loaded_trans["to"]
    != head_mri_trans["to"]
):
    raise RuntimeError(
        "Read-back transform has incorrect "
        "destination coordinate frame."
    )

matrix_difference = np.max(
    np.abs(
        loaded_trans["trans"]
        - trans_matrix
    )
)

print("\n" + "=" * 78)
print("SAVE / READ-BACK VALIDATION")
print("=" * 78)

print(
    f"\nMaximum matrix difference after read-back: "
    f"{matrix_difference:.12e}"
)

print(
    f"Read-back tolerance: "
    f"{READBACK_TOL:.1e}"
)

if matrix_difference > READBACK_TOL:
    raise RuntimeError(
        "Saved/read-back transform differs from "
        "the original matrix beyond the accepted "
        "numerical serialization tolerance."
    )

print("\nTransform read-back: PASS")


# ============================================================
# 18. Optional geometric interpretation of read-back error
#
# Report the maximum matrix difference in a convenient scale.
# For translation-like differences, multiplying meters by
# 1000 gives millimeters. This is only an intuitive numerical
# scale; matrix elements include both rotation and translation.
# ============================================================

print(
    "\nRead-back numerical scale:"
)

print(
    f"  maximum matrix difference = "
    f"{matrix_difference:.3e}"
)

print(
    f"  translation-equivalent scale = "
    f"{matrix_difference * 1000.0:.6e} mm"
)


# ============================================================
# 19. Final summary
# ============================================================

print("\n" + "=" * 78)
print("FINAL SUMMARY")
print("=" * 78)

print(
    f"""
Coordinate architecture:

    Original CapTrak electrodes
        coordinate frame : HEAD
        units            : meters
        electrodes       : {len(head_xyz_m)}

                    |
                    | rigid Kabsch transform
                    | no scaling
                    | no deformation
                    v

    ICBM152 / MNI152 anatomy
        coordinate frame : MRI
        MNE units        : meters

Transform:

    HEAD -> MRI

Registration landmarks:

    {len(common_names)} EEG positions

63-landmark registration error:

    mean   = {registration_errors_mm.mean():.3f} mm
    median = {np.median(registration_errors_mm):.3f} mm
    RMS    = {np.sqrt(np.mean(registration_errors_mm**2)):.3f} mm
    max    = {registration_errors_mm.max():.3f} mm

128-electrode transform reconstruction:

    mean   = {errors_mm.mean():.12e} mm
    max    = {errors_mm.max():.12e} mm

FIF read-back:

    maximum matrix difference
        = {matrix_difference:.12e}

Output:

    {OUTPUT_TRANS}
"""
)

print("HEAD -> MRI TRANSFORM: PASS")
print("=" * 78)