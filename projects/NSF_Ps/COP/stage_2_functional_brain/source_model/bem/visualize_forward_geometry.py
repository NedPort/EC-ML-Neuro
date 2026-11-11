from pathlib import Path

import mne
import numpy as np
import pandas as pd
import pyvista as pv


# ============================================================
# Paths
# ============================================================

BEM_ROOT = Path(__file__).resolve().parent
COP_ROOT = BEM_ROOT.parents[2]

ICO4_DIR = (
    BEM_ROOT
    / "surfaces_mne_ico4"
)

OUTER_SKIN_PATH = (
    ICO4_DIR
    / "outer_skin_5120.vtk"
)

OUTER_SKULL_PATH = (
    ICO4_DIR
    / "outer_skull_5120.vtk"
)

INNER_SKULL_PATH = (
    ICO4_DIR
    / "inner_skull_5120.vtk"
)

CORTEX_PATH = (
    COP_ROOT
    / "hm_icbm152"
    / "cortex_pial_high_mni152.obj"
)

SOURCE_PATH = (
    BEM_ROOT
    / "source_space_candidates"
    / "source_space_p2500.csv"
)

CAPTRAK_PATH = (
    COP_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "source_localization"
    / "sub-1_ses-0_captrak_sensor_geometry.csv"
)

REGISTERED_PATH = (
    COP_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "source_localization"
    / "sub-1_ses-0_captrak_registered_mni152.csv"
)

TRANS_PATH = (
    BEM_ROOT
    / "sub-1_ses-0-head-mri-trans.fif"
)


# ============================================================
# Header
# ============================================================

print("=" * 78)
print("FORWARD-MODEL GEOMETRY VISUALIZATION")
print("=" * 78)


# ============================================================
# 1. Check required files
# ============================================================

required_files = [
    OUTER_SKIN_PATH,
    OUTER_SKULL_PATH,
    INNER_SKULL_PATH,
    CORTEX_PATH,
    SOURCE_PATH,
    CAPTRAK_PATH,
    REGISTERED_PATH,
    TRANS_PATH,
]

for path in required_files:

    if not path.exists():
        raise FileNotFoundError(
            f"Missing required file:\n{path}"
        )

    print(f"PASS  {path.name}")


# ============================================================
# 2. Load BEM surfaces
# ============================================================

print("\n" + "=" * 78)
print("LOAD BEM SURFACES")
print("=" * 78)

outer_skin = pv.read(
    OUTER_SKIN_PATH
)

outer_skull = pv.read(
    OUTER_SKULL_PATH
)

inner_skull = pv.read(
    INNER_SKULL_PATH
)

print(
    f"\nOuter skin  : "
    f"{outer_skin.n_points:,} vertices, "
    f"{outer_skin.n_cells:,} triangles"
)

print(
    f"Outer skull : "
    f"{outer_skull.n_points:,} vertices, "
    f"{outer_skull.n_cells:,} triangles"
)

print(
    f"Inner skull : "
    f"{inner_skull.n_points:,} vertices, "
    f"{inner_skull.n_cells:,} triangles"
)


# ============================================================
# 3. Load physical MNI152 cortex
# ============================================================

print("\n" + "=" * 78)
print("LOAD PHYSICAL CORTEX")
print("=" * 78)

cortex = pv.read(
    CORTEX_PATH
)

print(
    f"\nCortex vertices  : "
    f"{cortex.n_points:,}"
)

print(
    f"Cortex triangles : "
    f"{cortex.n_cells:,}"
)

print(
    f"Cortex bounds    : "
    f"{cortex.bounds}"
)


# ============================================================
# 4. Load P=2500 cortical source candidates
# ============================================================

print("\n" + "=" * 78)
print("LOAD P=2500 SOURCE SPACE")
print("=" * 78)

sources = pd.read_csv(
    SOURCE_PATH
)

print("\nSource-space columns:")
print(
    list(sources.columns)
)


# ============================================================
# 5. Identify MNI coordinate columns
#
# The source-space CSV was generated from the validated
# 25k cortical master representation. We support the likely
# coordinate-column naming conventions explicitly.
# ============================================================

coordinate_options = [
    (
        "mni152_r",
        "mni152_a",
        "mni152_s",
    ),
    (
        "x_mni_mm",
        "y_mni_mm",
        "z_mni_mm",
    ),
    (
        "x",
        "y",
        "z",
    ),
]

source_coord_columns = None

