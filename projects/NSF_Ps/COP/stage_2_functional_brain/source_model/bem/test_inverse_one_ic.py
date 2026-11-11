"""
Test distributed EEG inverse reconstruction for ONE retained ICA component.

Purpose
-------
Controlled first inverse-model test.

Uses:
    - one retained ICA scalp topography
    - P = 2500 forward model
    - free-orientation source model
    - simple L2/Tikhonov minimum-norm regularization

This test does NOT:
    - process all 44 ICs
    - compare source-space densities
    - define the final inverse pipeline
    - interpret placeholder source-space normals as cortical normals

Pipeline
--------
IC scalp map
    ->
channel alignment
    ->
average-reference projection
    ->
normalization
    ->
regularized minimum-norm inverse
    ->
free-orientation cortical source estimate
    ->
forward reconstruction
    ->
comparison with original scalp map
    ->
cortical visualization
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

# Original ICA component number to test.
IC_TO_TEST = 1

# Relative Tikhonov regularization.
#
# alpha =
#     LAMBDA_REL * mean_eigenvalue(G G^T)
#
# This is only the initial controlled test value.
LAMBDA_REL = 0.05


# ============================================================
# PATHS
# ============================================================

HERE = Path(__file__).resolve().parent

# bem/
# -> source_model/
# -> stage_2_functional_brain/
# -> COP/
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
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# HELPER
# ============================================================

def section(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# ============================================================
# START
# ============================================================

section("ONE-IC DISTRIBUTED INVERSE TEST")

print(f"Source density       : P = {P}")
print(f"ICA component        : IC {IC_TO_TEST}")
print(f"Relative regularizer : {LAMBDA_REL}")

print()
print("This is a TEST only.")
print("No final inverse-model assumptions are frozen here.")


# ============================================================
# CHECK INPUT FILES
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


print(f"EEG channels      : {n_channels}")
print(f"Source locations  : {P}")
print(f"Dipole components : {n_components}")
print(f"Gain matrix       : {G.shape}")


if n_channels != 128:
    raise RuntimeError(
        f"Expected 128 EEG channels, "
        f"found {n_channels}."
    )


if n_components != expected_components:
    raise RuntimeError(
        f"Expected {expected_components} "
        f"free-orientation components, "
        f"found {n_components}."
    )


if not np.isfinite(G).all():
    raise RuntimeError(
        "Forward matrix contains NaN or Inf."
    )


if len(forward_channels) != n_channels:
    raise RuntimeError(
        "Forward channel-name count does not "
        "match gain-matrix rows."
    )


if len(set(forward_channels)) != n_channels:
    raise RuntimeError(
        "Duplicate channel names found "
        "in forward model."
    )


print()
print("Forward matrix: PASS")


# ============================================================
# LOAD RETAINED IC TABLE
# ============================================================

section("LOAD RETAINED IC SCALP MAP")

ic_df = pd.read_csv(
    IC_MAP_PATH
)


print(f"Total rows : {len(ic_df)}")
print(f"Columns    : {list(ic_df.columns)}")


required_columns = {
    "IC_index",
    "IC_name",
    "channel_index",
    "channel",
    "scalp_weight",
}


missing_columns = (
    required_columns
    - set(ic_df.columns)
)


if missing_columns:
    raise RuntimeError(
        "Missing required columns:\n"
        + "\n".join(
            sorted(missing_columns)
        )
    )


# ============================================================
# VERIFY COMPLETE RETAINED-IC TABLE
# ============================================================

n_ics = (
    ic_df["IC_index"]
    .nunique()
)


print()
print(
    f"Unique retained ICs : {n_ics}"
)

print(
    "Expected rows / IC  : 128"
)


counts = (
    ic_df
    .groupby("IC_index")
    .size()
)


if not np.all(
    counts.to_numpy() == 128
):
    raise RuntimeError(
        "Not every retained IC contains "
        "exactly 128 channels.\n"
        f"Counts:\n{counts}"
    )


print(
    "All retained ICs contain "
    "128 channels: PASS"
)


# ============================================================
# SELECT REQUESTED IC
# ============================================================

section("SELECT TEST IC")


available_ic_indices = sorted(
    ic_df["IC_index"]
    .unique()
    .tolist()
)


print(
    f"Available IC indices:\n"
    f"{available_ic_indices}"
)


ic_selected = (
    ic_df[
        ic_df["IC_index"]
        == IC_TO_TEST
    ]
    .copy()
)


if len(ic_selected) == 0:
    raise RuntimeError(
        f"IC_index={IC_TO_TEST} was not found.\n"
        f"Available indices:\n"
        f"{available_ic_indices}"
    )


if len(ic_selected) != 128:
    raise RuntimeError(
        f"IC {IC_TO_TEST} should contain "
        f"128 channels, but found "
        f"{len(ic_selected)}."
    )


ic_names = (
    ic_selected["IC_name"]
    .astype(str)
    .unique()
)


if len(ic_names) != 1:
    raise RuntimeError(
        f"IC_index={IC_TO_TEST} maps to "
        f"multiple IC_name values:\n"
        f"{ic_names.tolist()}"
    )


selected_ic_name = ic_names[0]


print()
print(
    f"Selected IC index : {IC_TO_TEST}"
)

print(
    f"Selected IC name  : {selected_ic_name}"
)

print(
    f"Rows selected     : {len(ic_selected)}"
)


# ============================================================
# ALIGN IC MAP TO FORWARD CHANNEL ORDER
# ============================================================

section("ALIGN EEG CHANNEL ORDER")


ic_selected["channel"] = (
    ic_selected["channel"]
    .astype(str)
)


if (
    ic_selected["channel"]
    .duplicated()
    .any()
):

    duplicated = (
        ic_selected.loc[
            ic_selected["channel"]
            .duplicated(),
            "channel",
        ]
        .tolist()
    )

    raise RuntimeError(
        "Duplicate channels found "
        "for selected IC:\n"
        + "\n".join(duplicated)
    )


selected_channels = set(
    ic_selected["channel"]
)


forward_channel_set = set(
    forward_channels
)


missing_from_ic = (
    forward_channel_set
    - selected_channels
)


extra_in_ic = (
    selected_channels
    - forward_channel_set
)


if missing_from_ic:
    raise RuntimeError(
        "Forward channels missing "
        "from selected IC:\n"
        + "\n".join(
            sorted(missing_from_ic)
        )
    )


if extra_in_ic:
    raise RuntimeError(
        "Selected IC contains channels "
        "not present in forward model:\n"
        + "\n".join(
            sorted(extra_in_ic)
        )
    )


# Explicitly reorder IC rows to match
# the row order of the gain matrix.
ic_selected = (
    ic_selected
    .set_index("channel")
    .loc[forward_channels]
)


a = (
    ic_selected["scalp_weight"]
    .to_numpy(dtype=float)
)


if a.shape != (128,):
    raise RuntimeError(
        f"Expected scalp map shape "
        f"(128,), found {a.shape}."
    )


if not np.isfinite(a).all():
    raise RuntimeError(
        "Selected IC scalp weights "
        "contain NaN or Inf."
    )


print("128/128 channels matched.")

print(
    "IC channel order aligned "
    "to forward model: PASS"
)


print()

print(
    f"Scalp-map shape : {a.shape}"
)

print(
    f"Minimum weight  : "
    f"{a.min():.12e}"
)

print(
    f"Maximum weight  : "
    f"{a.max():.12e}"
)

print(
    f"Mean weight     : "
    f"{a.mean():.12e}"
)

print(
    f"L2 norm         : "
    f"{np.linalg.norm(a):.12e}"
)


print()
print(
    "IC scalp-map extraction: PASS"
)


# ============================================================
# APPLY COMMON-AVERAGE PROJECTION
# ============================================================

section("APPLY COMMON-AVERAGE PROJECTION")


"""
EEG potentials are defined relative to a reference.

