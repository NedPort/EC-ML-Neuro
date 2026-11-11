from pathlib import Path

import nibabel as nib
import numpy as np
import pyvista as pv
import vtk
from vtk.util.numpy_support import numpy_to_vtk


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
    / "conformal_interfaces"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_SURFACE = (
    OUTPUT_DIR
    / "icbm152_multitissue_interfaces_mni152.vtp"
)


# ============================================================
# Tissue labels
# ============================================================

LABEL_NAMES = {
    1: "skin",
    2: "bone",
    3: "csf",
    4: "gray",
    5: "white",
}


# ============================================================
# Visualization settings
# ============================================================

COLORS = {
    "skin": "peachpuff",
    "bone": "ivory",
    "csf": "deepskyblue",
    "gray": "lightcoral",
    "white": "wheat",
}

OPACITY = {
    "skin": 0.08,
    "bone": 0.15,
    "csf": 0.22,
    "gray": 0.50,
    "white": 0.90,
}


# ============================================================
# Helper: voxel coordinates -> MNI coordinates
# ============================================================

def voxel_to_mni(points, affine):
    """
    Transform N x 3 voxel-index coordinates into MNI/world
    coordinates using the NIfTI affine.
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
# Helper: topology diagnostics
# ============================================================

def topology_diagnostics(surface):
    """
    Return:
        boundary-edge count
        non-manifold-edge count
        connected-region count
    """

    boundary = surface.extract_feature_edges(
        boundary_edges=True,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=False,
    )

    nonmanifold = surface.extract_feature_edges(
        boundary_edges=False,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=True,
    )

    connected = surface.connectivity()

    if "RegionId" in connected.cell_data:

        n_regions = len(
            np.unique(
                connected.cell_data["RegionId"]
            )
        )

    elif "RegionId" in connected.point_data:

        n_regions = len(
            np.unique(
                connected.point_data["RegionId"]
            )
        )

    else:
        n_regions = -1

    return (
        boundary.n_cells,
        nonmanifold.n_cells,
        n_regions,
    )


# ============================================================
# 1. Load FEM label volume
# ============================================================

print("\n============================================")
print("LOADING LABELED FEM VOLUME")
print("============================================")

img = nib.load(FEM_VOLUME)

labels = np.asarray(
    img.dataobj,
    dtype=np.uint8,
)

affine = img.affine.copy()

print("Shape:", labels.shape)
print("Voxel size:", img.header.get_zooms()[:3])
print("Labels:", np.unique(labels))

print("\nAffine:")
print(affine)


# ============================================================
# 2. Pad volume with background
# ============================================================

print("\n============================================")
print("PADDING LABEL VOLUME")
print("============================================")

labels_padded = np.pad(
    labels,
    pad_width=1,
    mode="constant",
    constant_values=0,
)

print(
    "Original shape:",
    labels.shape,
)

print(
    "Padded shape  :",
    labels_padded.shape,
)


# ============================================================
# 3. Create VTK image
# ============================================================

print("\n============================================")
print("CREATING VTK LABEL IMAGE")
print("============================================")

vtk_image = vtk.vtkImageData()

vtk_image.SetDimensions(
    int(labels_padded.shape[0]),
    int(labels_padded.shape[1]),
    int(labels_padded.shape[2]),
)

vtk_image.SetSpacing(
    1.0,
    1.0,
    1.0,
)

# The padded array has one additional voxel before the
# original index 0 along each axis.
#
# Therefore:
#
# padded index 1 -> original voxel index 0
#
# Setting origin = (-1,-1,-1) makes the coordinates produced
# by VTK correspond to the original unpadded voxel index frame.

vtk_image.SetOrigin(
    -1.0,
    -1.0,
    -1.0,
)

vtk_labels = numpy_to_vtk(
    labels_padded.ravel(order="F"),
    deep=True,
    array_type=vtk.VTK_UNSIGNED_CHAR,
)

vtk_labels.SetName(
    "TissueLabel"
)

vtk_image.GetPointData().SetScalars(
    vtk_labels
)

print("VTK image created.")


# ============================================================
# 4. Extract each discrete tissue label
# ============================================================

print("\n============================================")
print("DISCRETE MULTI-TISSUE EXTRACTION")
print("============================================")

tissue_surfaces = {}

for tissue_label, tissue_name in LABEL_NAMES.items():

    print("\n--------------------------------------------")
    print(
        f"{tissue_name.upper()} "
        f"(label {tissue_label})"
    )
    print("--------------------------------------------")

    extractor = vtk.vtkDiscreteFlyingEdges3D()

    extractor.SetInputData(
        vtk_image
    )

    # IMPORTANT:
    #
    # Extract only ONE known discrete label in this call.
    #
    # Therefore every triangle produced by this extractor is
    # explicitly associated with tissue_label. We do not need
    # to infer its label from point-data averages.

    extractor.SetValue(
        0,
        tissue_label,
    )

    extractor.ComputeNormalsOff()
    extractor.ComputeGradientsOff()

    extractor.Update()

    vtk_poly = extractor.GetOutput()

    print(
        "Raw vertices:",
        f"{vtk_poly.GetNumberOfPoints():,}",
    )

    print(
        "Raw faces   :",
        f"{vtk_poly.GetNumberOfCells():,}",
    )

    surface = pv.wrap(
        vtk_poly
    )

    # --------------------------------------------------------
    # Transform VTK voxel coordinates -> MNI
    # --------------------------------------------------------

    points_voxel = np.asarray(
        surface.points,
        dtype=float,
    )

    points_mni = voxel_to_mni(
        points_voxel,
        affine,
    )

    surface.points = points_mni

    # --------------------------------------------------------
    # Explicitly assign known tissue label to every triangle
    # --------------------------------------------------------

    surface.cell_data.clear()
    surface.point_data.clear()

    surface.cell_data[
        "TissueLabel"
    ] = np.full(
        surface.n_cells,
        tissue_label,
        dtype=np.uint8,
    )

    # --------------------------------------------------------
    # Clean duplicate points within this tissue surface
    # --------------------------------------------------------

    surface = surface.clean()

    print(
        "Clean vertices:",
        f"{surface.n_points:,}",
    )

    print(
        "Clean faces   :",
        f"{surface.n_cells:,}",
    )

    print(
        "MNI bounds:"
    )

    print(
        surface.bounds
    )

    # --------------------------------------------------------
    # Topology diagnostics
    # --------------------------------------------------------

    (
        boundary_count,
        nonmanifold_count,
        region_count,
    ) = topology_diagnostics(
        surface
    )

    print(
        "Boundary edges    :",
        f"{boundary_count:,}",
    )

    print(
        "Non-manifold edges:",
        f"{nonmanifold_count:,}",
    )

    print(
        "Connected regions :",
        region_count,
    )

    # --------------------------------------------------------
    # Save individual tissue extraction
    # --------------------------------------------------------

    tissue_path = (
        OUTPUT_DIR
        / f"{tissue_name}_interface_mni152.vtp"
    )

    surface.save(
        tissue_path
    )

    print(
        "Saved:"
        f"\n  {tissue_path}"
    )

    tissue_surfaces[
        tissue_name
    ] = surface


# ============================================================
# 5. Combine all tissue surfaces
# ============================================================

print("\n============================================")
print("COMBINING TISSUE INTERFACES")
print("============================================")

combined = None

for tissue_name in LABEL_NAMES.values():

    surface = tissue_surfaces[
        tissue_name
    ]

    if combined is None:

        combined = surface.copy(
            deep=True
        )

    else:

        combined = combined.merge(
            surface,
            merge_points=False,
        )


print(
    "Before shared-point cleaning:"
)

print(
    "  vertices:",
    f"{combined.n_points:,}",
)

print(
    "  faces   :",
    f"{combined.n_cells:,}",
)


# ============================================================
# 6. Merge geometrically coincident interface vertices
# ============================================================

print("\n============================================")
print("MERGING COINCIDENT INTERFACE VERTICES")
print("============================================")

# clean() merges coincident points.
#
# The cell-associated TissueLabel is preserved, so each
# triangle keeps its explicit anatomical identity.

combined = combined.clean(
    tolerance=0.0,
    absolute=True,
)

print(
    "After shared-point cleaning:"
)

print(
    "  vertices:",
    f"{combined.n_points:,}",
)

print(
    "  faces   :",
    f"{combined.n_cells:,}",
)

print(
    "Cell arrays:",
    list(
        combined.cell_data.keys()
    ),
)

if (
    "TissueLabel"
    not in combined.cell_data
):

    raise RuntimeError(
        "TissueLabel was lost during "
        "surface combination."
    )


combined_labels = np.asarray(
    combined.cell_data[
        "TissueLabel"
    ],
    dtype=np.uint8,
)

print(
    "Combined tissue labels:",
    np.unique(
        combined_labels
    ),
)


# ============================================================
# 7. Combined label counts
# ============================================================

print("\n============================================")
print("COMBINED CELL LABEL COUNTS")
print("============================================")

unique_labels, counts = np.unique(
    combined_labels,
    return_counts=True,
)

for label, count in zip(
    unique_labels,
    counts,
):

    name = LABEL_NAMES.get(
        int(label),
        "unknown",
    )

    print(
        f"{int(label)} "
        f"({name:<7}): "
        f"{int(count):,} cells"
    )


# ============================================================
# 8. Global topology diagnostics
# ============================================================

print("\n============================================")
print("GLOBAL TOPOLOGY")
print("============================================")

global_boundary = (
    combined.extract_feature_edges(
        boundary_edges=True,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=False,
    )
)

global_nonmanifold = (
    combined.extract_feature_edges(
        boundary_edges=False,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=True,
    )
)

print(
    "Boundary edges:",
    f"{global_boundary.n_cells:,}",
)

print(
    "Non-manifold edges:",
    f"{global_nonmanifold.n_cells:,}",
)


# ============================================================
# 9. Per-tissue topology after combination
# ============================================================

print("\n============================================")
print("PER-TISSUE TOPOLOGY")
print("============================================")

validation_surfaces = {}

for tissue_label, tissue_name in LABEL_NAMES.items():

    tissue = combined.threshold(
        [
            tissue_label - 0.1,
            tissue_label + 0.1,
        ],
        scalars="TissueLabel",
        preference="cell",
    )

    tissue = tissue.extract_surface(
        algorithm="dataset_surface"
    ).clean()

    validation_surfaces[
        tissue_name
    ] = tissue

    (
        boundary_count,
        nonmanifold_count,
        region_count,
    ) = topology_diagnostics(
        tissue
    )

    print(
        f"{tissue_name:<8} | "
        f"vertices={tissue.n_points:>9,} | "
        f"faces={tissue.n_cells:>9,} | "
        f"boundary={boundary_count:>7,} | "
        f"nonmanifold={nonmanifold_count:>7,} | "
        f"regions={region_count:>5}"
    )


# ============================================================
# 10. Save combined mesh
# ============================================================

combined.save(
    OUTPUT_SURFACE
)

print("\n============================================")
print("SAVED COMBINED INTERFACE MESH")
print("============================================")

print(
    OUTPUT_SURFACE
)


# ============================================================
# 11. Visualization
# ============================================================

print("\n============================================")
print("OPENING VALIDATION VIEW")
print("============================================")

plotter = pv.Plotter(
    window_size=(1300, 900)
)

for tissue_name, tissue in validation_surfaces.items():

    plotter.add_mesh(
        tissue,
        color=COLORS[
            tissue_name
        ],
        opacity=OPACITY[
            tissue_name
        ],
        smooth_shading=True,
        show_edges=False,
        label=tissue_name,
    )


# ============================================================
# Show global non-manifold edges
# ============================================================

if global_nonmanifold.n_cells > 0:

    plotter.add_mesh(
        global_nonmanifold,
        color="red",
        line_width=5,
        render_lines_as_tubes=True,
        label="Global non-manifold",
    )


# ============================================================
# Show global boundary edges
# ============================================================

if global_boundary.n_cells > 0:

    plotter.add_mesh(
        global_boundary,
        color="yellow",
        line_width=4,
        render_lines_as_tubes=True,
        label="Global boundary",
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


# ============================================================
# 12. Final summary
# ============================================================

print("\n============================================")
print("DONE")
print("============================================")

print(
    "Combined interface mesh:"
)

print(
    OUTPUT_SURFACE
)

print(
    "\nDo NOT use this mesh for Gmsh yet."
)

print(
    "First evaluate the reported global and "
    "per-tissue topology."
)