for candidate in coordinate_options:

    if all(
        col in sources.columns
        for col in candidate
    ):
        source_coord_columns = candidate
        break


if source_coord_columns is None:

    raise RuntimeError(
        "\nCould not identify source coordinate columns.\n"
        f"Available columns:\n{list(sources.columns)}"
    )


print(
    "\nUsing source coordinate columns:"
)

print(
    source_coord_columns
)

source_xyz_mm = (
    sources[
        list(source_coord_columns)
    ]
    .to_numpy(dtype=float)
)

if not np.isfinite(
    source_xyz_mm
).all():

    raise RuntimeError(
        "Non-finite source coordinates detected."
    )


print(
    f"\nSource locations : "
    f"{len(source_xyz_mm):,}"
)

print(
    "Source coordinate bounds [mm]:"
)

print(
    f"  x : "
    f"{source_xyz_mm[:, 0].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 0].max():.3f}"
)

print(
    f"  y : "
    f"{source_xyz_mm[:, 1].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 1].max():.3f}"
)

print(
    f"  z : "
    f"{source_xyz_mm[:, 2].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 2].max():.3f}"
)


# ============================================================
# 6. Hemisphere information, if available
# ============================================================

hemisphere_column = None

for candidate in [
    "hemisphere",
    "hemi",
]:

    if candidate in sources.columns:
        hemisphere_column = candidate
        break


if hemisphere_column is not None:

    hemisphere_values = (
        sources[
            hemisphere_column
        ]
        .astype(str)
        .str.upper()
        .to_numpy()
    )

else:

    # Safe visualization fallback based only on physical
    # left/right MNI x coordinate.
    hemisphere_values = np.where(
        source_xyz_mm[:, 0] < 0,
        "LH",
        "RH",
    )


lh_mask = np.array(
    [
        value.startswith("L")
        for value in hemisphere_values
    ]
)

rh_mask = ~lh_mask

print(
    f"\nLH sources : "
    f"{lh_mask.sum():,}"
)

print(
    f"RH sources : "
    f"{rh_mask.sum():,}"
)


# ============================================================
# 7. Load ORIGINAL CapTrak sensor geometry
#
# Important:
# We intentionally do NOT use the registered MNI coordinates
# as the primary electrode geometry here.
#
# We load the original HEAD-frame coordinates and transform
# them using the saved FIF transform.
# ============================================================

print("\n" + "=" * 78)
print("LOAD ORIGINAL CAPTRAK ELECTRODES")
print("=" * 78)

captrak = pd.read_csv(
    CAPTRAK_PATH
)

required_captrak_columns = {
    "channel",
    "x",
    "y",
    "z",
}

if not required_captrak_columns.issubset(
    captrak.columns
):

    raise RuntimeError(
        "CapTrak file is missing required columns."
    )


channel_names = (
    captrak["channel"]
    .astype(str)
    .tolist()
)

head_xyz_m = (
    captrak[
        ["x", "y", "z"]
    ]
    .to_numpy(dtype=float)
)

if not np.isfinite(
    head_xyz_m
).all():

    raise RuntimeError(
        "Non-finite CapTrak coordinates detected."
    )


print(
    f"\nElectrodes : "
    f"{len(channel_names):,}"
)

print(
    "Input frame : HEAD / CapTrak"
)

print(
    "Input units : meters"
)


# ============================================================
# 8. Load saved HEAD -> MRI transform
# ============================================================

print("\n" + "=" * 78)
print("LOAD HEAD -> MRI TRANSFORM")
print("=" * 78)

head_mri_trans = mne.read_trans(
    TRANS_PATH
)

print(
    "\nLoaded transform:"
)

print(
    head_mri_trans
)

T = head_mri_trans[
    "trans"
]

if T.shape != (4, 4):

    raise RuntimeError(
        "Unexpected transform matrix shape."
    )


# ============================================================
# 9. Apply saved FIF transform
#
# Input:
#     HEAD coordinates [m]
#
# Output:
#     MRI coordinates [m]
#
# PyVista anatomy is in millimeters, so convert transformed
# coordinates to mm afterward.
# ============================================================

homogeneous_head = np.column_stack(
    [
        head_xyz_m,
        np.ones(
            len(head_xyz_m),
            dtype=float,
        ),
    ]
)

electrode_mri_m = (
    T
    @ homogeneous_head.T
).T[:, :3]

electrode_mri_mm = (
    electrode_mri_m
    * 1000.0
)