For this controlled test, apply the SAME
common-average projection to:

    1. the IC scalp topography
    2. every column of the forward matrix

Projection:

    H = I - 11^T / N

Then:

    a_ref = H a
    G_ref = H G

This keeps the data and forward model in the
same average-referenced sensor subspace.
"""


H = (
    np.eye(n_channels)
    - np.ones(
        (n_channels, n_channels)
    )
    / n_channels
)


a_ref = H @ a

G_ref = H @ G


mean_before = np.mean(a)

mean_after = np.mean(a_ref)

max_gain_column_mean = np.max(
    np.abs(
        np.mean(
            G_ref,
            axis=0,
        )
    )
)


print(
    "Mean IC value before projection : "
    f"{mean_before:.12e}"
)

print(
    "Mean IC value after projection  : "
    f"{mean_after:.12e}"
)

print(
    "Max |column mean| of projected G : "
    f"{max_gain_column_mean:.12e}"
)


if not np.isfinite(a_ref).all():
    raise RuntimeError(
        "Average-referenced IC contains "
        "NaN or Inf."
    )


if not np.isfinite(G_ref).all():
    raise RuntimeError(
        "Average-referenced forward matrix "
        "contains NaN or Inf."
    )


print()
print(
    "Common-average projection: PASS"
)


# ============================================================
# NORMALIZE IC TOPOGRAPHY
# ============================================================

section("NORMALIZE TEST IC")


"""
ICA contains an intrinsic scaling ambiguity.

