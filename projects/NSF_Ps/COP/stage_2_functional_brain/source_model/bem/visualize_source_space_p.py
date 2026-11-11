# from pathlib import Path

# import mne
# import numpy as np
# import pyvista as pv


# # ============================================================
# # Configuration
# # ============================================================

# P = 2500

# BEM_ROOT = Path(__file__).resolve().parent
# COP_ROOT = BEM_ROOT.parents[2]

# SRC_PATH = BEM_ROOT / f"icbm152-discrete-p{P}-src.fif"

# INNER_SKULL_PATH = (
#     BEM_ROOT
#     / "surfaces_mne_ico4"
#     / "inner_skull_5120.vtk"
# )

# OUTER_SKULL_PATH = (
#     BEM_ROOT
#     / "surfaces_mne_ico4"
#     / "outer_skull_5120.vtk"
# )

# OUTER_SKIN_PATH = (
#     BEM_ROOT
#     / "surfaces_mne_ico4"
#     / "outer_skin_5120.vtk"
# )

# CORTEX_PATH = (
#     COP_ROOT
#     / "hm_icbm152"
#     / "cortex_pial_high_mni152.obj"
# )

# QC_DIR = (
#     BEM_ROOT
#     / "source_space_qc"
#     / f"p{P}"
# )

# QC_DIR.mkdir(
#     parents=True,
#     exist_ok=True,
# )


# # ============================================================
# # Header
# # ============================================================

# print("=" * 78)
# print(f"MNE SOURCE-SPACE VISUALIZATION: P={P}")
# print("=" * 78)


# # ============================================================
# # Check files
# # ============================================================

# required_files = [
#     SRC_PATH,
#     INNER_SKULL_PATH,
#     OUTER_SKULL_PATH,
#     OUTER_SKIN_PATH,
#     CORTEX_PATH,
# ]

# for path in required_files:

#     if not path.exists():
#         raise FileNotFoundError(
#             f"Missing required file:\n{path}"
#         )

#     print(f"PASS  {path.name}")


# # ============================================================
# # Load MNE source space
# # ============================================================

# print("\n" + "=" * 78)
# print("LOAD SAVED MNE SOURCE SPACE")
# print("=" * 78)

# src = mne.read_source_spaces(
#     SRC_PATH,
#     verbose=False,
# )

# if len(src) != 1:
#     raise RuntimeError(
#         f"Expected 1 discrete source space, found {len(src)}."
#     )

# src0 = src[0]

# print(f"\nType        : {src0['type']}")
# print(f"Total points: {src0['np']:,}")
# print(f"Used points : {src0['nuse']:,}")
# print(f"Coord frame : {src0['coord_frame']}")

# if src0["type"] != "discrete":
#     raise RuntimeError(
#         "Saved source space is not discrete."
#     )

# if src0["nuse"] != P:
#     raise RuntimeError(
#         f"Expected {P:,} active sources, "
#         f"found {src0['nuse']:,}."
#     )


# # ============================================================
# # Extract ACTIVE source positions
# #
# # MNE coordinates are meters.
# # PyVista anatomy is millimeters.
# # ============================================================

# vertno = np.asarray(
#     src0["vertno"],
#     dtype=int,
# )

# source_xyz_m = np.asarray(
#     src0["rr"],
#     dtype=float,
# )[vertno]

# source_xyz_mm = (
#     source_xyz_m
#     * 1000.0
# )

# if not np.isfinite(source_xyz_mm).all():
#     raise RuntimeError(
#         "Non-finite source coordinates detected."
#     )

# print("\nSource bounds [mm]:")

# print(
#     f"  x : {source_xyz_mm[:, 0].min():.3f} "
#     f"to {source_xyz_mm[:, 0].max():.3f}"
# )

# print(
#     f"  y : {source_xyz_mm[:, 1].min():.3f} "
#     f"to {source_xyz_mm[:, 1].max():.3f}"
# )

# print(
#     f"  z : {source_xyz_mm[:, 2].min():.3f} "
#     f"to {source_xyz_mm[:, 2].max():.3f}"
# )