print(
    "\nTransformed electrode bounds [mm]:"
)

print(
    f"  x : "
    f"{electrode_mri_mm[:, 0].min():.3f} "
    f"to "
    f"{electrode_mri_mm[:, 0].max():.3f}"
)

print(
    f"  y : "
    f"{electrode_mri_mm[:, 1].min():.3f} "
    f"to "
    f"{electrode_mri_mm[:, 1].max():.3f}"
)

print(
    f"  z : "
    f"{electrode_mri_mm[:, 2].min():.3f} "
    f"to "
    f"{electrode_mri_mm[:, 2].max():.3f}"
)


# ============================================================
# 10. Independent comparison against previously registered
#     MNI coordinates
# ============================================================

registered = pd.read_csv(
    REGISTERED_PATH
)

required_registered_columns = {
    "channel",
    "x_mni_mm",
    "y_mni_mm",
    "z_mni_mm",
}

if not required_registered_columns.issubset(
    registered.columns
):

    raise RuntimeError(
        "Registered electrode file is incomplete."
    )


registered_names = (
    registered["channel"]
    .astype(str)
    .tolist()
)

if registered_names != channel_names:

    raise RuntimeError(
        "Channel ordering differs between "
        "CapTrak and registered files."
    )


saved_mni_mm = (
    registered[
        [
            "x_mni_mm",
            "y_mni_mm",
            "z_mni_mm",
        ]
    ]
    .to_numpy(dtype=float)
)


transform_errors_mm = np.linalg.norm(
    electrode_mri_mm
    - saved_mni_mm,
    axis=1,
)


print("\n" + "=" * 78)
print("TRANSFORM CONSISTENCY CHECK")
print("=" * 78)

print(
    f"\nMean difference : "
    f"{transform_errors_mm.mean():.9f} mm"
)

print(
    f"Max difference  : "
    f"{transform_errors_mm.max():.9f} mm"
)


# ============================================================
# 11. Electrode-to-scalp distance
#
# Compute nearest surface-vertex distance as a simple
# diagnostic.
#
# Important:
# This is NOT the exact point-to-triangle surface distance.
# It is a nearest-vertex QC measure.
# ============================================================

print("\n" + "=" * 78)
print("ELECTRODE -> OUTER-SKIN DISTANCE")
print("=" * 78)

skin_points = np.asarray(
    outer_skin.points,
    dtype=float,
)

skin_tree = pv.PolyData(
    skin_points
)

nearest_skin_ids = []

nearest_skin_distances_mm = []

for point in electrode_mri_mm:

    idx = skin_tree.find_closest_point(
        point
    )

    nearest_skin_ids.append(
        idx
    )

    distance = np.linalg.norm(
        point
        - skin_points[idx]
    )

    nearest_skin_distances_mm.append(
        distance
    )


nearest_skin_distances_mm = np.asarray(
    nearest_skin_distances_mm,
    dtype=float,
)


print(
    f"\nMinimum : "
    f"{nearest_skin_distances_mm.min():.3f} mm"
)

print(
    f"Median  : "
    f"{np.median(nearest_skin_distances_mm):.3f} mm"
)

print(
    f"Mean    : "
    f"{nearest_skin_distances_mm.mean():.3f} mm"
)

print(
    f"95th    : "
    f"{np.percentile(nearest_skin_distances_mm, 95):.3f} mm"
)

print(
    f"Maximum : "
    f"{nearest_skin_distances_mm.max():.3f} mm"
)


# ============================================================
# 12. Show electrodes with largest scalp distances
# ============================================================

worst = np.argsort(
    nearest_skin_distances_mm
)[-10:][::-1]

print(
    "\n10 largest electrode -> skin "
    "nearest-vertex distances:"
)

for idx in worst:

    print(
        f"  {channel_names[idx]:>7s} : "
        f"{nearest_skin_distances_mm[idx]:.3f} mm"
    )


# ============================================================
# 13. Create PyVista point clouds
# ============================================================

electrode_cloud = pv.PolyData(
    electrode_mri_mm
)

lh_source_cloud = pv.PolyData(
    source_xyz_mm[
        lh_mask
    ]
)

rh_source_cloud = pv.PolyData(
    source_xyz_mm[
        rh_mask
    ]
)


# ============================================================
# 14. Visualization + permanent QC records
# ============================================================

print("\n" + "=" * 78)
print("CREATING FORWARD-GEOMETRY QC VISUALIZATION")
print("=" * 78)


