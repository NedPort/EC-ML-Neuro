from pathlib import Path

import nibabel as nib
import numpy as np
import pyvista as pv


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

SCALP_MNI = (
    PROJECT_ROOT
    / "hm_icbm152"
    / "mask_scalp_mni152.obj"
)


# ============================================================
# Tissue labels
# ============================================================

LABELS = {
    0: "background",
    1: "skin",
    2: "bone",
    3: "csf",
    4: "gray",
    5: "white",
}

# Interfaces we want to inspect.
CONTACTS = [
    (0, 2),  # background <-> bone
    (1, 3),  # skin <-> CSF
    (3, 5),  # CSF <-> white
]


# ============================================================
# 1. Load labeled FEM volume
# ============================================================

print("\n============================================")
print("LOADING FEM VOLUME")
print("============================================")

img = nib.load(FEM_VOLUME)
volume = np.asarray(img.dataobj, dtype=np.uint8)
affine = img.affine

print("Shape:", volume.shape)
print("Voxel size:", img.header.get_zooms()[:3])

print("\nAffine:")
print(affine)


# ============================================================
# 2. Helper: voxel indices -> MNI coordinates
# ============================================================

def voxel_to_mni(indices):
    """
    Convert N x 3 voxel indices to N x 3 MNI coordinates.
    """

    indices = np.asarray(indices, dtype=float)

    homogeneous = np.column_stack(
        [
            indices,
            np.ones(len(indices)),
        ]
    )

    xyz = (affine @ homogeneous.T).T[:, :3]

    return xyz


# ============================================================
# 3. Find contact voxels
# ============================================================

def find_contact_voxels(volume, label_a, label_b):
    """
    Find voxels belonging to label_a that share a face with
    label_b, and vice versa.

    Returns unique voxel coordinates for the interface region.
    """

    contact_indices = []

    for axis in range(3):

        slicer_a = [slice(None)] * 3
        slicer_b = [slice(None)] * 3

        slicer_a[axis] = slice(0, -1)
        slicer_b[axis] = slice(1, None)

        left = volume[tuple(slicer_a)]
        right = volume[tuple(slicer_b)]

        # A on left, B on right
        mask_ab = (
            (left == label_a)
            & (right == label_b)
        )

        # B on left, A on right
        mask_ba = (
            (left == label_b)
            & (right == label_a)
        )

        # ----------------------------------------------------
        # A-B orientation
        # ----------------------------------------------------

        idx = np.argwhere(mask_ab)

        if len(idx) > 0:

            idx_left = idx.copy()
            idx_right = idx.copy()

            idx_right[:, axis] += 1

            contact_indices.append(idx_left)
            contact_indices.append(idx_right)

        # ----------------------------------------------------
        # B-A orientation
        # ----------------------------------------------------

        idx = np.argwhere(mask_ba)

        if len(idx) > 0:

            idx_left = idx.copy()
            idx_right = idx.copy()

            idx_right[:, axis] += 1

            contact_indices.append(idx_left)
            contact_indices.append(idx_right)

    if not contact_indices:
        return np.empty((0, 3), dtype=int)

    contact_indices = np.vstack(contact_indices)

    # Same voxel may participate in several neighboring faces.
    contact_indices = np.unique(
        contact_indices,
        axis=0,
    )

    return contact_indices


# ============================================================
# 4. Extract interfaces
# ============================================================

print("\n============================================")
print("EXTRACTING CONTACT LOCATIONS")
print("============================================")

contact_clouds = {}

for label_a, label_b in CONTACTS:

    indices = find_contact_voxels(
        volume,
        label_a,
        label_b,
    )

    xyz = voxel_to_mni(indices)

    key = (label_a, label_b)

    contact_clouds[key] = xyz

    print(
        f"{LABELS[label_a]:>10} <-> "
        f"{LABELS[label_b]:<10}: "
        f"{len(indices):,} unique contact voxels"
    )

    if len(xyz) > 0:

        print(
            "    MNI bounds:"
            f"\n      x: {xyz[:, 0].min():.1f} "
            f"to {xyz[:, 0].max():.1f}"
            f"\n      y: {xyz[:, 1].min():.1f} "
            f"to {xyz[:, 1].max():.1f}"
            f"\n      z: {xyz[:, 2].min():.1f} "
            f"to {xyz[:, 2].max():.1f}"
        )


# ============================================================
# 5. Load scalp for anatomical context
# ============================================================

scalp = pv.read(SCALP_MNI)


# ============================================================
# 6. Plot
# ============================================================

print("\n============================================")
print("OPENING DIAGNOSTIC VIEW")
print("============================================")

plotter = pv.Plotter(
    window_size=(1300, 900)
)

# Transparent scalp for anatomical reference.
plotter.add_mesh(
    scalp,
    opacity=0.12,
    smooth_shading=True,
    show_edges=False,
    color="lightgray",
    label="Scalp",
)


# ============================================================
# Contact 1: background <-> bone
# ============================================================

xyz = contact_clouds[(0, 2)]

if len(xyz) > 0:

    cloud = pv.PolyData(xyz)

    plotter.add_mesh(
        cloud,
        color="red",
        point_size=6,
        render_points_as_spheres=True,
        label="Background-Bone",
    )


# ============================================================
# Contact 2: skin <-> CSF
# ============================================================

xyz = contact_clouds[(1, 3)]

if len(xyz) > 0:

    cloud = pv.PolyData(xyz)

    plotter.add_mesh(
        cloud,
        color="orange",
        point_size=6,
        render_points_as_spheres=True,
        label="Skin-CSF",
    )


# ============================================================
# Contact 3: CSF <-> white matter
# ============================================================

xyz = contact_clouds[(3, 5)]

if len(xyz) > 0:

    cloud = pv.PolyData(xyz)

    plotter.add_mesh(
        cloud,
        color="blue",
        point_size=6,
        render_points_as_spheres=True,
        label="CSF-White",
    )


# ============================================================
# Display settings
# ============================================================

plotter.add_axes(
    xlabel="X",
    ylabel="Y",
    zlabel="Z",
)

plotter.show_grid(
    xtitle="X MNI (mm)",
    ytitle="Y MNI (mm)",
    ztitle="Z MNI (mm)",
)

plotter.add_legend()

plotter.camera_position = "iso"

plotter.show()