For this first spatial reconstruction test,
we normalize the average-referenced IC
topography to unit L2 norm.

This means we are currently evaluating
spatial reconstruction rather than absolute
current amplitude.
"""


a_norm = np.linalg.norm(
    a_ref
)


if (
    not np.isfinite(a_norm)
    or a_norm <= 0
):
    raise RuntimeError(
        "IC scalp map has invalid or "
        "zero L2 norm."
    )


a_test = (
    a_ref
    / a_norm
)


print(
    "Norm before normalization : "
    f"{a_norm:.12e}"
)

print(
    "Norm after normalization  : "
    f"{np.linalg.norm(a_test):.12f}"
)


print()
print(
    "IC normalization: PASS"
)


# ============================================================
# REGULARIZED MINIMUM-NORM SOLUTION
# ============================================================

section(
    "COMPUTE REGULARIZED MINIMUM-NORM SOLUTION"
)


"""
For this initial controlled test, solve:

    j_hat =
        G^T
        (G G^T + alpha I)^(-1)
        a

This is an L2-regularized minimum-norm
solution in sensor-space form.

The regularization is defined relative
to the scale of G G^T:

    alpha =
        LAMBDA_REL
        * trace(G G^T) / N_channels

This is NOT yet being frozen as the
final inverse regularization strategy.
"""


K = (
    G_ref
    @ G_ref.T
)


if K.shape != (
    n_channels,
    n_channels,
):
    raise RuntimeError(
        f"Unexpected GG^T shape: "
        f"{K.shape}"
    )


if not np.isfinite(K).all():
    raise RuntimeError(
        "GG^T contains NaN or Inf."
    )


mean_eigenvalue = (
    np.trace(K)
    / n_channels
)


if (
    not np.isfinite(mean_eigenvalue)
    or mean_eigenvalue <= 0
):
    raise RuntimeError(
        "Invalid mean eigenvalue "
        "for regularization."
    )


alpha = (
    LAMBDA_REL
    * mean_eigenvalue
)


print(
    "Mean eigenvalue(GG^T) : "
    f"{mean_eigenvalue:.12e}"
)

print(
    "Regularization alpha  : "
    f"{alpha:.12e}"
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


if j_hat.shape != (
    expected_components,
):
    raise RuntimeError(
        f"Expected inverse shape "
        f"({expected_components},), "
        f"found {j_hat.shape}."
    )


if not np.isfinite(
    j_hat
).all():
    raise RuntimeError(
        "Inverse solution contains "
        "NaN or Inf."
    )


print()
print(
    f"Inverse vector shape : "
    f"{j_hat.shape}"
)

print(
    "Inverse minimum      : "
    f"{j_hat.min():.12e}"
)

print(
    "Inverse maximum      : "
    f"{j_hat.max():.12e}"
)

print(
    "Inverse L2 norm      : "
    f"{np.linalg.norm(j_hat):.12e}"
)


print()
print(
    "Regularized inverse: PASS"
)


# ============================================================
# FREE-ORIENTATION SOURCE REPRESENTATION
# ============================================================

section(
    "COMPUTE FREE-ORIENTATION SOURCE MAGNITUDES"
)


"""
The forward model contains three orthogonal
dipole components per source location.

Therefore:

    j_hat shape = (3P,)

is reshaped to:

    J shape = (P, 3)

For this FIRST visualization only:

    magnitude(r) =
        sqrt(
            jx(r)^2
            + jy(r)^2
            + jz(r)^2
        )

