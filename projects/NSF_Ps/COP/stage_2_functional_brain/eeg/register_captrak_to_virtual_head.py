from pathlib import Path
import json

import numpy as np
import pandas as pd
import pyvista as pv


# ============================================================
# Paths
# ============================================================

SCALP_PATH = Path("hm_icbm152/mask_scalp.obj")

LANDMARKS_PATH = Path("hm_icbm152/landmarks.mrk.json")

CAPTRAK_PATH = Path(
    "stage_2_functional_brain/eeg/source_localization/"
    "sub-1_ses-0_captrak_sensor_geometry.csv"
)

OUTPUT_PATH = Path(
    "stage_2_functional_brain/eeg/source_localization/"
    "sub-1_ses-0_captrak_registered_mni152.csv"
)


# ============================================================
# 1. Load subject CapTrak electrodes
# ============================================================

captrak = pd.read_csv(CAPTRAK_PATH)

required = {"channel", "x", "y", "z"}

if not required.issubset(captrak.columns):
    raise ValueError(
        f"CapTrak file must contain columns: {required}"
    )

# CapTrak is stored in meters -> convert to millimeters
captrak_xyz_mm = (
    captrak[["x", "y", "z"]].to_numpy(dtype=float) * 1000.0
)

captrak_names = captrak["channel"].astype(str).tolist()

print("\n============================================")
print("CAPTRAK")
print("============================================")
print(f"Electrodes: {len(captrak_names)}")


# ============================================================
# 2. Load MNI152 landmarks
# ============================================================

with open(LANDMARKS_PATH, "r", encoding="utf-8") as f:
    landmark_json = json.load(f)

markups = landmark_json["markups"]

if len(markups) == 0:
    raise RuntimeError("No markups found in landmark file.")

markup = markups[0]

print("\nMNI landmark coordinate system:")
print(markup.get("coordinateSystem"))

print("MNI landmark units:")
print(markup.get("coordinateUnits"))

control_points = markup["controlPoints"]

mni_landmarks = {}

for cp in control_points:

    label = str(cp["label"]).strip()

    position = np.asarray(
        cp["position"],
        dtype=float
    )

    mni_landmarks[label] = position


print(f"MNI landmarks loaded: {len(mni_landmarks)}")


# ============================================================
# 3. Find common EEG labels
#
# We intentionally exclude anatomical fiducials here.
# Registration is based on standard EEG positions that exist
# in both the subject CapTrak data and the MNI landmark file.
# ============================================================

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
    for name in captrak_names
    if name in mni_landmarks
    and name not in excluded_labels
]

print("\n============================================")
print("COMMON REGISTRATION LANDMARKS")
print("============================================")

print(f"Common EEG landmarks: {len(common_names)}")
print(common_names)

if len(common_names) < 3:
    raise RuntimeError(
        "Fewer than 3 common EEG landmarks were found."
    )


# ============================================================
# 4. Construct corresponding point matrices
# ============================================================

captrak_lookup = {
    name: captrak_xyz_mm[i]
    for i, name in enumerate(captrak_names)
}

subject_points = np.vstack(
    [captrak_lookup[name] for name in common_names]
)

template_points = np.vstack(
    [mni_landmarks[name] for name in common_names]
)


# ============================================================
# 5. Rigid registration using Kabsch algorithm
#
# Find:
#
#     template ≈ R @ subject + t
#
# No scaling or deformation is performed.
# ============================================================

subject_centroid = subject_points.mean(axis=0)
template_centroid = template_points.mean(axis=0)

X = subject_points - subject_centroid
Y = template_points - template_centroid

H = X.T @ Y

U, S, Vt = np.linalg.svd(H)

R = Vt.T @ U.T

# Prevent reflection
if np.linalg.det(R) < 0:
    Vt[-1, :] *= -1
    R = Vt.T @ U.T

t = template_centroid - R @ subject_centroid


print("\n============================================")
print("RIGID TRANSFORMATION")
print("============================================")

print("\nRotation matrix R:")
print(R)

print("\nTranslation vector t [mm]:")
print(t)

print(f"\ndet(R): {np.linalg.det(R):.6f}")


# ============================================================
# 6. Transform common registration landmarks
# ============================================================

subject_registered = (
    (R @ subject_points.T).T + t
)

errors = np.linalg.norm(
    subject_registered - template_points,
    axis=1
)

print("\n============================================")
print("REGISTRATION ERROR")
print("============================================")

for name, error in zip(common_names, errors):
    print(f"{name:>6s} : {error:7.3f} mm")

print("\nSummary:")
print(f"Mean error   : {errors.mean():.3f} mm")
print(f"Median error : {np.median(errors):.3f} mm")
print(f"Max error    : {errors.max():.3f} mm")
print(f"RMS error    : {np.sqrt(np.mean(errors**2)):.3f} mm")


# ============================================================
# 7. Transform ALL 128 subject electrodes
# ============================================================

registered_xyz = (
    (R @ captrak_xyz_mm.T).T + t
)

registered = captrak.copy()

registered["x_mni_mm"] = registered_xyz[:, 0]
registered["y_mni_mm"] = registered_xyz[:, 1]
registered["z_mni_mm"] = registered_xyz[:, 2]

registered.to_csv(
    OUTPUT_PATH,
    index=False
)

print("\nRegistered electrode coordinates saved to:")
print(OUTPUT_PATH.resolve())


# ============================================================
# 8. Load virtual scalp
# ============================================================

scalp = pv.read(SCALP_PATH)

print("\n============================================")
print("VIRTUAL SCALP")
print("============================================")

print(f"Vertices : {scalp.n_points}")
print(f"Cells    : {scalp.n_cells}")
print(f"Bounds   : {scalp.bounds}")


# ============================================================
# 9. PyVista objects
# ============================================================

registered_cloud = pv.PolyData(registered_xyz)

template_common_cloud = pv.PolyData(template_points)


# ============================================================
# 10. Visualization
# ============================================================

plotter = pv.Plotter()

# ICBM152 scalp
plotter.add_mesh(
    scalp,
    opacity=0.25,
    show_edges=False,
    label="ICBM152 scalp",
)

# Registered subject electrodes
plotter.add_mesh(
    registered_cloud,
    render_points_as_spheres=True,
    point_size=11,
    label="Registered subject CapTrak",
)

# MNI template landmarks used for registration
plotter.add_mesh(
    template_common_cloud,
    render_points_as_spheres=True,
    point_size=7,
    label="MNI EEG landmarks",
)


# ============================================================
# 11. Label selected electrodes
# ============================================================

important_channels = [
    "Fp1",
    "Fp2",
    "F3",
    "F4",
    "C3",
    "C4",
    "Cz",
    "P3",
    "P4",
    "Pz",
    "O1",
    "O2",
]

for channel in important_channels:

    if channel not in captrak_names:
        continue

    idx = captrak_names.index(channel)

    plotter.add_point_labels(
        registered_xyz[[idx]],
        [channel],
        point_size=7,
        font_size=11,
        shape=None,
        always_visible=True,
    )


# ============================================================
# 12. Display
# ============================================================

plotter.add_axes()
plotter.add_legend()
plotter.show_grid()

plotter.camera_position = "iso"

plotter.show()