# ============================================================
# 14.1 Output directory
# ============================================================

QC_DIR = (
    BEM_ROOT
    / "forward_geometry_qc"
)

QC_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

print(
    f"\nQC images will be saved to:\n"
    f"{QC_DIR}"
)


# ============================================================
# 14.2 Create point clouds
# ============================================================

electrode_cloud = pv.PolyData(
    electrode_mri_mm
)

lh_source_cloud = pv.PolyData(
    source_xyz_mm[
        lh_mask
    ]
)

rh_source_cloud = pv.PolyData(
    source_xyz_mm[
        rh_mask
    ]
)


# ============================================================
# 14.3 Selected electrode labels
# ============================================================

important_channels = [
    "Fp1",
    "Fp2",
    "F7",
    "F8",
    "F3",
    "F4",
    "Fz",
    "C3",
    "C4",
    "Cz",
    "P3",
    "P4",
    "Pz",
    "O1",
    "O2",
]

label_points = []
label_names = []

for name in important_channels:

    if name not in channel_names:
        continue

    idx = channel_names.index(
        name
    )

    label_points.append(
        electrode_mri_mm[idx]
    )

    label_names.append(
        name
    )

label_points = np.asarray(
    label_points,
    dtype=float,
)


# ============================================================
# 14.4 Function to build identical scene
#
# Every saved view uses the SAME geometry and rendering
# settings. Only the camera position changes.
# ============================================================

def build_scene(
    off_screen=False,
    show_labels=True,
):

    plotter = pv.Plotter(
        window_size=(
            1800,
            1400,
        ),
        off_screen=off_screen,
    )

    # --------------------------------------------------------
    # Outer skin
    # --------------------------------------------------------

    plotter.add_mesh(
        outer_skin,
        color="lightgray",
        opacity=0.10,
        show_edges=False,
        label="Outer skin",
    )

    # --------------------------------------------------------
    # Outer skull
    # --------------------------------------------------------

    plotter.add_mesh(
        outer_skull,
        color="gold",
        opacity=0.12,
        show_edges=False,
        label="Outer skull",
    )

    # --------------------------------------------------------
    # Inner skull
    # --------------------------------------------------------

    plotter.add_mesh(
        inner_skull,
        color="dodgerblue",
        opacity=0.16,
        show_edges=False,
        label="Inner skull",
    )

    # --------------------------------------------------------
    # High-resolution physical cortex
    # --------------------------------------------------------

    plotter.add_mesh(
        cortex,
        color="lightcoral",
        opacity=0.30,
        show_edges=False,
        label="Physical cortex",
    )

    # --------------------------------------------------------
    # P=2500 left-hemisphere sources
    # --------------------------------------------------------

    plotter.add_mesh(
        lh_source_cloud,
        color="crimson",
        render_points_as_spheres=True,
        point_size=6,
        label="P=2500 LH sources",
    )

    # --------------------------------------------------------
    # P=2500 right-hemisphere sources
    # --------------------------------------------------------

    plotter.add_mesh(
        rh_source_cloud,
        color="royalblue",
        render_points_as_spheres=True,
        point_size=6,
        label="P=2500 RH sources",
    )

    # --------------------------------------------------------
    # 128 transformed EEG electrodes
    # --------------------------------------------------------

    plotter.add_mesh(
        electrode_cloud,
        color="limegreen",
        render_points_as_spheres=True,
        point_size=11,
        label="128 EEG electrodes",
    )

    # --------------------------------------------------------
    # Selected electrode labels
    # --------------------------------------------------------

    if (
        show_labels
        and len(label_points) > 0
    ):

        plotter.add_point_labels(
            label_points,
            label_names,
            point_size=5,
            font_size=10,
            shape=None,
            always_visible=True,
        )

    # --------------------------------------------------------
    # Scene settings
    # --------------------------------------------------------

    plotter.add_axes()

    plotter.add_legend(
        bcolor="white",
    )

    plotter.show_grid()

    plotter.enable_anti_aliasing(
        "ssaa"
    )

    return plotter


# ============================================================
# 15. Function to save a standardized camera view
# ============================================================

