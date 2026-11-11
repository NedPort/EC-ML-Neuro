from pathlib import Path

import nibabel as nib
import numpy as np
import pyvista as pv
from scipy import ndimage
from skimage import measure


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parents[3]

ANATOMY_DIR = ROOT / "hm_icbm152"

BEM_ROOT = (
    ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "bem"
)

OUTPUT_DIR = BEM_ROOT / "surfaces"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# Input anatomical masks
# ------------------------------------------------------------

MASK_PATHS = {
    "skin": ANATOMY_DIR / "mask_skin.nii",
    "bone": ANATOMY_DIR / "mask_bone.nii",
    "csf": ANATOMY_DIR / "mask_csf.nii",
    "gray": ANATOMY_DIR / "mask_gray.nii",
    "white": ANATOMY_DIR / "mask_white.nii",
}

CORTEX_PATH = (
    ANATOMY_DIR
    / "cortex_pial_high_mni152.obj"
)


# ------------------------------------------------------------
# BEM construction parameters
# ------------------------------------------------------------

# Inferior cutoff for the cerebral intracranial compartment.
CEREBRAL_Z_MIN = -65.0


# Previously validated:
#
# Initial/near-zero margin -> ~96.410% cortex containment
# 2 mm                    -> 99.859%
# 3 mm                    -> 100%
#
# KEEP THIS FROZEN.
INNER_SKULL_MARGIN_MM = 3.0


# NEW:
#
# Minimum computational separation between the inner- and
# outer-skull BEM volumes.
#
# This is NOT intended to represent anatomical skull thickness.
# It prevents coincident conductivity interfaces where the
# bone-derived outer envelope does not extend beyond the
# inner-skull envelope.
OUTER_SKULL_MIN_MARGIN_MM = 2.0


# Morphological cleanup used for derived BEM envelopes.
CLOSING_ITERATIONS = 2


# ============================================================
# Utility functions
# ============================================================

def load_binary_mask(path):
    """Load a NIfTI mask as a Boolean volume."""

    img = nib.load(path)

    data = np.asarray(
        img.get_fdata()
    )

    mask = data > 0

    return mask, img.affine.copy()


def keep_largest_component(mask):
    """Keep only the largest 26-connected component."""

    structure = np.ones(
        (3, 3, 3),
        dtype=np.uint8,
    )

    labels, n_components = ndimage.label(
        mask,
        structure=structure,
    )

    if n_components == 0:
        raise RuntimeError(
            "No connected components found."
        )

    counts = np.bincount(
        labels.ravel()
    )

    counts[0] = 0

    largest_label = int(
        np.argmax(counts)
    )

    return labels == largest_label


def keep_components_touching(mask, reference):
    """
    Keep connected components of `mask` that touch `reference`.
    """

    structure = np.ones(
        (3, 3, 3),
        dtype=np.uint8,
    )

    labels, n_components = ndimage.label(
        mask,
        structure=structure,
    )

    if n_components == 0:
        return np.zeros_like(
            mask,
            dtype=bool,
        )

    touching_labels = np.unique(
        labels[reference & (labels > 0)]
    )

    touching_labels = touching_labels[
        touching_labels > 0
    ]

    if len(touching_labels) == 0:
        return np.zeros_like(
            mask,
            dtype=bool,
        )

    return np.isin(
        labels,
        touching_labels,
    )


def make_ball(radius_voxels):
    """
    Create a spherical binary structuring element.
    """

    radius_voxels = int(radius_voxels)

    if radius_voxels < 1:
        return np.ones(
            (1, 1, 1),
            dtype=bool,
        )

    r = radius_voxels

    x, y, z = np.ogrid[
        -r:r + 1,
        -r:r + 1,
        -r:r + 1,
    ]

    ball = (
        x * x
        + y * y
        + z * z
    ) <= r * r

    return ball


def voxel_margin_to_radius(
    margin_mm,
    affine,
):
    """
    Convert an isotropic physical margin in mm to voxel radius.
    """

    voxel_sizes = np.sqrt(
        np.sum(
            affine[:3, :3] ** 2,
            axis=0,
        )
    )

    if not np.allclose(
        voxel_sizes,
        voxel_sizes[0],
        atol=1e-6,
    ):
        raise RuntimeError(
            "Expected isotropic voxel spacing."
        )

    voxel_size = float(
        voxel_sizes[0]
    )

    radius = int(
        np.ceil(
            margin_mm / voxel_size
        )
    )

    return radius, voxel_size


