from pathlib import Path

import nibabel as nib
import numpy as np
import pyvista as pv


# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

HEAD_DIR = PROJECT_ROOT / "hm_icbm152"

OUTPUT_DIR = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "fem"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_NIFTI = OUTPUT_DIR / "icbm152_fem_tissues.nii.gz"


# ============================================================
# Tissue definitions
# ============================================================

# Integer labels used in the FEM anatomical volume
TISSUES = {
    "skin": {
        "file": HEAD_DIR / "mask_skin.nii",
        "label": 1,
    },
    "bone": {
        "file": HEAD_DIR / "mask_bone.nii",
        "label": 2,
    },
    "csf": {
        "file": HEAD_DIR / "mask_csf.nii",
        "label": 3,
    },
    "gray": {
        "file": HEAD_DIR / "mask_gray.nii",
        "label": 4,
    },
    "white": {
        "file": HEAD_DIR / "mask_white.nii",
        "label": 5,
    },
}


# ============================================================
# 1. Load all masks
# ============================================================

print("\n============================================")
print("LOADING FEM TISSUE MASKS")
print("============================================")

masks = {}
reference_img = None
reference_shape = None
reference_affine = None

for tissue_name, info in TISSUES.items():

    img = nib.load(info["file"])
    data = img.get_fdata()

    mask = data > 0.5

    if reference_img is None:
        reference_img = img
        reference_shape = img.shape
        reference_affine = img.affine.copy()

    else:
        if img.shape != reference_shape:
            raise RuntimeError(
                f"Shape mismatch for {tissue_name}: "
                f"{img.shape} != {reference_shape}"
            )

        if not np.allclose(img.affine, reference_affine):
            raise RuntimeError(
                f"Affine mismatch for tissue: {tissue_name}"
            )

    masks[tissue_name] = mask

    print(
        f"{tissue_name:>5}: "
        f"label={info['label']} | "
        f"voxels={np.count_nonzero(mask):,}"
    )


# ============================================================
# 2. Verify masks are mutually exclusive
# ============================================================

print("\n============================================")
print("CHECKING TISSUE OVERLAP")
print("============================================")

membership_count = np.zeros(
    reference_shape,
    dtype=np.uint8,
)

for mask in masks.values():
    membership_count += mask.astype(np.uint8)

overlap_voxels = np.count_nonzero(membership_count > 1)

print(f"Overlapping voxels: {overlap_voxels:,}")
print(f"Maximum tissues per voxel: {membership_count.max()}")

if overlap_voxels != 0:
    raise RuntimeError(
        "Tissue masks overlap. "
        "Cannot construct an unambiguous FEM label volume."
    )


# ============================================================
# 3. Construct labeled tissue volume
# ============================================================

print("\n============================================")
print("BUILDING LABELED FEM VOLUME")
print("============================================")

labels = np.zeros(
    reference_shape,
    dtype=np.uint8,
)

for tissue_name, info in TISSUES.items():

    labels[masks[tissue_name]] = info["label"]

    print(
        f"{info['label']} = {tissue_name}"
    )


# ============================================================
# 4. Validate resulting labels
# ============================================================

unique_labels, counts = np.unique(
    labels,
    return_counts=True,
)

print("\nFinal volume labels:")

for label, count in zip(unique_labels, counts):

    if label == 0:
        name = "background"
    else:
        name = next(
            tissue_name
            for tissue_name, info in TISSUES.items()
            if info["label"] == label
        )

    print(
        f"  {label}: {name:<10} "
        f"{count:,} voxels"
    )


# ============================================================
# 5. Save NIfTI
# ============================================================

output_img = nib.Nifti1Image(
    labels,
    affine=reference_affine,
    header=reference_img.header.copy(),
)

# Explicitly store labels as unsigned 8-bit integers
output_img.set_data_dtype(np.uint8)

nib.save(
    output_img,
    OUTPUT_NIFTI,
)

print("\n============================================")
print("SAVED FEM TISSUE VOLUME")
print("============================================")

print(OUTPUT_NIFTI)


# ============================================================
# 6. Reload saved file for verification
# ============================================================

check_img = nib.load(OUTPUT_NIFTI)
check_data = np.asarray(check_img.dataobj)

print("\nReloaded shape:")
print(check_img.shape)

print("\nReloaded affine:")
print(check_img.affine)

print("\nReloaded datatype:")
print(check_data.dtype)

print("\nReloaded unique labels:")
print(np.unique(check_data))


# ============================================================
# 7. 3D anatomical validation
# ============================================================

print("\n============================================")
print("CREATING 3D VALIDATION VIEW")
print("============================================")

plotter = pv.Plotter(
    window_size=(1200, 900)
)

# Different opacities allow us to inspect nesting.
opacity_map = {
    "skin": 0.10,
    "bone": 0.15,
    "csf": 0.20,
    "gray": 0.45,
    "white": 0.85,
}

for tissue_name, info in TISSUES.items():

    mask = labels == info["label"]

    # Convert binary tissue mask into a PyVista volume.
    grid = pv.ImageData()

    grid.dimensions = np.array(reference_shape) + 1
    grid.spacing = (
        float(reference_img.header.get_zooms()[0]),
        float(reference_img.header.get_zooms()[1]),
        float(reference_img.header.get_zooms()[2]),
    )

    # The NIfTI affine is axis-aligned for this dataset.
    grid.origin = (
        reference_affine[0, 3],
        reference_affine[1, 3],
        reference_affine[2, 3],
    )

    grid.cell_data["mask"] = mask.flatten(order="F").astype(
        np.uint8
    )

    surface = grid.threshold(
        value=0.5,
        scalars="mask",
    ).extract_surface()

    plotter.add_mesh(
        surface,
        opacity=opacity_map[tissue_name],
        smooth_shading=True,
        show_edges=False,
        label=tissue_name,
    )


plotter.add_axes(
    xlabel="X",
    ylabel="Y",
    zlabel="Z",
)

plotter.show_grid(
    xlabel="X MNI (mm)",
    ylabel="Y MNI (mm)",
    zlabel="Z MNI (mm)",
)

plotter.add_legend()

plotter.camera_position = "iso"

plotter.show()