def save_view(
    filename,
    camera_position,
    show_labels=True,
):

    output_path = (
        QC_DIR
        / filename
    )

    plotter = build_scene(
        off_screen=True,
        show_labels=show_labels,
    )

    # --------------------------------------------------------
    # Camera orientation
    # --------------------------------------------------------

    if camera_position == "iso":

        plotter.camera_position = "iso"

    elif camera_position == "xy":

        plotter.view_xy()

    elif camera_position == "xz":

        plotter.view_xz()

    elif camera_position == "yz":

        plotter.view_yz()

    else:

        raise ValueError(
            f"Unknown camera position: "
            f"{camera_position}"
        )

    plotter.reset_camera()

    # --------------------------------------------------------
    # Render before screenshot
    # --------------------------------------------------------

    plotter.render()

    plotter.screenshot(
        str(output_path),
        scale=2,
    )

    plotter.close()

    print(
        f"PASS  saved {output_path.name}"
    )

    return output_path


# ============================================================
# 16. Save standardized QC views
# ============================================================

print("\n" + "=" * 78)
print("SAVE STANDARDIZED QC IMAGES")
print("=" * 78)

saved_images = []


# ------------------------------------------------------------
# 16.1 Isometric view
#
# Closest to the view we are currently inspecting.
# ------------------------------------------------------------

saved_images.append(
    save_view(
        filename=(
            "forward_geometry_qc_isometric.png"
        ),
        camera_position="iso",
        show_labels=True,
    )
)


# ------------------------------------------------------------
# 16.2 Superior / top view
# ------------------------------------------------------------

saved_images.append(
    save_view(
        filename=(
            "forward_geometry_qc_superior.png"
        ),
        camera_position="xy",
        show_labels=True,
    )
)


# ------------------------------------------------------------
# 16.3 Anterior/posterior-oriented view
# ------------------------------------------------------------

saved_images.append(
    save_view(
        filename=(
            "forward_geometry_qc_coronal.png"
        ),
        camera_position="xz",
        show_labels=True,
    )
)


# ------------------------------------------------------------
# 16.4 Lateral view
# ------------------------------------------------------------

saved_images.append(
    save_view(
        filename=(
            "forward_geometry_qc_lateral.png"
        ),
        camera_position="yz",
        show_labels=True,
    )
)


# ============================================================
# 17. Save a clean isometric image without electrode labels
#
# This is useful later for a manuscript, presentation, or
# supplementary figure where labels may make the image too
# crowded.
# ============================================================

saved_images.append(
    save_view(
        filename=(
            "forward_geometry_qc_isometric_clean.png"
        ),
        camera_position="iso",
        show_labels=False,
    )
)


# ============================================================
# 18. Save numerical QC table
#
# Preserve each electrode's transformed MRI/MNI coordinate
# and its nearest outer-skin vertex distance.
# ============================================================

qc_table = pd.DataFrame(
    {
        "channel": channel_names,

        "head_x_m":
            head_xyz_m[:, 0],

        "head_y_m":
            head_xyz_m[:, 1],

        "head_z_m":
            head_xyz_m[:, 2],

        "mri_x_mm":
            electrode_mri_mm[:, 0],

        "mri_y_mm":
            electrode_mri_mm[:, 1],

        "mri_z_mm":
            electrode_mri_mm[:, 2],

        "transform_reconstruction_error_mm":
            transform_errors_mm,

        "nearest_skin_vertex_distance_mm":
            nearest_skin_distances_mm,
    }
)

QC_TABLE_PATH = (
    QC_DIR
    / "forward_geometry_electrode_qc.csv"
)

qc_table.to_csv(
    QC_TABLE_PATH,
    index=False,
)

print(
    f"\nPASS  saved "
    f"{QC_TABLE_PATH.name}"
)


# ============================================================
# 19. Save a text summary for provenance
# ============================================================

QC_SUMMARY_PATH = (
    QC_DIR
    / "forward_geometry_qc_summary.txt"
)