def volume_to_surface(
    mask,
    affine,
):
    """
    Convert a binary voxel volume to a triangular surface
    using marching cubes.

    Returned coordinates are in the world/MNI coordinate
    system defined by the NIfTI affine.
    """

    volume = mask.astype(
        np.uint8
    )

    vertices_voxel, faces, _, _ = (
        measure.marching_cubes(
            volume,
            level=0.5,
            spacing=(1.0, 1.0, 1.0),
        )
    )

    vertices_world = nib.affines.apply_affine(
        affine,
        vertices_voxel,
    )

    faces_pv = np.hstack(
        [
            np.full(
                (len(faces), 1),
                3,
                dtype=np.int64,
            ),
            faces.astype(np.int64),
        ]
    ).ravel()

    mesh = pv.PolyData(
        vertices_world,
        faces_pv,
    )

    mesh = (
        mesh
        .triangulate()
        .clean()
    )

    mesh = mesh.compute_normals(
        cell_normals=True,
        point_normals=True,
        consistent_normals=True,
        auto_orient_normals=True,
        split_vertices=False,
        inplace=False,
    )

    return mesh


def topology_report(
    mesh,
    name,
):
    """Print basic surface topology information."""

    boundary = mesh.extract_feature_edges(
        boundary_edges=True,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=False,
    )

    non_manifold = mesh.extract_feature_edges(
        boundary_edges=False,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=True,
    )

    connectivity = mesh.connectivity()

    region_ids = np.asarray(
        connectivity["RegionId"]
    )

    n_regions = (
        len(np.unique(region_ids))
        if len(region_ids) > 0
        else 0
    )

    print(f"\n{name}")
    print("-" * 72)

    print(
        f"points              : "
        f"{mesh.n_points:,}"
    )

    print(
        f"faces               : "
        f"{mesh.n_cells:,}"
    )

    print(
        f"boundary edges      : "
        f"{boundary.n_cells:,}"
    )

    print(
        f"non-manifold edges  : "
        f"{non_manifold.n_cells:,}"
    )

    print(
        f"connected regions   : "
        f"{n_regions:,}"
    )

    bounds = mesh.bounds

    print(
        f"x bounds [mm]       : "
        f"{bounds[0]:.3f} to "
        f"{bounds[1]:.3f}"
    )

    print(
        f"y bounds [mm]       : "
        f"{bounds[2]:.3f} to "
        f"{bounds[3]:.3f}"
    )

    print(
        f"z bounds [mm]       : "
        f"{bounds[4]:.3f} to "
        f"{bounds[5]:.3f}"
    )

    return {
        "boundary_edges": boundary.n_cells,
        "non_manifold_edges": non_manifold.n_cells,
        "regions": n_regions,
    }


# ============================================================
# Load masks
# ============================================================

print("\nLOADING ICBM152 MASKS")
print("=" * 72)

masks = {}
affines = {}


for name, path in MASK_PATHS.items():

    mask, affine = load_binary_mask(
        path
    )

    masks[name] = mask
    affines[name] = affine

    print(
        f"{name:<8}: "
        f"{np.count_nonzero(mask):,} voxels"
    )


# ============================================================
# Validate common geometry
# ============================================================

reference_shape = masks["skin"].shape
reference_affine = affines["skin"]


for name in masks:

    if masks[name].shape != reference_shape:
        raise RuntimeError(
            f"{name} has a different volume shape."
        )

    if not np.allclose(
        affines[name],
        reference_affine,
    ):
        raise RuntimeError(
            f"{name} has a different affine."
        )


affine = reference_affine


print("\nCommon volume shape:")
print(reference_shape)

print("\nCommon affine:")
print(affine)


# ============================================================
# Load cortical surface
# ============================================================

print("\nLOADING HIGH-RESOLUTION CORTEX")
print("=" * 72)

cortex = (
    pv.read(CORTEX_PATH)
    .triangulate()
    .clean()
)

print(
    f"Cortex points : "
    f"{cortex.n_points:,}"
)

print(
    f"Cortex faces  : "
    f"{cortex.n_cells:,}"
)

print(
    "Cortex bounds:"
)

print(
    f"  x: {cortex.bounds[0]:.3f} "
    f"to {cortex.bounds[1]:.3f}"
)

print(
    f"  y: {cortex.bounds[2]:.3f} "
    f"to {cortex.bounds[3]:.3f}"
)

print(
    f"  z: {cortex.bounds[4]:.3f} "
    f"to {cortex.bounds[5]:.3f}"
)


# ============================================================
# Coordinate grid for cerebral ROI
# ============================================================

shape = reference_shape

ijk = np.indices(
    shape,
    sparse=True,
)

