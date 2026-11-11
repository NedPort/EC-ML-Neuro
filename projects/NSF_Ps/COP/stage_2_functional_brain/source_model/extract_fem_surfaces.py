from pathlib import Path

import nibabel as nib
import numpy as np
import pyvista as pv
from skimage import measure


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

OUTPUT_DIR = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "source_model"
    / "fem"
    / "tissue_surfaces"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# Tissue definitions
# ============================================================

TISSUES = {
    1: "skin",
    2: "bone",
    3: "csf",
    4: "gray",
    5: "white",
}


# ============================================================
# 1. Load labeled FEM volume
# ============================================================

print("\n============================================")
print("LOADING FEM LABEL VOLUME")
print("============================================")

img = nib.load(FEM_VOLUME)

labels = np.asarray(
    img.dataobj,
    dtype=np.uint8,
)

affine = img.affine.copy()

voxel_sizes = np.asarray(
    img.header.get_zooms()[:3],
    dtype=float,
)

print("Shape:", labels.shape)
print("Voxel size [mm]:", voxel_sizes)
print("Labels:", np.unique(labels))

print("\nAffine:")
print(affine)


# ============================================================
# 2. Helper: voxel coordinates -> MNI coordinates
# ============================================================

def voxel_to_mni(points):
    """
    Convert N x 3 voxel coordinates to MNI/world coordinates.
    """

    points = np.asarray(
        points,
        dtype=float,
    )

    homogeneous = np.column_stack(
        [
            points,
            np.ones(len(points)),
        ]
    )

    world = (
        affine @ homogeneous.T
    ).T[:, :3]

    return world


# ============================================================
# 3. Helper: create PyVista triangular surface
# ============================================================

def make_surface(vertices, faces):
    """
    Convert vertices and triangular faces from marching cubes
    into a PyVista PolyData object.
    """

    face_array = np.column_stack(
        [
            np.full(
                len(faces),
                3,
                dtype=np.int64,
            ),
            faces.astype(np.int64),
        ]
    ).ravel()

    surface = pv.PolyData(
        vertices,
        face_array,
    )

    surface = surface.clean()

    return surface


# ============================================================
# 4. Extract one surface per tissue
# ============================================================

print("\n============================================")
print("EXTRACTING TISSUE SURFACES")
print("============================================")

surfaces = {}

for tissue_label, tissue_name in TISSUES.items():

    print("\n--------------------------------------------")
    print(
        f"{tissue_name.upper()} "
        f"(label {tissue_label})"
    )
    print("--------------------------------------------")

    mask = (
        labels == tissue_label
    ).astype(np.uint8)

    n_voxels = int(
        np.count_nonzero(mask)
    )

    print(
        f"Tissue voxels: {n_voxels:,}"
    )

    if n_voxels == 0:
        raise RuntimeError(
            f"No voxels found for {tissue_name}"
        )

    # --------------------------------------------------------
    # Pad by one voxel.
    #
    # This is important for tissues that touch the edge of the
    # NIfTI volume. Marching cubes then sees background outside
    # the original image rather than producing an open surface.
    # --------------------------------------------------------

    padded = np.pad(
        mask,
        pad_width=1,
        mode="constant",
        constant_values=0,
    )

    # --------------------------------------------------------
    # Marching cubes
    #
    # We use voxel-index coordinates here and transform the
    # resulting vertices with the NIfTI affine afterward.
    # --------------------------------------------------------

    vertices, faces, normals, values = (
        measure.marching_cubes(
            padded,
            level=0.5,
            spacing=(1.0, 1.0, 1.0),
            allow_degenerate=False,
        )
    )

    # Remove the one-voxel padding offset.
    vertices -= 1.0

    # Convert to MNI coordinates.
    vertices_mni = voxel_to_mni(
        vertices
    )

    surface = make_surface(
        vertices_mni,
        faces,
    )

    surfaces[tissue_name] = surface

    print(
        f"Vertices: {surface.n_points:,}"
    )

    print(
        f"Faces   : {surface.n_cells:,}"
    )

    print(
        "Bounds  : "
        f"{surface.bounds}"
    )

    # --------------------------------------------------------
    # Surface topology diagnostics
    # --------------------------------------------------------

    boundary_edges = (
        surface.extract_feature_edges(
            boundary_edges=True,
            feature_edges=False,
            manifold_edges=False,
            non_manifold_edges=False,
        )
    )

    non_manifold_edges = (
        surface.extract_feature_edges(
            boundary_edges=False,
            feature_edges=False,
            manifold_edges=False,
            non_manifold_edges=True,
        )
    )

    print(
        f"Boundary-edge lines   : "
        f"{boundary_edges.n_cells:,}"
    )

    print(
        f"Non-manifold edges    : "
        f"{non_manifold_edges.n_cells:,}"
    )

    # --------------------------------------------------------
    # Connected surface regions
    # --------------------------------------------------------

    connected = surface.connectivity()

    if (
        "RegionId"
        in connected.point_data
    ):
        region_ids = np.unique(
            connected.point_data[
                "RegionId"
            ]
        )

        n_regions = len(region_ids)

    elif (
        "RegionId"
        in connected.cell_data
    ):
        region_ids = np.unique(
            connected.cell_data[
                "RegionId"
            ]
        )

        n_regions = len(region_ids)

    else:
        n_regions = -1

    print(
        f"Connected surface regions: "
        f"{n_regions}"
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    output_file = (
        OUTPUT_DIR
        / f"{tissue_name}_surface_mni152.vtp"
    )

    surface.save(
        output_file
    )

    print(
        "Saved:"
        f"\n  {output_file}"
    )


# ============================================================
# 5. Overall summary
# ============================================================

print("\n============================================")
print("SURFACE EXTRACTION SUMMARY")
print("============================================")

for tissue_name, surface in surfaces.items():

    boundary_edges = (
        surface.extract_feature_edges(
            boundary_edges=True,
            feature_edges=False,
            manifold_edges=False,
            non_manifold_edges=False,
        )
    )

    non_manifold_edges = (
        surface.extract_feature_edges(
            boundary_edges=False,
            feature_edges=False,
            manifold_edges=False,
            non_manifold_edges=True,
        )
    )

    print(
        f"{tissue_name:<8} | "
        f"vertices={surface.n_points:>9,} | "
        f"faces={surface.n_cells:>9,} | "
        f"boundary={boundary_edges.n_cells:>7,} | "
        f"nonmanifold={non_manifold_edges.n_cells:>7,}"
    )


# ============================================================
# 6. Visual validation
# ============================================================

print("\n============================================")
print("OPENING SURFACE VALIDATION VIEW")
print("============================================")

plotter = pv.Plotter(
    window_size=(1300, 900)
)

# Distinct anatomical colors for visualization only.
colors = {
    "skin": "peachpuff",
    "bone": "ivory",
    "csf": "deepskyblue",
    "gray": "lightcoral",
    "white": "wheat",
}

opacity = {
    "skin": 0.10,
    "bone": 0.18,
    "csf": 0.25,
    "gray": 0.55,
    "white": 0.90,
}

for tissue_name, surface in surfaces.items():

    plotter.add_mesh(
        surface,
        color=colors[tissue_name],
        opacity=opacity[tissue_name],
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
    xtitle="X MNI (mm)",
    ytitle="Y MNI (mm)",
    ztitle="Z MNI (mm)",
)

plotter.add_legend()

plotter.camera_position = "iso"

plotter.show()