"""
Regularization sensitivity test for ONE retained ICA component.

Fixed:
    IC = 1
    P = 2500

Varied:
    relative Tikhonov regularization lambda

Purpose
-------
Determine whether the estimated cortical spatial distribution is stable
when the regularization strength changes.

For each lambda:
    1. Compute regularized minimum-norm inverse.
    2. Compute free-orientation source magnitude.
    3. Normalize magnitude by its maximum for visualization.
    4. Forward-project the solution to EEG space.
    5. Compute scalp reconstruction metrics.
    6. Compare cortical magnitude map with lambda=0.05 reference.
    7. Save frontal, left, right, and superior cortical views.

IMPORTANT
---------
The magnitude of the three free-orientation components is used only for
this spatial stability experiment.

It is NOT yet the final signed cortical weight w_i(r).
"""

from pathlib import Path

import mne
import numpy as np
import pandas as pd
import pyvista as pv


# ============================================================
# CONFIGURATION
# ============================================================

P = 2500
IC_TO_TEST = 1

LAMBDAS = [
    0.001,
    0.005,
    0.01,
    0.05,
    0.1,
    0.5,
]

REFERENCE_LAMBDA = 0.05


# ============================================================
# PATHS
# ============================================================

HERE = Path(__file__).resolve().parent
COP_ROOT = HERE.parents[2]

EEG_SOURCE_LOCALIZATION_DIR = (
    COP_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "source_localization"
)

FORWARD_PATH = (
    HERE
    / "forward_models"
    / f"p{P}"
    / f"sub-1_p{P}-eeg-fwd.fif"
)

IC_MAP_PATH = (
    EEG_SOURCE_LOCALIZATION_DIR
    / "sub-1_ses-0_retained_ic_scalp_maps.csv"
)

SOURCE_MAPPING_PATH = (
    HERE
    / f"icbm152-discrete-p{P}-source-mapping.csv"
)

SOURCE_SPACE_PATH = (
    HERE
    / f"icbm152-discrete-p{P}-src.fif"
)

CORTEX_PATH = (
    COP_ROOT
    / "hm_icbm152"
    / "cortex_pial_high_mni152.obj"
)