# # ============================================================
# # Hemisphere split
# #
# # Because this candidate set was generated from the master
# # cortical table, left/right can be determined geometrically
# # for visualization using MNI x.
# #
# # This is ONLY for visualization coloring.
# # It does not alter source metadata.
# # ============================================================

# lh_mask = source_xyz_mm[:, 0] < 0
# rh_mask = ~lh_mask

# lh_xyz = source_xyz_mm[lh_mask]
# rh_xyz = source_xyz_mm[rh_mask]

# print("\nVisualization hemisphere split:")
# print(f"  LH : {len(lh_xyz):,}")
# print(f"  RH : {len(rh_xyz):,}")

# print(
#     "\nNOTE: hemisphere coloring here uses MNI x only "
#     "for visualization."
# )


# # ============================================================
# # Load anatomy
# # ============================================================

# print("\n" + "=" * 78)
# print("LOAD ANATOMICAL GEOMETRY")
# print("=" * 78)

# inner_skull = pv.read(
#     INNER_SKULL_PATH
# )

# outer_skull = pv.read(
#     OUTER_SKULL_PATH
# )

# outer_skin = pv.read(
#     OUTER_SKIN_PATH
# )

# cortex = pv.read(
#     CORTEX_PATH
# )

# print(
#     f"\nInner skull : "
#     f"{inner_skull.n_points:,} vertices, "
#     f"{inner_skull.n_cells:,} triangles"
# )

# print(
#     f"Outer skull : "
#     f"{outer_skull.n_points:,} vertices, "
#     f"{outer_skull.n_cells:,} triangles"
# )

# print(
#     f"Outer skin  : "
#     f"{outer_skin.n_points:,} vertices, "
#     f"{outer_skin.n_cells:,} triangles"
# )

# print(
#     f"Cortex      : "
#     f"{cortex.n_points:,} vertices, "
#     f"{cortex.n_cells:,} triangles"
# )


# # ============================================================
# # Independent containment check
# # ============================================================

# print("\n" + "=" * 78)
# print("FIF SOURCE -> INNER-SKULL CONTAINMENT")
# print("=" * 78)

# source_cloud = pv.PolyData(
#     source_xyz_mm
# )

# # Newer PyVista versions prefer select_interior_points.
# # Fall back to select_enclosed_points if needed.
# if hasattr(
#     source_cloud,
#     "select_interior_points",
# ):

#     selection = (
#         source_cloud
#         .select_interior_points(
#             inner_skull,
#         )
#     )

# else:

#     selection = (
#         source_cloud
#         .select_enclosed_points(
#             inner_skull,
#             tolerance=0.0,
#             check_surface=True,
#         )
#     )


# # Different PyVista versions may use different array names.
# possible_arrays = [
#     "SelectedPoints",
#     "selected_points",
#     "Inside",
#     "inside",
# ]

# inside = None

# for name in possible_arrays:

#     if name in selection.point_data:
#         inside = np.asarray(
#             selection[name]
#         ).astype(bool)
#         break


# if inside is None:

#     print(
#         "\nWARNING:"
#     )

#     print(
#         "Could not identify the containment mask "
#         "returned by this PyVista version."
#     )

#     print(
#         "Skipping numerical containment in this "
#         "visualization script."
#     )

# else:

#     n_inside = int(
#         inside.sum()
#     )

#     n_outside = int(
#         (~inside).sum()
#     )

#     print(
#         f"\nInside inner skull : "
#         f"{n_inside:,} / {P:,}"
#     )

#     print(
#         f"Outside inner skull: "
#         f"{n_outside:,}"
#     )

#     if n_outside != 0:

#         raise RuntimeError(
#             f"{n_outside} saved MNE sources are "
#             "outside the inner skull."
#         )

#     print(
#         "\nSaved FIF source containment: PASS"
#     )


# # ============================================================
# # Create PyVista source clouds
# # ============================================================

# lh_cloud = pv.PolyData(
#     lh_xyz
# )

# rh_cloud = pv.PolyData(
#     rh_xyz
# )


# # ============================================================
# # Scene builder
# # ============================================================

# def build_scene(
#     off_screen=False,
# ):

