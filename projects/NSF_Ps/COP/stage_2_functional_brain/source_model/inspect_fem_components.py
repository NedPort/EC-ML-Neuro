from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage


# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEM_VOLUME = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "fem"
    / "icbm152_fem_tissues.nii.gz"
)


# ============================================================
# Tissue labels
# ============================================================

LABELS = {
    1: "skin",
    2: "bone",
    3: "csf",
    4: "gray",
    5: "white",
}


# ============================================================
# Settings
# ============================================================

# Use face-sharing connectivity only (6-connectivity).
#
# This is consistent with our previous topology analysis:
# voxels are considered connected only if they share a face.
STRUCTURE = ndimage.generate_binary_structure(
    rank=3,
    connectivity=1,
)

# Number of largest components to print for each tissue.
TOP_N = 15


# ============================================================
# 1. Load FEM tissue volume
# ============================================================

print("\n============================================")
print("LOADING FEM LABEL VOLUME")
print("============================================")

img = nib.load(FEM_VOLUME)
volume = np.asarray(img.dataobj, dtype=np.uint8)

voxel_sizes = np.asarray(
    img.header.get_zooms()[:3],
    dtype=float,
)

voxel_volume_mm3 = np.prod(voxel_sizes)

print("Shape:", volume.shape)
print("Voxel size [mm]:", tuple(voxel_sizes))
print("Voxel volume [mm^3]:", voxel_volume_mm3)
print("Labels:", np.unique(volume))


# ============================================================
# 2. Inspect each tissue independently
# ============================================================

print("\n============================================")
print("CONNECTED COMPONENT ANALYSIS")
print("============================================")

summary = {}


for tissue_label, tissue_name in LABELS.items():

    print("\n--------------------------------------------")
    print(
        f"{tissue_name.upper()} "
        f"(label {tissue_label})"
    )
    print("--------------------------------------------")

    mask = volume == tissue_label

    total_voxels = int(np.count_nonzero(mask))

    # --------------------------------------------------------
    # Connected-component labeling
    # --------------------------------------------------------

    component_map, n_components = ndimage.label(
        mask,
        structure=STRUCTURE,
    )

    # Label 0 = background, so ignore it.
    component_sizes = np.bincount(
        component_map.ravel()
    )[1:]

    if n_components == 0:

        print("No components found.")

        summary[tissue_name] = {
            "total_voxels": total_voxels,
            "n_components": 0,
            "largest": 0,
            "largest_fraction": 0.0,
        }

        continue

    # Sort component IDs by size, largest first.
    order = np.argsort(component_sizes)[::-1]

    largest_size = int(component_sizes[order[0]])

    largest_fraction = (
        largest_size / total_voxels
        if total_voxels > 0
        else 0.0
    )

    print(f"Total tissue voxels : {total_voxels:,}")
    print(f"Components          : {n_components:,}")

    print(
        f"Largest component   : "
        f"{largest_size:,} voxels"
    )

    print(
        f"Largest fraction    : "
        f"{100 * largest_fraction:.4f}%"
    )

    print(
        f"Largest volume      : "
        f"{largest_size * voxel_volume_mm3:,.1f} mm^3"
    )

    # --------------------------------------------------------
    # Print largest components
    # --------------------------------------------------------

    print(
        f"\nTop {min(TOP_N, n_components)} "
        f"components:"
    )

    for rank, idx in enumerate(
        order[:TOP_N],
        start=1,
    ):

        component_id = int(idx + 1)
        size = int(component_sizes[idx])

        fraction = (
            100.0 * size / total_voxels
        )

        # Get bounding box for this component.
        coords = np.argwhere(
            component_map == component_id
        )

        voxel_min = coords.min(axis=0)
        voxel_max = coords.max(axis=0)

        # Convert the extrema to MNI/world coordinates.
        world_min = nib.affines.apply_affine(
            img.affine,
            voxel_min,
        )

        world_max = nib.affines.apply_affine(
            img.affine,
            voxel_max,
        )

        print(
            f"  {rank:>2}. "
            f"ID={component_id:<5} "
            f"voxels={size:>9,} "
            f"({fraction:>8.4f}%)"
        )

        print(
            "      MNI bounds approx: "
            f"x [{world_min[0]:.1f}, "
            f"{world_max[0]:.1f}], "
            f"y [{world_min[1]:.1f}, "
            f"{world_max[1]:.1f}], "
            f"z [{world_min[2]:.1f}, "
            f"{world_max[2]:.1f}]"
        )

    # --------------------------------------------------------
    # Small-component statistics
    # --------------------------------------------------------

    thresholds = [
        10,
        100,
        1000,
        10000,
    ]

    print("\nSmall-component counts:")

    for threshold in thresholds:

        count = int(
            np.count_nonzero(
                component_sizes < threshold
            )
        )

        voxels_in_small = int(
            component_sizes[
                component_sizes < threshold
            ].sum()
        )

        print(
            f"  < {threshold:>5} voxels: "
            f"{count:>6} components | "
            f"{voxels_in_small:>9,} voxels total"
        )

    summary[tissue_name] = {
        "total_voxels": total_voxels,
        "n_components": int(n_components),
        "largest": largest_size,
        "largest_fraction": largest_fraction,
    }


# ============================================================
# 3. Overall summary
# ============================================================

print("\n============================================")
print("OVERALL COMPONENT SUMMARY")
print("============================================")

print(
    f"{'Tissue':<10}"
    f"{'Components':>14}"
    f"{'Largest voxels':>18}"
    f"{'Largest %':>14}"
)

for tissue_name, result in summary.items():

    print(
        f"{tissue_name:<10}"
        f"{result['n_components']:>14,}"
        f"{result['largest']:>18,}"
        f"{100 * result['largest_fraction']:>13.4f}%"
    )


print("\n============================================")
print("DONE")
print("============================================")