OUTPUT_DIR = (
    HERE
    / "inverse_test"
    / f"p{P}"
    / f"IC{IC_TO_TEST:03d}"
    / "lambda_sweep"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# HELPERS
# ============================================================

def section(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def lambda_label(value):
    """
    Convert lambda to a filename-safe label.

    Example:
        0.001 -> 0p001
        0.05  -> 0p05
    """
    return f"{value:g}".replace(".", "p")


def safe_correlation(x, y):
    """
    Pearson correlation with a simple zero-variance check.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if np.std(x) == 0 or np.std(y) == 0:
        return np.nan

    return np.corrcoef(x, y)[0, 1]


def normalized_rmse(x, y):
    """
    Compare two already normalized spatial maps.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    return np.sqrt(
        np.mean(
            (x - y) ** 2
        )
    )


def top_fraction_indices(values, fraction=0.05):
    """
    Return indices of the strongest top fraction of sources.

    Example:
        fraction=0.05 -> strongest 5% of source locations.
    """
    values = np.asarray(values)

    n_keep = max(
        1,
        int(np.ceil(len(values) * fraction)),
    )

    return np.argsort(values)[-n_keep:]


def jaccard_index(indices_a, indices_b):
    """
    Jaccard overlap between two sets of source indices.
    """
    a = set(
        np.asarray(indices_a).tolist()
    )

    b = set(
        np.asarray(indices_b).tolist()
    )

    union = a | b

    if len(union) == 0:
        return np.nan

    return len(a & b) / len(union)


def weighted_centroid(xyz, weights):
    """
    Magnitude-weighted spatial centroid in millimeters.
    """
    xyz = np.asarray(xyz, dtype=float)
    weights = np.asarray(weights, dtype=float)

    total = np.sum(weights)

    if total <= 0:
        return np.full(3, np.nan)

    return np.sum(
        xyz * weights[:, None],
        axis=0,
    ) / total


def add_source_scene(
    plotter,
    cortex,
    source_xyz_mm,
    normalized_magnitude,
    title,
):
    """
    Add common cortex + source magnitude scene.
    """

    plotter.set_background("white")

    plotter.add_mesh(
        cortex,
        color="lightgray",
        opacity=0.18,
        smooth_shading=True,
    )

    points = pv.PolyData(
        source_xyz_mm
    )

    points["normalized_magnitude"] = (
        normalized_magnitude
    )

    plotter.add_mesh(
        points,
        scalars="normalized_magnitude",
        cmap="viridis",
        clim=[0.0, 1.0],
        point_size=10,
        render_points_as_spheres=True,
        scalar_bar_args={
            "title": "Normalized source magnitude"
        },
    )

    plotter.add_text(
        title,
        position="upper_left",
        font_size=13,
        color="black",
    )


def set_camera(
    plotter,
    center,
    view,
):
    """
    Set explicit MNI-oriented camera.

    MNI:
        +X = right
        +Y = anterior
        +Z = superior
    """

    distance = 400.0

    cx, cy, cz = center

    if view == "frontal":

        camera = (
            cx,
            cy + distance,
            cz,
        )

        up = (
            0.0,
            0.0,
            1.0,
        )

    elif view == "left":

        camera = (
            cx - distance,
            cy,
            cz,
        )

        up = (
            0.0,
            0.0,
            1.0,
        )

    elif view == "right":

        camera = (
            cx + distance,
            cy,
            cz,
        )

        up = (
            0.0,
            0.0,
            1.0,
        )

    elif view == "superior":

        camera = (
            cx,
            cy,
            cz + distance,
        )

        # Anterior (+Y) appears toward the top.
        up = (
            0.0,
            1.0,
            0.0,
        )

    else:
        raise ValueError(
            f"Unknown view: {view}"
        )

    plotter.camera_position = [
        camera,
        tuple(center),
        up,
    ]

    plotter.reset_camera()


# ============================================================
# START
# ============================================================

section("IC001 REGULARIZATION SENSITIVITY TEST")

print(f"Source density   : P = {P}")
print(f"ICA component    : IC {IC_TO_TEST}")
print(f"Reference lambda : {REFERENCE_LAMBDA}")

print()
print("Lambda values:")

for value in LAMBDAS:
    print(f"  {value}")


if REFERENCE_LAMBDA not in LAMBDAS:
    raise RuntimeError(
        "REFERENCE_LAMBDA must be included "
        "in LAMBDAS."
    )


# ============================================================
# CHECK INPUTS
# ============================================================

section("CHECK INPUT FILES")

required_files = [
    FORWARD_PATH,
    IC_MAP_PATH,
    SOURCE_MAPPING_PATH,
    SOURCE_SPACE_PATH,
    CORTEX_PATH,
]

for path in required_files:

    if not path.exists():
        raise FileNotFoundError(
            f"Missing required file:\n{path}"
        )

    print(f"PASS  {path.name}")


# ============================================================
# LOAD FORWARD MODEL
# ============================================================

section("LOAD FORWARD MODEL")

fwd = mne.read_forward_solution(
    FORWARD_PATH,
    verbose=False,
)

G = np.asarray(
    fwd["sol"]["data"],
    dtype=float,
)

forward_channels = list(
    fwd["sol"]["row_names"]
)

n_channels, n_components = G.shape

expected_components = 3 * P

print(f"Gain matrix       : {G.shape}")
print(f"EEG channels      : {n_channels}")
print(f"Source locations  : {P}")
print(f"Dipole components : {n_components}")

if n_channels != 128:
    raise RuntimeError(
        f"Expected 128 channels, "
        f"found {n_channels}."
    )

if n_components != expected_components:
    raise RuntimeError(
        f"Expected {expected_components} "
        f"components, found {n_components}."
    )

if not np.isfinite(G).all():
    raise RuntimeError(
        "Forward matrix contains NaN or Inf."
    )

print()
print("Forward model: PASS")


# ============================================================
# LOAD IC TABLE
# ============================================================

section("LOAD IC001")

ic_df = pd.read_csv(
    IC_MAP_PATH
)

required_columns = {
    "IC_index",
    "IC_name",
    "channel",
    "scalp_weight",
}

missing = (
    required_columns
    - set(ic_df.columns)
)

if missing:
    raise RuntimeError(
        "Missing IC-table columns:\n"
        + "\n".join(sorted(missing))
    )


ic_selected = (
    ic_df[
        ic_df["IC_index"]
        == IC_TO_TEST
    ]
    .copy()
)

if len(ic_selected) != 128:
    raise RuntimeError(
        f"Expected 128 rows for IC "
        f"{IC_TO_TEST}, found "
        f"{len(ic_selected)}."
    )

ic_names = (
    ic_selected["IC_name"]
    .astype(str)
    .unique()
)

if len(ic_names) != 1:
    raise RuntimeError(
        "Selected IC has multiple names."
    )

IC_NAME = ic_names[0]

print(f"IC index : {IC_TO_TEST}")
print(f"IC name  : {IC_NAME}")
print(f"Rows     : {len(ic_selected)}")


# ============================================================
# ALIGN CHANNELS
# ============================================================

section("ALIGN CHANNELS")

ic_selected["channel"] = (
    ic_selected["channel"]
    .astype(str)
)

if ic_selected["channel"].duplicated().any():
    raise RuntimeError(
        "Duplicate channels in IC table."
    )

selected_channels = set(
    ic_selected["channel"]
)

forward_channel_set = set(
    forward_channels
)

if selected_channels != forward_channel_set:

    missing_from_ic = (
        forward_channel_set
        - selected_channels
    )

    extra_in_ic = (
        selected_channels
        - forward_channel_set
    )

    raise RuntimeError(
        "Channel mismatch.\n"
        f"Missing from IC: "
        f"{sorted(missing_from_ic)}\n"
        f"Extra in IC: "
        f"{sorted(extra_in_ic)}"
    )


ic_selected = (
    ic_selected
    .set_index("channel")
    .loc[forward_channels]
)

a = (
    ic_selected["scalp_weight"]
    .to_numpy(dtype=float)
)

if not np.isfinite(a).all():
    raise RuntimeError(
        "IC scalp map contains NaN or Inf."
    )

print("128/128 channels aligned: PASS")


# ============================================================
# COMMON-AVERAGE PROJECTION
# ============================================================

section("COMMON-AVERAGE PROJECTION")

H = (
    np.eye(n_channels)
    - np.ones(
        (n_channels, n_channels)
    )
    / n_channels
)

a_ref = H @ a

G_ref = H @ G

a_norm = np.linalg.norm(
    a_ref
)

if a_norm <= 0:
    raise RuntimeError(
        "Invalid IC norm."
    )

a_test = (
    a_ref
    / a_norm
)

print(
    "Mean projected IC : "
    f"{np.mean(a_ref):.12e}"
)

print(
    "Normalized IC norm: "
    f"{np.linalg.norm(a_test):.12f}"
)

print()
print("Projection/normalization: PASS")


# ============================================================
# LOAD SOURCE COORDINATES
# ============================================================

section("LOAD SOURCE COORDINATES")

mapping_df = pd.read_csv(
    SOURCE_MAPPING_PATH
)

if len(mapping_df) != P:
    raise RuntimeError(
        f"Expected {P} mapping rows, "
        f"found {len(mapping_df)}."
    )


# Your actual mapping CSV uses these names.
mapping_coordinate_columns = (
    "mni152_r_mm",
    "mni152_a_mm",
    "mni152_s_mm",
)


if all(
    col in mapping_df.columns
    for col in mapping_coordinate_columns
):

    source_xyz_mm = (
        mapping_df[
            list(
                mapping_coordinate_columns
            )
        ]
        .to_numpy(dtype=float)
    )

    print(
        "Using MNI coordinates from "
        "source mapping CSV."
    )

else:

    print(
        "MNI coordinate columns not found; "
        "using source-space FIF."
    )

    src = mne.read_source_spaces(
        SOURCE_SPACE_PATH,
        verbose=False,
    )

    if len(src) != 1:
        raise RuntimeError(
            "Expected one discrete "
            "source-space entry."
        )

    source_xyz_mm = (
        src[0]["rr"][
            src[0]["vertno"]
        ]
        * 1000.0
    )


if source_xyz_mm.shape != (P, 3):
    raise RuntimeError(
        f"Unexpected source coordinate shape: "
        f"{source_xyz_mm.shape}"
    )

if not np.isfinite(
    source_xyz_mm
).all():
    raise RuntimeError(
        "Source coordinates contain NaN/Inf."
    )

print(
    f"Source coordinates : "
    f"{source_xyz_mm.shape}"
)

print("Source coordinates: PASS")


# ============================================================
# PRECOMPUTE GG^T
# ============================================================

section("PRECOMPUTE SENSOR-SPACE FORWARD MATRIX")

K = (
    G_ref
    @ G_ref.T
)

mean_eigenvalue = (
    np.trace(K)
    / n_channels
)

print(
    "Mean eigenvalue(GG^T): "
    f"{mean_eigenvalue:.12e}"
)

if (
    not np.isfinite(mean_eigenvalue)
    or mean_eigenvalue <= 0
):
    raise RuntimeError(
        "Invalid forward scaling."
    )


# ============================================================
# RUN LAMBDA SWEEP
# ============================================================

section("RUN LAMBDA SWEEP")

results = {}

for lambda_rel in LAMBDAS:

    print()
    print("-" * 70)
    print(
        f"lambda_rel = {lambda_rel}"
    )
    print("-" * 70)

    alpha = (
        lambda_rel
        * mean_eigenvalue
    )

    A = (
        K
        + alpha
        * np.eye(n_channels)
    )

    sensor_solution = np.linalg.solve(
        A,
        a_test,
    )

    j_hat = (
        G_ref.T
        @ sensor_solution
    )

    if not np.isfinite(
        j_hat
    ).all():
        raise RuntimeError(
            f"Invalid inverse at "
            f"lambda={lambda_rel}"
        )

    # ----------------------------------------
    # Free-orientation vectors
    # ----------------------------------------

    J = j_hat.reshape(
        P,
        3,
    )

    magnitude = np.linalg.norm(
        J,
        axis=1,
    )

    magnitude_max = np.max(
        magnitude
    )

    if magnitude_max <= 0:
        raise RuntimeError(
            f"Zero source magnitude at "
            f"lambda={lambda_rel}"
        )

    normalized_magnitude = (
        magnitude
        / magnitude_max
    )

    # ----------------------------------------
    # Forward reconstruction
    # ----------------------------------------

    a_hat = (
        G_ref
        @ j_hat
    )

    scalp_correlation = (
        safe_correlation(
            a_test,
            a_hat,
        )
    )

    relative_l2_error = (
        np.linalg.norm(
            a_test - a_hat
        )
        /
        np.linalg.norm(
            a_test
        )
    )

    rmse = np.sqrt(
        np.mean(
            (
                a_test
                - a_hat
            ) ** 2
        )
    )

    # ----------------------------------------
    # Spatial descriptors
    # ----------------------------------------

    peak_index = int(
        np.argmax(magnitude)
    )

    peak_xyz = (
        source_xyz_mm[
            peak_index
        ]
    )

    centroid = weighted_centroid(
        source_xyz_mm,
        magnitude,
    )

    top5 = top_fraction_indices(
        magnitude,
        fraction=0.05,
    )

    # ----------------------------------------
    # Store
    # ----------------------------------------

    results[lambda_rel] = {
        "alpha":
            alpha,

        "j_hat":
            j_hat,

        "J":
            J,

        "magnitude":
            magnitude,

        "normalized_magnitude":
            normalized_magnitude,

        "a_hat":
            a_hat,

        "scalp_correlation":
            scalp_correlation,

        "relative_l2_error":
            relative_l2_error,

        "rmse":
            rmse,

        "peak_index":
            peak_index,

        "peak_xyz":
            peak_xyz,

        "centroid":
            centroid,

        "top5":
            top5,
    }


    print(
        f"alpha              : "
        f"{alpha:.6e}"
    )

    print(
        f"scalp correlation  : "
        f"{scalp_correlation:.6f}"
    )

    print(
        f"relative L2 error  : "
        f"{relative_l2_error:.6f}"
    )

    print(
        f"source max         : "
        f"{magnitude_max:.6e}"
    )

    print(
        f"peak source index  : "
        f"{peak_index}"
    )

    print(
        "peak MNI [mm]      : "
        f"({peak_xyz[0]:.2f}, "
        f"{peak_xyz[1]:.2f}, "
        f"{peak_xyz[2]:.2f})"
    )


# ============================================================
# COMPARE WITH REFERENCE LAMBDA
# ============================================================

section(
    f"COMPARE MAPS WITH REFERENCE "
    f"LAMBDA = {REFERENCE_LAMBDA}"
)

reference = results[
    REFERENCE_LAMBDA
]

reference_map = (
    reference[
        "normalized_magnitude"
    ]
)

reference_top5 = (
    reference[
        "top5"
    ]
)

reference_peak = (
    reference[
        "peak_xyz"
    ]
)

reference_centroid = (
    reference[
        "centroid"
    ]
)


summary_rows = []


for lambda_rel in LAMBDAS:

    result = results[
        lambda_rel
    ]

    current_map = (
        result[
            "normalized_magnitude"
        ]
    )

    map_correlation = (
        safe_correlation(
            reference_map,
            current_map,
        )
    )

    map_nrmse = (
        normalized_rmse(
            reference_map,
            current_map,
        )
    )

    top5_jaccard = (
        jaccard_index(
            reference_top5,
            result["top5"],
        )
    )

    peak_displacement = (
        np.linalg.norm(
            result["peak_xyz"]
            - reference_peak
        )
    )

    centroid_displacement = (
        np.linalg.norm(
            result["centroid"]
            - reference_centroid
        )
    )


    summary_rows.append(
        {
            "lambda_rel":
                lambda_rel,

            "alpha":
                result["alpha"],

            "scalp_correlation":
                result[
                    "scalp_correlation"
                ],

            "relative_l2_error":
                result[
                    "relative_l2_error"
                ],

            "rmse":
                result["rmse"],

            "source_magnitude_max":
                np.max(
                    result["magnitude"]
                ),

            "map_corr_vs_lambda_0p05":
                map_correlation,

            "map_nrmse_vs_lambda_0p05":
                map_nrmse,

            "top5_jaccard_vs_lambda_0p05":
                top5_jaccard,

            "peak_displacement_mm":
                peak_displacement,

            "centroid_displacement_mm":
                centroid_displacement,

            "peak_x_mm":
                result["peak_xyz"][0],

            "peak_y_mm":
                result["peak_xyz"][1],

            "peak_z_mm":
                result["peak_xyz"][2],

            "centroid_x_mm":
                result["centroid"][0],

            "centroid_y_mm":
                result["centroid"][1],

            "centroid_z_mm":
                result["centroid"][2],
        }
    )


    print()
    print(
        f"lambda = {lambda_rel}"
    )

    print(
        f"  map correlation     : "
        f"{map_correlation:.6f}"
    )

    print(
        f"  normalized RMSE     : "
        f"{map_nrmse:.6f}"
    )

    print(
        f"  top-5% Jaccard      : "
        f"{top5_jaccard:.6f}"
    )

    print(
        f"  peak displacement   : "
        f"{peak_displacement:.3f} mm"
    )

    print(
        f"  centroid displacement: "
        f"{centroid_displacement:.3f} mm"
    )


# ============================================================
# SAVE SUMMARY TABLE
# ============================================================

section("SAVE SUMMARY TABLE")

summary_df = pd.DataFrame(
    summary_rows
)

summary_path = (
    OUTPUT_DIR
    / "lambda_sweep_summary.csv"
)

summary_df.to_csv(
    summary_path,
    index=False,
)

print(
    f"Saved:\n{summary_path}"
)


# ============================================================
# SAVE SOURCE MAPS
# ============================================================

section("SAVE SOURCE MAPS")

for lambda_rel in LAMBDAS:

    result = results[
        lambda_rel
    ]

    label = lambda_label(
        lambda_rel
    )

    source_df = pd.DataFrame(
        {
            "source_index":
                np.arange(P),

            "x_mm":
                source_xyz_mm[:, 0],

            "y_mm":
                source_xyz_mm[:, 1],

            "z_mm":
                source_xyz_mm[:, 2],

            "jx":
                result["J"][:, 0],

            "jy":
                result["J"][:, 1],

            "jz":
                result["J"][:, 2],

            "magnitude":
                result["magnitude"],

            "normalized_magnitude":
                result[
                    "normalized_magnitude"
                ],
        }
    )

    output_path = (
        OUTPUT_DIR
        / (
            f"IC{IC_TO_TEST:03d}"
            f"_p{P}"
            f"_lambda_{label}"
            f"_sources.csv"
        )
    )

    source_df.to_csv(
        output_path,
        index=False,
    )

    print(
        f"Saved lambda={lambda_rel}: "
        f"{output_path.name}"
    )


# ============================================================
# VISUALIZATION
# ============================================================

section("GENERATE MULTI-VIEW CORTICAL MAPS")

cortex = pv.read(
    CORTEX_PATH
)

center = np.asarray(
    cortex.center
)

views = [
    "frontal",
    "left",
    "right",
    "superior",
]


for lambda_rel in LAMBDAS:

    result = results[
        lambda_rel
    ]

    normalized_magnitude = (
        result[
            "normalized_magnitude"
        ]
    )

    label = lambda_label(
        lambda_rel
    )

    lambda_dir = (
        OUTPUT_DIR
        / f"lambda_{label}"
    )

    lambda_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print(
        f"Rendering lambda={lambda_rel}"
    )

    for view in views:

        plotter = pv.Plotter(
            off_screen=True,
            window_size=(
                1600,
                1200,
            ),
        )

        title = (
            f"{IC_NAME} | "
            f"P={P} | "
            f"lambda={lambda_rel} | "
            f"{view}"
        )

        add_source_scene(
            plotter,
            cortex,
            source_xyz_mm,
            normalized_magnitude,
            title,
        )

        set_camera(
            plotter,
            center,
            view,
        )

        image_path = (
            lambda_dir
            / (
                f"IC{IC_TO_TEST:03d}"
                f"_p{P}"
                f"_lambda_{label}"
                f"_{view}.png"
            )
        )

        plotter.screenshot(
            image_path
        )

        plotter.close()

        print(
            f"  Saved {view}"
        )


# ============================================================
# FINAL REPORT
# ============================================================

section("FINAL LAMBDA-SWEEP SUMMARY")

display_columns = [
    "lambda_rel",
    "scalp_correlation",
    "relative_l2_error",
    "map_corr_vs_lambda_0p05",
    "top5_jaccard_vs_lambda_0p05",
    "peak_displacement_mm",
    "centroid_displacement_mm",
]

print(
    summary_df[
        display_columns
    ].to_string(
        index=False
    )
)

print()
print("=" * 78)
print("INTERPRETATION GUIDE")
print("=" * 78)

print()
print(
    "We are NOT choosing lambda from scalp reconstruction "
    "error alone."
)

print()
print(
    "The main question is whether the cortical spatial map "
    "remains stable as lambda changes."
)

print()
print(
    "Useful stability indicators:"
)

print(
    "  1. High cortical map correlation."
)

print(
    "  2. High top-5% source overlap (Jaccard)."
)

print(
    "  3. Small peak displacement."
)

print(
    "  4. Small magnitude-weighted centroid displacement."
)

print(
    "  5. No dramatic visual relocation of the dominant "
    "cortical regions."
)

print()
print(
    "Do NOT run the 44 ICs or P=5000/P=10000 yet."
)

print()
print(
    "First evaluate this regularization sensitivity experiment."
)

print()
print("LAMBDA SWEEP COMPLETE")