#     plotter = pv.Plotter(
#         off_screen=off_screen,
#         window_size=(1800, 1400),
#     )

#     # --------------------------------------------------------
#     # Outer skin
#     # --------------------------------------------------------

#     plotter.add_mesh(
#         outer_skin,
#         color="lightgray",
#         opacity=0.08,
#         smooth_shading=True,
#         label="Outer skin",
#     )

#     # --------------------------------------------------------
#     # Outer skull
#     # --------------------------------------------------------

#     plotter.add_mesh(
#         outer_skull,
#         color="khaki",
#         opacity=0.10,
#         smooth_shading=True,
#         label="Outer skull",
#     )

#     # --------------------------------------------------------
#     # Inner skull
#     # --------------------------------------------------------

#     plotter.add_mesh(
#         inner_skull,
#         color="lightskyblue",
#         opacity=0.15,
#         smooth_shading=True,
#         label="Inner skull",
#     )

#     # --------------------------------------------------------
#     # Physical high-resolution cortex
#     # --------------------------------------------------------

#     plotter.add_mesh(
#         cortex,
#         color="mistyrose",
#         opacity=0.38,
#         smooth_shading=True,
#         label="Physical cortex",
#     )

#     # --------------------------------------------------------
#     # LEFT source points
#     # --------------------------------------------------------

#     plotter.add_mesh(
#         lh_cloud,
#         color="royalblue",
#         point_size=8,
#         render_points_as_spheres=True,
#         label=f"LH sources ({len(lh_xyz):,})",
#     )

#     # --------------------------------------------------------
#     # RIGHT source points
#     # --------------------------------------------------------

#     plotter.add_mesh(
#         rh_cloud,
#         color="crimson",
#         point_size=8,
#         render_points_as_spheres=True,
#         label=f"RH sources ({len(rh_xyz):,})",
#     )

#     plotter.add_legend(
#         bcolor="white",
#         face=None,
#         size=(0.25, 0.20),
#     )

#     plotter.add_axes()

#     return plotter


# # ============================================================
# # Save standardized views
# # ============================================================

# print("\n" + "=" * 78)
# print("SAVE SOURCE-SPACE QC IMAGES")
# print("=" * 78)

# print(
#     f"\nQC directory:\n{QC_DIR}"
# )


# views = {
#     "isometric": "iso",
#     "superior": "xy",
#     "coronal": "xz",
#     "lateral": "yz",
# }


# for name, view in views.items():

#     plotter = build_scene(
#         off_screen=True
#     )

#     if view == "iso":

#         plotter.view_isometric()

#     elif view == "xy":

#         plotter.view_xy()

#     elif view == "xz":

#         plotter.view_xz()

#     elif view == "yz":

#         plotter.view_yz()

#     plotter.reset_camera()

#     output_path = (
#         QC_DIR
#         / f"source_space_p{P}_{name}.png"
#     )

#     plotter.screenshot(
#         output_path,
#         scale=2,
#     )

#     plotter.close()

#     print(
#         f"PASS  saved {output_path.name}"
#     )


# # ============================================================
# # Save clean isometric view
# # ============================================================

# plotter = pv.Plotter(
#     off_screen=True,
#     window_size=(1800, 1400),
# )

# plotter.add_mesh(
#     inner_skull,
#     color="lightskyblue",
#     opacity=0.10,
#     smooth_shading=True,
# )

# plotter.add_mesh(
#     cortex,
#     color="mistyrose",
#     opacity=0.32,
#     smooth_shading=True,
# )

# plotter.add_mesh(
#     lh_cloud,
#     color="royalblue",
#     point_size=8,
#     render_points_as_spheres=True,
# )

# plotter.add_mesh(
#     rh_cloud,
#     color="crimson",
#     point_size=8,
#     render_points_as_spheres=True,
# )

# plotter.view_isometric()
# plotter.reset_camera()

# clean_path = (
#     QC_DIR
#     / f"source_space_p{P}_isometric_clean.png"
# )

# plotter.screenshot(
#     clean_path,
#     scale=2,
# )

# plotter.close()

# print(
#     f"PASS  saved {clean_path.name}"
# )


