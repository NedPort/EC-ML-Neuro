from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist


# ============================================================
# Paths
# ============================================================

BEM_ROOT = Path(__file__).resolve().parent
COP_ROOT = BEM_ROOT.parents[2]

ANATOMY_DIR = COP_ROOT / "hm_icbm152"

INPUT_CSV = (
    ANATOMY_DIR
    / "brain_vertex_coordinates.csv"
)

OUTPUT_DIR = (
    BEM_ROOT
    / "source_space_candidates"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "source_space_p2500.csv"
)


# ============================================================
# Settings
# ============================================================

TARGET_P = 2500

COORD_COLS = [
    "mni152_r",
    "mni152_a",
    "mni152_s",
]


# ============================================================
# Farthest-point sampling
# ============================================================

def farthest_point_sampling(points, n_select):
    """
    Select n_select existing points using deterministic
    Euclidean farthest-point sampling.

    No new coordinates are generated.

    Parameters
    ----------
    points : ndarray, shape (N, 3)
        Candidate MNI coordinates.

    n_select : int
        Number of points to select.

    Returns
    -------
    selected : ndarray, shape (n_select,)
        Indices into the input points array.
    """

    points = np.asarray(
        points,
        dtype=np.float64,
    )

    n_points = len(points)

    if n_select > n_points:
        raise ValueError(
            "Cannot select more points than available."
        )

    # --------------------------------------------------------
    # Deterministic starting point
    #
    # Start with the point farthest from the hemisphere's
    # coordinate centroid.
    # --------------------------------------------------------

    centroid = points.mean(axis=0)

    dist_to_centroid = np.linalg.norm(
        points - centroid,
        axis=1,
    )

    first = int(
        np.argmax(dist_to_centroid)
    )

    selected = np.empty(
        n_select,
        dtype=np.int64,
    )

    selected[0] = first

    # For every candidate point, store its current distance
    # to the nearest selected point.
    min_dist = np.linalg.norm(
        points - points[first],
        axis=1,
    )

    min_dist[first] = 0.0

    # --------------------------------------------------------
    # Iteratively add the point farthest from the current
    # selected set.
    # --------------------------------------------------------

    for k in range(1, n_select):

        next_idx = int(
            np.argmax(min_dist)
        )

        selected[k] = next_idx

        new_dist = np.linalg.norm(
            points - points[next_idx],
            axis=1,
        )

        min_dist = np.minimum(
            min_dist,
            new_dist,
        )

        min_dist[selected[:k + 1]] = 0.0

        if (
            (k + 1) % 250 == 0
            or (k + 1) == n_select
        ):
            print(
                f"    selected "
                f"{k + 1:,} / "
                f"{n_select:,}"
            )

    return selected


# ============================================================
# Load master cortex
# ============================================================

print("=" * 78)
print("BUILD SOURCE SPACE CANDIDATE: P = 2,500")
print("=" * 78)

print(f"\nInput:\n{INPUT_CSV}")

df = pd.read_csv(INPUT_CSV)

if len(df) != 25_000:
    raise RuntimeError(
        f"Expected 25,000 master vertices, "
        f"found {len(df):,}."
    )

print(
    f"\nMaster cortical vertices: "
    f"{len(df):,}"
)


# ============================================================
# Determine hemisphere
# ============================================================

parcel = df["parcel"].astype(str)

lh_mask = parcel.str.endswith(
    "_LH",
    na=False,
)

rh_mask = parcel.str.endswith(
    "_RH",
    na=False,
)

if not np.all(lh_mask | rh_mask):
    raise RuntimeError(
        "Some vertices do not have a valid "
        "LH/RH parcel suffix."
    )

n_lh_master = int(lh_mask.sum())
n_rh_master = int(rh_mask.sum())

print(
    f"  LH: {n_lh_master:,}"
)

print(
    f"  RH: {n_rh_master:,}"
)


# ============================================================
# Allocate P proportionally between hemispheres
# ============================================================

p_lh = int(
    round(
        TARGET_P
        * n_lh_master
        / len(df)
    )
)

p_rh = TARGET_P - p_lh

print("\nTarget source counts:")

print(
    f"  LH: {p_lh:,}"
)

print(
    f"  RH: {p_rh:,}"
)

print(
    f"  Total: "
    f"{p_lh + p_rh:,}"
)