with open(
    QC_SUMMARY_PATH,
    "w",
    encoding="utf-8",
) as f:

    f.write(
        "FORWARD-MODEL GEOMETRY QC\n"
    )

    f.write(
        "=" * 78
        + "\n\n"
    )

    f.write(
        "Purpose\n"
        "-------\n"
    )

    f.write(
        "Final geometric consistency check before "
        "construction of the EEG forward operator.\n\n"
    )

    f.write(
        "Geometry included\n"
        "-----------------\n"
    )

    f.write(
        "Outer skin: ico4 BEM\n"
    )

    f.write(
        "Outer skull: ico4 BEM\n"
    )

    f.write(
        "Inner skull: ico4 BEM\n"
    )

    f.write(
        "Cortex: high-resolution physical "
        "ICBM152/MNI152 cortex\n"
    )

    f.write(
        "Source candidates: P=2500\n"
    )

    f.write(
        "EEG electrodes: 128 original CapTrak "
        "positions transformed HEAD -> MRI\n\n"
    )

    f.write(
        "Transform\n"
        "---------\n"
    )

    f.write(
        f"{TRANS_PATH}\n\n"
    )

    f.write(
        "Transform consistency\n"
        "---------------------\n"
    )

    f.write(
        f"Mean reconstruction difference: "
        f"{transform_errors_mm.mean():.12e} mm\n"
    )

    f.write(
        f"Maximum reconstruction difference: "
        f"{transform_errors_mm.max():.12e} mm\n\n"
    )

    f.write(
        "Electrode -> outer-skin nearest-vertex "
        "distance\n"
    )

    f.write(
        "-----------------------------------------\n"
    )

    f.write(
        f"Minimum: "
        f"{nearest_skin_distances_mm.min():.6f} mm\n"
    )

    f.write(
        f"Median: "
        f"{np.median(nearest_skin_distances_mm):.6f} mm\n"
    )

    f.write(
        f"Mean: "
        f"{nearest_skin_distances_mm.mean():.6f} mm\n"
    )

    f.write(
        f"95th percentile: "
        f"{np.percentile(nearest_skin_distances_mm, 95):.6f} mm\n"
    )

    f.write(
        f"Maximum: "
        f"{nearest_skin_distances_mm.max():.6f} mm\n\n"
    )

    f.write(
        "Important interpretation\n"
        "------------------------\n"
    )

    f.write(
        "Electrode-to-skin distances are "
        "nearest-VERTEX diagnostics and are not "
        "exact point-to-triangle surface distances.\n"
    )

    f.write(
        "No electrode snapping was performed.\n"
    )

print(
    f"PASS  saved "
    f"{QC_SUMMARY_PATH.name}"
)


# ============================================================
# 20. Open interactive visualization
#
# The automatically saved images above are the permanent
# records. This interactive window can now be rotated and
# inspected freely without affecting those records.
# ============================================================

print("\n" + "=" * 78)
print("OPENING INTERACTIVE VISUALIZATION")
print("=" * 78)

print(
    "\nInspect:"
)

print(
    "  1. electrodes follow the outer scalp"
)

print(
    "  2. no gross translation or rotation mismatch"
)

print(
    "  3. cortex is enclosed by inner skull"
)

print(
    "  4. inner skull is enclosed by outer skull"
)

print(
    "  5. outer skull is enclosed by outer skin"
)

print(
    "  6. P=2500 sources follow cortical geometry"
)


plotter = build_scene(
    off_screen=False,
    show_labels=True,
)

plotter.camera_position = "iso"

plotter.show()


# ============================================================
# 21. Final terminal summary
# ============================================================

print("\n" + "=" * 78)
print("VISUALIZATION AND QC RECORD COMPLETE")
print("=" * 78)

print(
    f"""
Geometry shown:

    Outer skin
    Outer skull
    Inner skull
    High-resolution physical cortex
    P=2500 cortical sources
    128 transformed EEG electrodes

Electrode transform:

    HEAD -> MRI

    {TRANS_PATH}

Transform consistency:

    mean difference =
        {transform_errors_mm.mean():.12e} mm

    max difference =
        {transform_errors_mm.max():.12e} mm

Electrode -> skin nearest-vertex distance:

    minimum =
        {nearest_skin_distances_mm.min():.3f} mm

    median =
        {np.median(nearest_skin_distances_mm):.3f} mm

    mean =
        {nearest_skin_distances_mm.mean():.3f} mm

    95th percentile =
        {np.percentile(nearest_skin_distances_mm, 95):.3f} mm

    maximum =
        {nearest_skin_distances_mm.max():.3f} mm

Permanent QC directory:

    {QC_DIR}

Saved records:

    forward_geometry_qc_isometric.png
    forward_geometry_qc_superior.png
    forward_geometry_qc_coronal.png
    forward_geometry_qc_lateral.png
    forward_geometry_qc_isometric_clean.png
    forward_geometry_electrode_qc.csv
    forward_geometry_qc_summary.txt

NOTE:

    Electrode-to-skin values are nearest-VERTEX
    diagnostics, not exact point-to-triangle distances.

    No electrode snapping was performed.
"""
)

print("=" * 78)