This produces a nonnegative measure of
source strength.

IMPORTANT:
This magnitude is NOT yet the final
signed cortical IC spatial weight w_i(r).
"""


J = j_hat.reshape(
    P,
    3,
)


source_magnitude = np.linalg.norm(
    J,
    axis=1,
)


if J.shape != (
    P,
    3,
):
    raise RuntimeError(
        f"Unexpected vector-source shape: "
        f"{J.shape}"
    )


if source_magnitude.shape != (
    P,
):
    raise RuntimeError(
        "Source magnitude dimension "
        "mismatch."
    )


if not np.isfinite(
    source_magnitude
).all():
    raise RuntimeError(
        "Source magnitudes contain "
        "NaN or Inf."
    )


print(
    f"Vector source shape : "
    f"{J.shape}"
)

print(
    f"Source locations    : "
    f"{len(source_magnitude)}"
)

print(
    "Magnitude min       : "
    f"{source_magnitude.min():.12e}"
)

print(
    "Magnitude median    : "
    f"{np.median(source_magnitude):.12e}"
)

print(
    "Magnitude mean      : "
    f"{np.mean(source_magnitude):.12e}"
)

print(
    "Magnitude max       : "
    f"{source_magnitude.max():.12e}"
)


print()
print(
    "Free-orientation magnitude: PASS"
)


# ============================================================
# FORWARD RECONSTRUCTION
# ============================================================

section(
    "FORWARD-PROJECT RECONSTRUCTED SOURCE"
)


"""
Reconstruct the scalp topography:

    a_hat = G j_hat

and compare it with the normalized
input scalp topography.