# # ============================================================
# # Save QC summary
# # ============================================================

# summary_path = (
#     QC_DIR
#     / f"source_space_p{P}_qc_summary.txt"
# )

# with open(
#     summary_path,
#     "w",
#     encoding="utf-8",
# ) as f:

#     f.write(
#         "MNE DISCRETE SOURCE-SPACE VISUAL QC\n"
#     )

#     f.write(
#         "=" * 60 + "\n\n"
#     )

#     f.write(
#         f"Density: P={P:,}\n"
#     )

#     f.write(
#         f"Source FIF: {SRC_PATH}\n\n"
#     )

#     f.write(
#         f"MNE type: {src0['type']}\n"
#     )

#     f.write(
#         f"MNE nuse: {src0['nuse']:,}\n"
#     )

#     f.write(
#         f"MNE coordinate frame: "
#         f"{src0['coord_frame']}\n\n"
#     )

#     f.write(
#         "Source bounds [mm]:\n"
#     )

#     f.write(
#         f"x: {source_xyz_mm[:,0].min():.3f} "
#         f"to {source_xyz_mm[:,0].max():.3f}\n"
#     )

#     f.write(
#         f"y: {source_xyz_mm[:,1].min():.3f} "
#         f"to {source_xyz_mm[:,1].max():.3f}\n"
#     )

#     f.write(
#         f"z: {source_xyz_mm[:,2].min():.3f} "
#         f"to {source_xyz_mm[:,2].max():.3f}\n\n"
#     )

#     f.write(
#         f"Visualization LH count: "
#         f"{len(lh_xyz):,}\n"
#     )

#     f.write(
#         f"Visualization RH count: "
#         f"{len(rh_xyz):,}\n\n"
#     )

#     if inside is not None:

#         f.write(
#             f"Inside inner skull: "
#             f"{n_inside:,}/{P:,}\n"
#         )

#         f.write(
#             f"Outside inner skull: "
#             f"{n_outside:,}\n\n"
#         )

#     f.write(
#         "NOTE:\n"
#     )

#     f.write(
#         "LH/RH coloring in this visualization "
#         "uses the sign of the MNI x-coordinate "
#         "only for visual QC.\n"
#     )

#     f.write(
#         "The canonical hemisphere and cortical "
#         "metadata remain in the companion source "
#         "mapping CSV.\n"
#     )


# print(
#     f"PASS  saved {summary_path.name}"
# )


# # ============================================================
# # Interactive visualization
# # ============================================================

# print("\n" + "=" * 78)
# print("OPENING INTERACTIVE VISUALIZATION")
# print("=" * 78)

# print(
#     """
# Inspect:

#   1. sources follow the physical cortical sheet
#   2. no global translation
#   3. no global rotation
#   4. no left/right reflection
#   5. sources remain enclosed by inner skull
#   6. no isolated or obviously displaced source clusters
# """
# )

# plotter = build_scene(
#     off_screen=False
# )

# plotter.view_isometric()
# plotter.reset_camera()

# plotter.show()


# print("\n" + "=" * 78)
# print(f"MNE SOURCE-SPACE VISUALIZATION P={P}: COMPLETE")
# print("=" * 78)



from pathlib import Path

import mne
import numpy as np
import pyvista as pv


# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_DENSITIES = [
    5000,
    10000,
]

BEM_ROOT = Path(__file__).resolve().parent
COP_ROOT = BEM_ROOT.parents[2]

INNER_SKULL_PATH = (
    BEM_ROOT
    / "surfaces_mne_ico4"
    / "inner_skull_5120.vtk"
)

OUTER_SKULL_PATH = (
    BEM_ROOT
    / "surfaces_mne_ico4"
    / "outer_skull_5120.vtk"
)

OUTER_SKIN_PATH = (
    BEM_ROOT
    / "surfaces_mne_ico4"
    / "outer_skin_5120.vtk"
)

CORTEX_PATH = (
    COP_ROOT
    / "hm_icbm152"
    / "cortex_pial_high_mni152.obj"
)


# ============================================================
# CHECK COMMON ANATOMICAL FILES
# ============================================================

