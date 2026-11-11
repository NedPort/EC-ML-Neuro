from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
import pyvista as pv


# ============================================================
# Paths
# ============================================================

SCALP_OBJ = Path("hm_icbm152/mask_scalp.obj")

# NIfTI corresponding to the skin/scalp geometry
SCALP_NIFTI = Path("hm_icbm152/mask_skin.nii")

OUTPUT_SCALP = Path("hm_icbm152/mask_scalp_mni152.obj")

REGISTERED_ELECTRODES = Path(
    "stage_2_functional_brain/eeg/source_localization/"
    "sub-1_ses-0_captrak_registered_mni152.csv"
)


# ============================================================
# 1. Load original scalp OBJ
# ============================================================

print("\n============================================")
print("ORIGINAL SCALP")
print("============================================")

scalp = pv.read(SCALP_OBJ)

print(f"Vertices : {scalp.n_points}")
print(f"Cells    : {scalp.n_cells}")
print(f"Bounds   : {scalp.bounds}")


# ============================================================
# 2. Load NIfTI affine
# ============================================================

img = nib.load(SCALP_NIFTI)

affine = img.affine

print("\n============================================")
print("NIFTI GEOMETRY")
print("============================================")

print(f"Shape       : {img.shape}")
print(f"Voxel sizes : {img.header.get_zooms()[:3]}")

print("\nAffine:")
print(affine)


# ============================================================
# 3. Transform scalp vertices:
#
# voxel/OBJ coordinates -> MNI152 world coordinates
#
# [x_mni]       [x_obj]
# [y_mni] = A * [y_obj]
# [z_mni]       [z_obj]
# [  1  ]       [  1  ]
# ============================================================

points_obj = np.asarray(scalp.points, dtype=float)

ones = np.ones((points_obj.shape[0], 1))

points_homogeneous = np.hstack(
    [points_obj, ones]
)

points_mni_homogeneous = (
    affine @ points_homogeneous.T
).T

points_mni = points_mni_homogeneous[:, :3]


# ============================================================
# 4. Create transformed scalp mesh
# ============================================================

scalp_mni = scalp.copy(deep=True)

scalp_mni.points = points_mni


print("\n============================================")
print("MNI152 SCALP")
print("============================================")

print(f"Vertices : {scalp_mni.n_points}")
print(f"Cells    : {scalp_mni.n_cells}")
print(f"Bounds   : {scalp_mni.bounds}")


# ============================================================
# 5. Save transformed mesh
# ============================================================

scalp_mni.save(OUTPUT_SCALP)

print("\nSaved transformed scalp:")
print(OUTPUT_SCALP.resolve())


# ============================================================
# 6. Load registered CapTrak electrodes
# ============================================================

electrodes = pd.read_csv(REGISTERED_ELECTRODES)

required_columns = {
    "channel",
    "x_mni_mm",
    "y_mni_mm",
    "z_mni_mm",
}

if not required_columns.issubset(electrodes.columns):
    raise RuntimeError(
        "Registered electrode CSV does not contain the expected "
        "MNI coordinate columns."
    )

electrode_xyz = electrodes[
    ["x_mni_mm", "y_mni_mm", "z_mni_mm"]
].to_numpy(dtype=float)

electrode_names = electrodes["channel"].astype(str).tolist()

electrode_cloud = pv.PolyData(electrode_xyz)


# ============================================================
# 7. Print electrode bounds
# ============================================================

print("\n============================================")
print("REGISTERED ELECTRODES")
print("============================================")

print(f"Electrodes: {len(electrode_xyz)}")

print(
    f"x: {electrode_xyz[:, 0].min():.3f} "
    f"to {electrode_xyz[:, 0].max():.3f}"
)

print(
    f"y: {electrode_xyz[:, 1].min():.3f} "
    f"to {electrode_xyz[:, 1].max():.3f}"
)

print(
    f"z: {electrode_xyz[:, 2].min():.3f} "
    f"to {electrode_xyz[:, 2].max():.3f}"
)


# ============================================================
# 8. Visualize MNI scalp + registered electrodes
# ============================================================

plotter = pv.Plotter(
    window_size=(1100, 850)
)

plotter.add_mesh(
    scalp_mni,
    opacity=0.30,
    smooth_shading=True,
    show_edges=False,
    label="ICBM152 scalp - MNI152",
)

plotter.add_mesh(
    electrode_cloud,
    render_points_as_spheres=True,
    point_size=12,
    label="Registered subject CapTrak",
)


# ============================================================
# 9. Label selected electrodes
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
    "Oz",
]

for channel in important_channels:

    if channel not in electrode_names:
        continue

    idx = electrode_names.index(channel)

    plotter.add_point_labels(
        electrode_xyz[[idx]],
        [channel],
        point_size=7,
        font_size=11,
        shape=None,
        always_visible=True,
    )


# ============================================================
# 10. Display
# ============================================================

plotter.add_axes(
    xlabel="X: Left / Right",
    ylabel="Y: Posterior / Anterior",
    zlabel="Z: Inferior / Superior",
)

plotter.show_grid(
    xlabel="X MNI (mm)",
    ylabel="Y MNI (mm)",
    zlabel="Z MNI (mm)",
)

plotter.add_legend()

plotter.camera_position = "iso"

plotter.show()