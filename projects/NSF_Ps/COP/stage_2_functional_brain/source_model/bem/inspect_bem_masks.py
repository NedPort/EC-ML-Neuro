from pathlib import Path

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
ANAT = ROOT / "hm_icbm152"

FILES = {
    "skin": ANAT / "mask_skin.nii",
    "bone": ANAT / "mask_bone.nii",
    "csf": ANAT / "mask_csf.nii",
    "gray": ANAT / "mask_gray.nii",
    "white": ANAT / "mask_white.nii",
}


# ---------------------------------------------------------
# Load masks
# ---------------------------------------------------------

masks = {}

for name, path in FILES.items():
    img = nib.load(path)
    data = np.asarray(img.dataobj) > 0
    masks[name] = data

    print(
        f"{name:>5}: "
        f"shape={data.shape}, "
        f"voxels={data.sum():,}"
    )


# ---------------------------------------------------------
# Confirm all masks have identical dimensions
# ---------------------------------------------------------

shapes = {x.shape for x in masks.values()}

if len(shapes) != 1:
    raise RuntimeError(
        f"Masks do not have identical dimensions: {shapes}"
    )

shape = next(iter(shapes))

print("\nCommon shape:", shape)


# ---------------------------------------------------------
# Choose central slices
# ---------------------------------------------------------

cx = shape[0] // 2
cy = shape[1] // 2
cz = shape[2] // 2

print(f"\nCentral voxel: x={cx}, y={cy}, z={cz}")


# ---------------------------------------------------------
# Create labeled volume for visualization
#
# 0 background
# 1 skin
# 2 bone
# 3 CSF
# 4 gray
# 5 white
# ---------------------------------------------------------

labels = np.zeros(shape, dtype=np.uint8)

labels[masks["skin"]] = 1
labels[masks["bone"]] = 2
labels[masks["csf"]] = 3
labels[masks["gray"]] = 4
labels[masks["white"]] = 5


# ---------------------------------------------------------
# Plot three orthogonal views
# ---------------------------------------------------------

fig, axes = plt.subplots(1, 3, figsize=(16, 6))

axes[0].imshow(
    np.rot90(labels[cx, :, :]),
    interpolation="nearest",
)
axes[0].set_title("Sagittal")
axes[0].axis("off")


axes[1].imshow(
    np.rot90(labels[:, cy, :]),
    interpolation="nearest",
)
axes[1].set_title("Coronal")
axes[1].axis("off")


axes[2].imshow(
    np.rot90(labels[:, :, cz]),
    interpolation="nearest",
)
axes[2].set_title("Axial")
axes[2].axis("off")


fig.suptitle(
    "ICBM152 tissue masks\n"
    "1=skin | 2=bone | 3=CSF | 4=gray | 5=white"
)

plt.tight_layout()
plt.show()