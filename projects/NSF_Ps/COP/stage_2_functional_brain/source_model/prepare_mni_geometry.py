from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
import pyvista as pv


# ============================================================
# Project paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

HEAD_DIR = PROJECT_ROOT / "hm_icbm152"

CORTEX_INPUT = HEAD_DIR / "cortex_pial_high.obj"
CORTEX_OUTPUT = HEAD_DIR / "cortex_pial_high_mni152.obj"

SCALP_MNI = HEAD_DIR / "mask_scalp_mni152.obj"

REFERENCE_NIFTI = HEAD_DIR / "mask_skin.nii"

ELECTRODES_PATH = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "source_localization"
    / "sub-1_ses-0_captrak_registered_mni152.csv"
)


# ============================================================
# 1. Load reference affine
# ============================================================

print("\n============================================")
print("REFERENCE NIFTI")
print("============================================")

img = nib.load(REFERENCE_NIFTI)

affine = img.affine

print("Shape:")
print(img.shape)

print("\nVoxel sizes:")
print(img.header.get_zooms()[:3])

print("\nAffine:")
print(affine)


# ============================================================
# 2. Load original high-resolution cortex
# ============================================================

print("\n============================================")
print("ORIGINAL CORTEX")
print("============================================")

cortex = pv.read(CORTEX_INPUT)

print(f"Vertices : {cortex.n_points}")
print(f"Cells    : {cortex.n_cells}")
print(f"Bounds   : {cortex.bounds}")


# ============================================================
# 3. Transform cortex into MNI152 coordinates
# ============================================================

points = np.asarray(cortex.points, dtype=float)

points_h = np.column_stack(
    [points, np.ones(points.shape[0])]
)

points_mni_h = (affine @ points_h.T).T

points_mni = points_mni_h[:, :3]


# ============================================================
# 4. Create MNI cortex
# ============================================================

cortex_mni = cortex.copy(deep=True)
cortex_mni.points = points_mni

print("\n============================================")
print("MNI152 CORTEX")
print("============================================")

print(f"Vertices : {cortex_mni.n_points}")
print(f"Cells    : {cortex_mni.n_cells}")
print(f"Bounds   : {cortex_mni.bounds}")


# ============================================================
# 5. Save transformed cortex
# ============================================================

cortex_mni.save(CORTEX_OUTPUT)

print("\nSaved MNI152 cortex:")
print(CORTEX_OUTPUT)


# ============================================================
# 6. Load MNI scalp
# ============================================================

scalp = pv.read(SCALP_MNI)

print("\n============================================")
print("MNI152 SCALP")
print("============================================")

print(f"Vertices : {scalp.n_points}")
print(f"Cells    : {scalp.n_cells}")
print(f"Bounds   : {scalp.bounds}")


# ============================================================
# 7. Load registered electrodes
# ============================================================

electrodes = pd.read_csv(ELECTRODES_PATH)

electrode_xyz = electrodes[
    ["x_mni_mm", "y_mni_mm", "z_mni_mm"]
].to_numpy(dtype=float)

print("\n============================================")
print("REGISTERED ELECTRODES")
print("============================================")

print(f"Electrodes : {len(electrode_xyz)}")

print(
    "Bounds [mm]:\n"
    f"x = {electrode_xyz[:, 0].min():.3f} "
    f"to {electrode_xyz[:, 0].max():.3f}\n"
    f"y = {electrode_xyz[:, 1].min():.3f} "
    f"to {electrode_xyz[:, 1].max():.3f}\n"
    f"z = {electrode_xyz[:, 2].min():.3f} "
    f"to {electrode_xyz[:, 2].max():.3f}"
)

electrode_cloud = pv.PolyData(electrode_xyz)


# ============================================================
# 8. Visual validation
# ============================================================

plotter = pv.Plotter(
    window_size=(1200, 900)
)

# Scalp
plotter.add_mesh(
    scalp,
    opacity=0.20,
    smooth_shading=True,
    show_edges=False,
    label="ICBM152 scalp",
)

# Cortex
plotter.add_mesh(
    cortex_mni,
    opacity=0.85,
    smooth_shading=True,
    show_edges=False,
    label="ICBM152 pial cortex",
)

# Registered electrodes
plotter.add_mesh(
    electrode_cloud,
    render_points_as_spheres=True,
    point_size=10,
    label="Registered CapTrak electrodes",
)

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