This tests whether the regularized
cortical solution reproduces the
observed spatial EEG pattern.
"""


a_hat = (
    G_ref
    @ j_hat
)


if a_hat.shape != (
    n_channels,
):
    raise RuntimeError(
        f"Unexpected reconstructed scalp "
        f"shape: {a_hat.shape}"
    )


if not np.isfinite(
    a_hat
).all():
    raise RuntimeError(
        "Reconstructed scalp map "
        "contains NaN or Inf."
    )


correlation = np.corrcoef(
    a_test,
    a_hat,
)[0, 1]


relative_error = (
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


print(
    "Spatial correlation : "
    f"{correlation:.6f}"
)

print(
    "Relative L2 error   : "
    f"{relative_error:.6f}"
)

print(
    "RMSE                : "
    f"{rmse:.12e}"
)


if not np.isfinite(
    correlation
):
    raise RuntimeError(
        "Invalid scalp reconstruction "
        "correlation."
    )


print()
print(
    "Forward reconstruction: PASS"
)


# ============================================================
# LOAD SOURCE COORDINATES
# ============================================================

section("LOAD SOURCE COORDINATES")


mapping_df = pd.read_csv(
    SOURCE_MAPPING_PATH
)


print(
    f"Mapping rows : "
    f"{len(mapping_df)}"
)

print(
    f"Mapping columns : "
    f"{list(mapping_df.columns)}"
)


if len(mapping_df) != P:
    raise RuntimeError(
        f"Expected {P} mapping rows, "
        f"found {len(mapping_df)}."
    )


# ------------------------------------------------------------
# Try known coordinate-column formats.
# ------------------------------------------------------------

coordinate_candidates = [
    (
        "mni152_r",
        "mni152_a",
        "mni152_s",
    ),
    (
        "x_mm",
        "y_mm",
        "z_mm",
    ),
    (
        "x",
        "y",
        "z",
    ),
]


coord_cols = None


for candidate in coordinate_candidates:

    if all(
        col in mapping_df.columns
        for col in candidate
    ):
        coord_cols = candidate
        break


if coord_cols is not None:

    source_xyz_mm = (
        mapping_df[
            list(coord_cols)
        ]
        .to_numpy(
            dtype=float
        )
    )

    print(
        f"Using mapping coordinates: "
        f"{coord_cols}"
    )


else:

    # --------------------------------------------------------
    # Safe fallback:
    # use the original MNE discrete source-space coordinates.
    #
    # These are stored in MRI coordinates in meters.
    # --------------------------------------------------------

    print()
    print(
        "Recognized coordinate columns "
        "not found in mapping CSV."
    )

    print(
        "Using source-space FIF coordinates "
        "instead."
    )


    src = mne.read_source_spaces(
        SOURCE_SPACE_PATH,
        verbose=False,
    )


    if len(src) != 1:
        raise RuntimeError(
            f"Expected one discrete source-space "
            f"entry, found {len(src)}."
        )


    vertno = src[0]["vertno"]


    source_xyz_mm = (
        src[0]["rr"][vertno]
        * 1000.0
    )


if source_xyz_mm.shape != (
    P,
    3,
):
    raise RuntimeError(
        f"Expected source-coordinate shape "
        f"({P}, 3), found "
        f"{source_xyz_mm.shape}."
    )


if not np.isfinite(
    source_xyz_mm
).all():
    raise RuntimeError(
        "Source coordinates contain "
        "NaN or Inf."
    )


print(
    f"Source-coordinate shape : "
    f"{source_xyz_mm.shape}"
)

print(
    "X range [mm] : "
    f"{source_xyz_mm[:, 0].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 0].max():.3f}"
)

print(
    "Y range [mm] : "
    f"{source_xyz_mm[:, 1].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 1].max():.3f}"
)

print(
    "Z range [mm] : "
    f"{source_xyz_mm[:, 2].min():.3f} "
    f"to "
    f"{source_xyz_mm[:, 2].max():.3f}"
)


print()
print(
    "Source coordinates: PASS"
)


# ============================================================
# SAVE NUMERICAL RESULTS
# ============================================================

section("SAVE NUMERICAL RESULTS")


result_df = pd.DataFrame(
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
            J[:, 0],

        "jy":
            J[:, 1],

        "jz":
            J[:, 2],

        "magnitude":
            source_magnitude,
    }
)


result_csv = (
    OUTPUT_DIR
    / (
        f"IC{IC_TO_TEST:03d}"
        f"_p{P}"
        f"_inverse_test.csv"
    )
)


result_df.to_csv(
    result_csv,
    index=False,
)


scalp_df = pd.DataFrame(
    {
        "channel":
            forward_channels,

        "original_scalp_weight":
            a,

        "average_referenced":
            a_ref,

        "normalized_input":
            a_test,

        "reconstructed":
            a_hat,

        "residual":
            a_test - a_hat,
    }
)


scalp_csv = (
    OUTPUT_DIR
    / (
        f"IC{IC_TO_TEST:03d}"
        f"_p{P}"
        f"_scalp_reconstruction.csv"
    )
)


scalp_df.to_csv(
    scalp_csv,
    index=False,
)


summary_path = (
    OUTPUT_DIR
    / (
        f"IC{IC_TO_TEST:03d}"
        f"_p{P}"
        f"_summary.txt"
    )
)


with open(
    summary_path,
    "w",
    encoding="utf-8",
) as f:

    f.write(
        "ONE-IC DISTRIBUTED INVERSE TEST\n"
    )

    f.write(
        "=" * 60 + "\n"
    )

    f.write(
        f"IC_index: {IC_TO_TEST}\n"
    )

    f.write(
        f"IC_name: {selected_ic_name}\n"
    )

    f.write(
        f"P: {P}\n"
    )

    f.write(
        f"Forward shape: {G.shape}\n"
    )

    f.write(
        f"Relative regularizer: "
        f"{LAMBDA_REL}\n"
    )

    f.write(
        f"alpha: "
        f"{alpha:.12e}\n"
    )

    f.write(
        f"Spatial correlation: "
        f"{correlation:.12f}\n"
    )

    f.write(
        f"Relative L2 error: "
        f"{relative_error:.12f}\n"
    )

    f.write(
        f"RMSE: "
        f"{rmse:.12e}\n"
    )

    f.write(
        f"Source magnitude min: "
        f"{source_magnitude.min():.12e}\n"
    )

    f.write(
        f"Source magnitude median: "
        f"{np.median(source_magnitude):.12e}\n"
    )

    f.write(
        f"Source magnitude mean: "
        f"{np.mean(source_magnitude):.12e}\n"
    )

    f.write(
        f"Source magnitude max: "
        f"{source_magnitude.max():.12e}\n"
    )


print(
    f"Saved:\n{result_csv}"
)

print()

print(
    f"Saved:\n{scalp_csv}"
)

print()

print(
    f"Saved:\n{summary_path}"
)


# ============================================================
# VISUALIZE CORTICAL SOURCE MAGNITUDE
# ============================================================

section(
    "VISUALIZE CORTICAL SOURCE MAGNITUDE"
)


cortex = pv.read(
    CORTEX_PATH
)


points = pv.PolyData(
    source_xyz_mm
)


points["magnitude"] = (
    source_magnitude
)


plotter = pv.Plotter(
    off_screen=True,
    window_size=(
        1600,
        1200,
    ),
)


plotter.set_background(
    "white"
)


plotter.add_mesh(
    cortex,
    color="lightgray",
    opacity=0.20,
    smooth_shading=True,
)


plotter.add_mesh(
    points,
    scalars="magnitude",
    cmap="viridis",
    point_size=10,
    render_points_as_spheres=True,
    scalar_bar_args={
        "title":
            "Source magnitude"
    },
)


center = np.asarray(
    cortex.center
)


# MNI coordinate convention:
# +Y = anterior.
#
# Position camera anterior to the brain
# and look toward its center.

plotter.camera_position = [
    (
        center[0],
        center[1] + 400.0,
        center[2],
    ),
    tuple(center),
    (
        0.0,
        0.0,
        1.0,
    ),
]


plotter.reset_camera()


plotter.add_text(
    (
        f"{selected_ic_name} "
        f"(IC_index={IC_TO_TEST}) | "
        f"P={P} | "
        f"Inverse test"
    ),
    position="upper_left",
    font_size=14,
    color="black",
)


image_path = (
    OUTPUT_DIR
    / (
        f"IC{IC_TO_TEST:03d}"
        f"_p{P}"
        f"_frontal.png"
    )
)


plotter.screenshot(
    image_path
)


plotter.close()


print(
    f"Saved:\n{image_path}"
)


# ============================================================
# FINAL SUMMARY
# ============================================================

section("FINAL TEST SUMMARY")


print(
    f"IC index             : "
    f"{IC_TO_TEST}"
)

print(
    f"IC name              : "
    f"{selected_ic_name}"
)

print(
    f"Source density       : "
    f"{P}"
)

print(
    f"Forward matrix       : "
    f"{G.shape}"
)

print(
    f"Inverse vector       : "
    f"{j_hat.shape}"
)

print(
    f"Vector source matrix : "
    f"{J.shape}"
)

print(
    f"Cortical locations   : "
    f"{len(source_magnitude)}"
)

print()

print(
    f"Spatial correlation  : "
    f"{correlation:.6f}"
)

print(
    f"Relative L2 error    : "
    f"{relative_error:.6f}"
)

print(
    f"RMSE                 : "
    f"{rmse:.12e}"
)

print()

print(
    f"Relative lambda      : "
    f"{LAMBDA_REL}"
)

print(
    f"Regularization alpha : "
    f"{alpha:.12e}"
)

print()

print(
    "Source magnitude:"
)

print(
    f"  min    = "
    f"{source_magnitude.min():.12e}"
)

print(
    f"  median = "
    f"{np.median(source_magnitude):.12e}"
)

print(
    f"  mean   = "
    f"{np.mean(source_magnitude):.12e}"
)

print(
    f"  max    = "
    f"{source_magnitude.max():.12e}"
)


print()
print("-" * 78)

print(
    "IMPORTANT INTERPRETATION"
)

print("-" * 78)

print()

print(
    "1. This is a controlled inverse TEST, "
    "not the final inverse pipeline."
)

print()

print(
    "2. The displayed cortical magnitude is "
    "the norm of the three free-orientation "
    "components at each source."
)

print()

print(
    "3. This magnitude is nonnegative and "
    "must NOT yet be interpreted as the "
    "final signed cortical IC weight w_i(r)."
)

print()

print(
    "4. The regularization strategy has "
    "not yet been frozen."
)

print()

print(
    "5. Do NOT run all 44 ICs yet."
)

print()

print(
    "First inspect:"
)

print(
    "   - IC identity"
)

print(
    "   - spatial correlation"
)

print(
    "   - relative L2 error"
)

print(
    "   - source magnitude distribution"
)

print(
    "   - frontal cortical map"
)

print()

print(
    "ONE-IC INVERSE TEST COMPLETE"
)