print("=" * 78)
print("MNE SOURCE-SPACE FRONTAL VISUALIZATION")
print("=" * 78)

required_common_files = [
    INNER_SKULL_PATH,
    OUTER_SKULL_PATH,
    OUTER_SKIN_PATH,
    CORTEX_PATH,
]

for path in required_common_files:

    if not path.exists():
        raise FileNotFoundError(
            f"Missing required file:\n{path}"
        )

    print(f"PASS  {path.name}")


# ============================================================
# LOAD ANATOMY ONCE
# ============================================================

print("\n" + "=" * 78)
print("LOAD ANATOMICAL GEOMETRY")
print("=" * 78)

inner_skull = pv.read(
    INNER_SKULL_PATH
)

outer_skull = pv.read(
    OUTER_SKULL_PATH
)

outer_skin = pv.read(
    OUTER_SKIN_PATH
)

cortex = pv.read(
    CORTEX_PATH
)

print(
    f"\nInner skull : "
    f"{inner_skull.n_points:,} vertices, "
    f"{inner_skull.n_cells:,} triangles"
)

print(
    f"Outer skull : "
    f"{outer_skull.n_points:,} vertices, "
    f"{outer_skull.n_cells:,} triangles"
)

print(
    f"Outer skin  : "
    f"{outer_skin.n_points:,} vertices, "
    f"{outer_skin.n_cells:,} triangles"
)

print(
    f"Cortex      : "
    f"{cortex.n_points:,} vertices, "
    f"{cortex.n_cells:,} triangles"
)


# ============================================================
# PROCESS EACH SOURCE DENSITY
# ============================================================