# With the current ICBM152 affine:
#
# world_z = affine[2,0]*i +
#           affine[2,1]*j +
#           affine[2,2]*k +
#           affine[2,3]
#
# Since the current affine is axis-aligned, this can be
# calculated efficiently from the k dimension.

k_coords = np.arange(
    shape[2],
    dtype=float,
)

world_z = (
    affine[2, 2] * k_coords
    + affine[2, 3]
)

cerebral_z_mask = (
    world_z >= CEREBRAL_Z_MIN
)

cerebral_z_mask = cerebral_z_mask[
    np.newaxis,
    np.newaxis,
    :
]


print("\nCEREBRAL ROI")
print("=" * 72)

print(
    f"Minimum retained MNI z = "
    f"{CEREBRAL_Z_MIN:.1f} mm"
)


# ============================================================
# Construct intracranial cerebral volume
# ============================================================

intracranial_raw = (
    masks["csf"]
    | masks["gray"]
    | masks["white"]
)

print(
    "\nRaw intracranial voxels:"
)

print(
    f"{np.count_nonzero(intracranial_raw):,}"
)


intracranial_cerebral = (
    intracranial_raw
    & cerebral_z_mask
)

intracranial_cerebral = (
    keep_largest_component(
        intracranial_cerebral
    )
)


print(
    "Cerebral intracranial voxels:"
)

print(
    f"{np.count_nonzero(intracranial_cerebral):,}"
)


# ============================================================
# Clean cerebral intracranial volume
# ============================================================

structure_3 = np.ones(
    (3, 3, 3),
    dtype=bool,
)

intracranial_clean = (
    ndimage.binary_closing(
        intracranial_cerebral,
        structure=structure_3,
        iterations=CLOSING_ITERATIONS,
    )
)

intracranial_clean = (
    ndimage.binary_fill_holes(
        intracranial_clean
    )
)

intracranial_clean = (
    keep_largest_component(
        intracranial_clean
    )
)


# ============================================================
# INNER SKULL
#
# Frozen 3-mm margin.
# ============================================================

inner_radius, voxel_size = (
    voxel_margin_to_radius(
        INNER_SKULL_MARGIN_MM,
        affine,
    )
)

print("\nINNER-SKULL CONSTRUCTION")
print("=" * 72)

print(
    f"Requested margin : "
    f"{INNER_SKULL_MARGIN_MM:.1f} mm"
)

print(
    f"Voxel size       : "
    f"{voxel_size:.3f} mm"
)

print(
    f"Dilation radius  : "
    f"{inner_radius} voxels"
)


inner_structure = make_ball(
    inner_radius
)

inner_skull_volume = (
    ndimage.binary_dilation(
        intracranial_clean,
        structure=inner_structure,
        iterations=1,
    )
)

inner_skull_volume = (
    ndimage.binary_fill_holes(
        inner_skull_volume
    )
)

inner_skull_volume = (
    keep_largest_component(
        inner_skull_volume
    )
)


print(
    "Derived inner-skull volume:"
)

print(
    f"{np.count_nonzero(inner_skull_volume):,}"
)


# ============================================================
# Relevant bone
#
# Keep cerebral bone components associated with the
# intracranial/skull region.
# ============================================================

print("\nBONE SELECTION")
print("=" * 72)

bone_cerebral = (
    masks["bone"]
    & cerebral_z_mask
)

bone_cerebral = ndimage.binary_closing(
    bone_cerebral,
    structure=structure_3,
    iterations=CLOSING_ITERATIONS,
)


# Reference slightly expanded from the inner skull so that
# nearby cranial bone components are retained.

bone_reference = ndimage.binary_dilation(
    inner_skull_volume,
    structure=make_ball(2),
    iterations=1,
)

bone_relevant = keep_components_touching(
    bone_cerebral,
    bone_reference,
)


print(
    "Relevant bone voxels:"
)

print(
    f"{np.count_nonzero(bone_relevant):,}"
)


# ============================================================
# OUTER SKULL
#
# IMPORTANT NEW RULE:
#
# The previous construction used approximately:
#
#     inner_skull | bone_relevant
#
# This allowed inner and outer skull surfaces to become
# exactly coincident where the bone-derived envelope did not
# extend beyond the inner skull.
#
# We now create a minimum 2-mm computational envelope around
# the already-frozen inner-skull volume.
#
# This is a BEM interface-separation rule, NOT a claim about
# anatomical skull thickness.
# ============================================================

print("\nOUTER-SKULL CONSTRUCTION")
print("=" * 72)