# ============================================================
# Extract hemisphere data
# ============================================================

lh_df = (
    df.loc[lh_mask]
    .copy()
    .reset_index(drop=True)
)

rh_df = (
    df.loc[rh_mask]
    .copy()
    .reset_index(drop=True)
)

lh_xyz = (
    lh_df[COORD_COLS]
    .to_numpy(dtype=float)
)

rh_xyz = (
    rh_df[COORD_COLS]
    .to_numpy(dtype=float)
)


# ============================================================
# Sample LH
# ============================================================

print("\n" + "=" * 78)
print("LEFT HEMISPHERE FPS")
print("=" * 78)

lh_selected_local = (
    farthest_point_sampling(
        lh_xyz,
        p_lh,
    )
)

lh_selected = (
    lh_df
    .iloc[lh_selected_local]
    .copy()
)

lh_selected["hemisphere"] = "LH"


# ============================================================
# Sample RH
# ============================================================

print("\n" + "=" * 78)
print("RIGHT HEMISPHERE FPS")
print("=" * 78)

rh_selected_local = (
    farthest_point_sampling(
        rh_xyz,
        p_rh,
    )
)

rh_selected = (
    rh_df
    .iloc[rh_selected_local]
    .copy()
)

rh_selected["hemisphere"] = "RH"


# ============================================================
# Combine
# ============================================================

selected = pd.concat(
    [
        lh_selected,
        rh_selected,
    ],
    ignore_index=True,
)

selected["source_index"] = np.arange(
    len(selected),
    dtype=int,
)


# ============================================================
# Basic checks
# ============================================================

print("\n" + "=" * 78)
print("SOURCE-SPACE CHECKS")
print("=" * 78)

print(
    f"\nSelected sources : "
    f"{len(selected):,}"
)

print(
    f"LH sources       : "
    f"{(selected['hemisphere'] == 'LH').sum():,}"
)

print(
    f"RH sources       : "
    f"{(selected['hemisphere'] == 'RH').sum():,}"
)

print(
    f"Unique master IDs: "
    f"{selected['vertex'].nunique():,}"
)

if len(selected) != TARGET_P:
    raise RuntimeError(
        "Incorrect final source count."
    )

if selected["vertex"].nunique() != TARGET_P:
    raise RuntimeError(
        "Duplicate master cortical vertices detected."
    )


# ============================================================
# Nearest-neighbor spacing
# ============================================================

print("\n" + "=" * 78)
print("SOURCE SPACING")
print("=" * 78)


def nearest_neighbor_spacing(points):
    """
    Calculate Euclidean nearest-neighbor spacing.
    """

    distances = cdist(
        points,
        points,
    )

    np.fill_diagonal(
        distances,
        np.inf,
    )

    return distances.min(axis=1)


for hemi_name in ["LH", "RH"]:

    hemi = selected[
        selected["hemisphere"]
        == hemi_name
    ]

    xyz = hemi[
        COORD_COLS
    ].to_numpy(dtype=float)

    nn = nearest_neighbor_spacing(xyz)

    print(
        f"\n{hemi_name}:"
    )

    print(
        f"  sources : "
        f"{len(xyz):,}"
    )

    print(
        f"  minimum : "
        f"{nn.min():.3f} mm"
    )

    print(
        f"  median  : "
        f"{np.median(nn):.3f} mm"
    )

    print(
        f"  mean    : "
        f"{nn.mean():.3f} mm"
    )

    print(
        f"  95th    : "
        f"{np.percentile(nn, 95):.3f} mm"
    )

    print(
        f"  maximum : "
        f"{nn.max():.3f} mm"
    )


# ============================================================
# Save
# ============================================================

# Put source_index first for readability.
column_order = [
    "source_index",
    "vertex",
    "fsaverage_vertex",
    "hemisphere",
    "parcel",
    "mni152_r",
    "mni152_a",
    "mni152_s",
]

selected = selected[column_order]

selected.to_csv(
    OUTPUT_CSV,
    index=False,
)

print("\n" + "=" * 78)
print("OUTPUT")
print("=" * 78)

print(
    f"\nSaved:\n{OUTPUT_CSV}"
)

print("\nP = 2,500 SOURCE CANDIDATE: CREATED")

print("=" * 78)