for P in SOURCE_DENSITIES:

    print("\n" + "=" * 78)
    print(f"PROCESS SOURCE SPACE: P={P:,}")
    print("=" * 78)

    # --------------------------------------------------------
    # Paths
    # --------------------------------------------------------

    SRC_PATH = (
        BEM_ROOT
        / f"icbm152-discrete-p{P}-src.fif"
    )

    QC_DIR = (
        BEM_ROOT
        / "source_space_qc"
        / f"p{P}"
    )

    QC_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH = (
        QC_DIR
        / f"source_space_p{P}_frontal.png"
    )

    if not SRC_PATH.exists():
        raise FileNotFoundError(
            f"Missing source-space FIF:\n{SRC_PATH}"
        )

    print(
        f"\nSource FIF:\n{SRC_PATH}"
    )

    print(
        f"\nOutput image:\n{OUTPUT_PATH}"
    )


    # ========================================================
    # LOAD MNE SOURCE SPACE
    # ========================================================

    src = mne.read_source_spaces(
        SRC_PATH,
        verbose=False,
    )

    if len(src) != 1:
        raise RuntimeError(
            f"Expected 1 discrete source space, "
            f"found {len(src)}."
        )

    src0 = src[0]

    print(
        f"\nType        : {src0['type']}"
    )

    print(
        f"Total points: {src0['np']:,}"
    )

    print(
        f"Used points : {src0['nuse']:,}"
    )

    print(
        f"Coord frame : {src0['coord_frame']}"
    )

    if src0["type"] != "discrete":
        raise RuntimeError(
            "Saved source space is not discrete."
        )

    if src0["nuse"] != P:
        raise RuntimeError(
            f"Expected {P:,} active sources, "
            f"found {src0['nuse']:,}."
        )


    # ========================================================
    # EXTRACT ACTIVE SOURCE POSITIONS
    #
    # MNE = meters
    # PyVista anatomy = millimeters
    # ========================================================

    vertno = np.asarray(
        src0["vertno"],
        dtype=int,
    )

    source_xyz_m = np.asarray(
        src0["rr"],
        dtype=float,
    )[vertno]

    source_xyz_mm = (
        source_xyz_m
        * 1000.0
    )

    if not np.isfinite(
        source_xyz_mm
    ).all():

        raise RuntimeError(
            "Non-finite source coordinates detected."
        )


    # ========================================================
    # HEMISPHERE SPLIT
    #
    # Used only for visualization coloring.
    # ========================================================

    lh_mask = (
        source_xyz_mm[:, 0] < 0
    )

    rh_mask = ~lh_mask

    lh_xyz = source_xyz_mm[
        lh_mask
    ]

    rh_xyz = source_xyz_mm[
        rh_mask
    ]

    print(
        f"\nVisualization hemisphere split:"
    )

    print(
        f"  LH : {len(lh_xyz):,}"
    )

    print(
        f"  RH : {len(rh_xyz):,}"
    )


    # ========================================================
    # SOURCE CLOUDS
    # ========================================================

    lh_cloud = pv.PolyData(
        lh_xyz
    )

    rh_cloud = pv.PolyData(
        rh_xyz
    )


    # ========================================================
    # BUILD FRONTAL SCENE
    # ========================================================

    plotter = pv.Plotter(
        off_screen=True,
        window_size=(
            1800,
            1600,
        ),
    )


    # --------------------------------------------------------
    # Outer skin
    # --------------------------------------------------------

    plotter.add_mesh(
        outer_skin,
        color="lightgray",
        opacity=0.035,
        smooth_shading=True,
    )


    # --------------------------------------------------------
    # Outer skull
    # --------------------------------------------------------

    plotter.add_mesh(
        outer_skull,
        color="khaki",
        opacity=0.05,
        smooth_shading=True,
    )


    # --------------------------------------------------------
    # Inner skull
    # --------------------------------------------------------

    plotter.add_mesh(
        inner_skull,
        color="lightskyblue",
        opacity=0.10,
        smooth_shading=True,
    )


    # --------------------------------------------------------
    # High-resolution physical cortex
    # --------------------------------------------------------

    plotter.add_mesh(
        cortex,
        color="mistyrose",
        opacity=0.32,
        smooth_shading=True,
    )


    # --------------------------------------------------------
    # LEFT sources
    # --------------------------------------------------------

    plotter.add_mesh(
        lh_cloud,
        color="royalblue",
        point_size=7,
        render_points_as_spheres=True,
        label=f"LH ({len(lh_xyz):,})",
    )


    # --------------------------------------------------------
    # RIGHT sources
    # --------------------------------------------------------

    plotter.add_mesh(
        rh_cloud,
        color="crimson",
        point_size=7,
        render_points_as_spheres=True,
        label=f"RH ({len(rh_xyz):,})",
    )


    # ========================================================
    # FRONTAL / ANTERIOR VIEW
    #
    # MNI axes:
    #
    # x = Left -> Right
    # y = Posterior -> Anterior
    # z = Inferior -> Superior
    #
    # Therefore, looking from +Y toward the origin gives
    # the frontal/anterior view.
    # ========================================================

    center = np.asarray(
        cortex.center,
        dtype=float,
    )

    camera_distance = 400.0

    camera_position = (
        (
            center[0],
            center[1] + camera_distance,
            center[2],
        ),
        (
            center[0],
            center[1],
            center[2],
        ),
        (
            0.0,
            0.0,
            1.0,
        ),
    )

    plotter.camera_position = (
        camera_position
    )

    plotter.reset_camera()


    # ========================================================
    # TITLE
    # ========================================================

    plotter.add_text(
        f"MNE cortical source space — P={P:,}",
        position="upper_edge",
        font_size=16,
    )


    # ========================================================
    # LEGEND
    # ========================================================

    plotter.add_legend(
        bcolor="white",
        face=None,
        size=(0.22, 0.13),
    )


    # ========================================================
    # SAVE
    # ========================================================

    plotter.screenshot(
        OUTPUT_PATH,
        scale=2,
    )

    plotter.close()

    print(
        f"\nPASS  saved:"
    )

    print(
        OUTPUT_PATH
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 78)
print("FRONTAL SOURCE-SPACE VISUALIZATION COMPLETE")
print("=" * 78)

for P in SOURCE_DENSITIES:

    path = (
        BEM_ROOT
        / "source_space_qc"
        / f"p{P}"
        / f"source_space_p{P}_frontal.png"
    )

    print(
        f"\nP={P:,}:"
    )

    print(
        f"    {path}"
    )

print("\nDONE.")
print("=" * 78)