outer_margin_radius, _ = (
    voxel_margin_to_radius(
        OUTER_SKULL_MIN_MARGIN_MM,
        affine,
    )
)


print(
    f"Minimum requested BEM margin : "
    f"{OUTER_SKULL_MIN_MARGIN_MM:.1f} mm"
)

print(
    f"Voxel size                    : "
    f"{voxel_size:.3f} mm"
)

print(
    f"Dilation radius               : "
    f"{outer_margin_radius} voxels"
)


outer_margin_structure = make_ball(
    outer_margin_radius
)


inner_skull_min_outer_envelope = (
    ndimage.binary_dilation(
        inner_skull_volume,
        structure=outer_margin_structure,
        iterations=1,
    )
)


print(
    "Minimum outer envelope voxels:"
)

print(
    f"{np.count_nonzero(inner_skull_min_outer_envelope):,}"
)


# Combine:
#
# 1. guaranteed minimum envelope around inner skull
# 2. available anatomical bone information

outer_skull_volume = (
    inner_skull_min_outer_envelope
    | bone_relevant
)


# Clean only the DERIVED outer-skull BEM volume.

outer_skull_volume = (
    ndimage.binary_closing(
        outer_skull_volume,
        structure=structure_3,
        iterations=CLOSING_ITERATIONS,
    )
)

outer_skull_volume = (
    ndimage.binary_fill_holes(
        outer_skull_volume
    )
)

outer_skull_volume = (
    keep_largest_component(
        outer_skull_volume
    )
)


# Explicit safety condition.
outer_skull_volume |= (
    inner_skull_min_outer_envelope
)


print(
    "Derived outer-skull volume:"
)

print(
    f"{np.count_nonzero(outer_skull_volume):,}"
)


# ============================================================
# OUTER SKIN
#
# Construct from the full head-material union.
# ============================================================

print("\nOUTER-SKIN CONSTRUCTION")
print("=" * 72)

head_material = (
    masks["skin"]
    | masks["bone"]
    | masks["csf"]
    | masks["gray"]
    | masks["white"]
)

head_material = (
    keep_largest_component(
        head_material
    )
)

outer_skin_volume = (
    ndimage.binary_closing(
        head_material,
        structure=structure_3,
        iterations=CLOSING_ITERATIONS,
    )
)

outer_skin_volume = (
    ndimage.binary_fill_holes(
        outer_skin_volume
    )
)

outer_skin_volume = (
    keep_largest_component(
        outer_skin_volume
    )
)


# ============================================================
# Enforce volume nesting
# ============================================================

outer_skull_volume |= (
    inner_skull_volume
)

outer_skin_volume |= (
    outer_skull_volume
)


print(
    "Derived outer-skin volume:"
)

print(
    f"{np.count_nonzero(outer_skin_volume):,}"
)


# ============================================================
# Voxel-space nesting checks
# ============================================================

print("\nVOXEL NESTING CHECK")
print("=" * 72)

inner_outside_outer = np.count_nonzero(
    inner_skull_volume
    & ~outer_skull_volume
)

outer_outside_skin = np.count_nonzero(
    outer_skull_volume
    & ~outer_skin_volume
)


print(
    "Inner-skull voxels outside outer skull:"
)

print(
    f"{inner_outside_outer:,}"
)


print(
    "Outer-skull voxels outside outer skin:"
)

print(
    f"{outer_outside_skin:,}"
)


# ============================================================
# Convert derived volumes to surfaces
# ============================================================

print("\nEXTRACTING TRIANGULATED SURFACES")
print("=" * 72)

inner_mesh = volume_to_surface(
    inner_skull_volume,
    affine,
)

outer_mesh = volume_to_surface(
    outer_skull_volume,
    affine,
)

skin_mesh = volume_to_surface(
    outer_skin_volume,
    affine,
)


# ============================================================
# Save surfaces
# ============================================================

INNER_OUTPUT = (
    OUTPUT_DIR
    / "inner_skull.vtk"
)

OUTER_OUTPUT = (
    OUTPUT_DIR
    / "outer_skull.vtk"
)

SKIN_OUTPUT = (
    OUTPUT_DIR
    / "outer_skin.vtk"
)


inner_mesh.save(
    INNER_OUTPUT
)

outer_mesh.save(
    OUTER_OUTPUT
)

skin_mesh.save(
    SKIN_OUTPUT
)


print("\nSaved:")
print(INNER_OUTPUT)
print(OUTER_OUTPUT)
print(SKIN_OUTPUT)


# ============================================================
# Surface topology
# ============================================================

print("\nSURFACE TOPOLOGY")
print("=" * 72)

inner_topology = topology_report(
    inner_mesh,
    "INNER SKULL",
)

outer_topology = topology_report(
    outer_mesh,
    "OUTER SKULL",
)

skin_topology = topology_report(
    skin_mesh,
    "OUTER SKIN",
)


# ============================================================
# Cortex containment
# ============================================================

print("\nCORTEX CONTAINMENT")
print("=" * 72)

cortex_points = pv.PolyData(
    np.asarray(cortex.points)
)

selection = (
    cortex_points
    .select_enclosed_points(
        inner_mesh,
        tolerance=0.0,
        check_surface=True,
    )
)

inside_mask = np.asarray(
    selection["SelectedPoints"]
).astype(bool)

n_cortex = cortex.n_points

n_inside = int(
    np.count_nonzero(
        inside_mask
    )
)

n_outside = (
    n_cortex
    - n_inside
)


containment_percent = (
    100.0
    * n_inside
    / n_cortex
)


print(
    f"Total cortex vertices : "
    f"{n_cortex:,}"
)

print(
    f"Inside inner skull    : "
    f"{n_inside:,}"
)

print(
    f"Outside inner skull   : "
    f"{n_outside:,}"
)

print(
    f"Containment           : "
    f"{containment_percent:.4f}%"
)


outside_cortex_points = np.asarray(
    cortex.points
)[~inside_mask]


# ============================================================
# Preliminary validation summary
# ============================================================

print("\nPRELIMINARY VALIDATION")
print("=" * 72)


checks = {
    "Voxel nesting inner -> outer":
        inner_outside_outer == 0,

    "Voxel nesting outer -> skin":
        outer_outside_skin == 0,

    "Inner skull closed":
        inner_topology["boundary_edges"] == 0,

    "Inner skull manifold":
        inner_topology["non_manifold_edges"] == 0,

    "Inner skull single region":
        inner_topology["regions"] == 1,

    "Outer skull closed":
        outer_topology["boundary_edges"] == 0,

    "Outer skull manifold":
        outer_topology["non_manifold_edges"] == 0,

    "Outer skull single region":
        outer_topology["regions"] == 1,

    "Outer skin closed":
        skin_topology["boundary_edges"] == 0,

    "Outer skin manifold":
        skin_topology["non_manifold_edges"] == 0,

    "Outer skin single region":
        skin_topology["regions"] == 1,

    "Cortex fully inside inner skull":
        n_outside == 0,
}


for label, passed in checks.items():

    status = (
        "PASS"
        if passed
        else "FAIL"
    )

    print(
        f"{label:<42} "
        f"{status}"
    )


# ============================================================
# Visualization
# ============================================================

print("\nOPENING BEM VISUALIZATION")
print("=" * 72)


plotter = pv.Plotter()


# Outer skin
plotter.add_mesh(
    skin_mesh,
    color="lightgray",
    opacity=0.10,
    smooth_shading=True,
    label="Outer skin",
)


# Outer skull
plotter.add_mesh(
    outer_mesh,
    color="orange",
    opacity=0.20,
    smooth_shading=True,
    label="Outer skull",
)


# Inner skull
plotter.add_mesh(
    inner_mesh,
    color="royalblue",
    opacity=0.25,
    smooth_shading=True,
    label="Inner skull",
)


# Cortex
plotter.add_mesh(
    cortex,
    color="red",
    opacity=0.85,
    smooth_shading=True,
    label="Cortex",
)


# Cortex points outside inner skull
if n_outside > 0:

    outside_cloud = pv.PolyData(
        outside_cortex_points
    )

    plotter.add_mesh(
        outside_cloud,
        color="yellow",
        point_size=8,
        render_points_as_spheres=True,
        label="Cortex outside inner skull",
    )


plotter.add_legend()

plotter.add_axes()

plotter.show_grid()

plotter.show()


# ============================================================
# Final message
# ============================================================

print("\n" + "=" * 72)

if all(checks.values()):

    print(
        "DERIVED BEM SURFACE CONSTRUCTION: "
        "PRELIMINARY PASS"
    )

else:

    print(
        "DERIVED BEM SURFACE CONSTRUCTION: "
        "CHECK FAILED ITEMS"
    )

print("=" * 72)

print(
    "\nImportant:"
)

print(
    "This validates the derived geometry/topology only."
)

print(
    "It does NOT yet establish MNE BEM compatibility."
)

print(
    "\nNext step:"
)

print(
    "Run diagnose_skull_nesting.py before "
    "running the expensive MNE validation."
)