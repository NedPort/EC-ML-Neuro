from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


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


# ============================================================
# Settings
# ============================================================

TARGETS = [2500, 5000, 10000]

MAX_P = max(TARGETS)

COORD_COLS = [
    "mni152_r",
    "mni152_a",
    "mni152_s",
]


# ============================================================
# Ordered farthest-point sampling
# ============================================================

def farthest_point_order(points, n_select):
    """
    Produce one deterministic ordered farthest-point sample.

    The important property is:

        first 1250 points
            subset of
        first 2500 points
            subset of
        first 5000 points

    Therefore progressively larger source spaces can be built
    from the same ordered hierarchy.

    Parameters
    ----------
    points : ndarray, shape (N, 3)
        Candidate physical MNI coordinates.

    n_select : int
        Maximum number of points required.

    Returns
    -------
    selected : ndarray, shape (n_select,)
        Ordered indices into points.
    """

    points = np.asarray(
        points,
        dtype=np.float64,
    )

    n_points = len(points)

    if n_select > n_points:
        raise ValueError(
            "Requested more samples than available points."
        )

    # --------------------------------------------------------
    # Deterministic first point
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

    # Distance from each point to its nearest selected source.
    min_dist = np.linalg.norm(
        points - points[first],
        axis=1,
    )

    min_dist[first] = 0.0

    # --------------------------------------------------------
    # Progressive FPS
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
            (k + 1) % 500 == 0
            or (k + 1) == n_select
        ):
            print(
                f"    selected "
                f"{k + 1:,} / {n_select:,}"
            )

    return selected


# ============================================================
# Nearest-neighbor spacing
# ============================================================

def nearest_neighbor_spacing(points):
    """
    Efficient Euclidean nearest-neighbor spacing.

    k=2 is used because the closest point returned by the
    KD-tree is the point itself.
    """

    points = np.asarray(
        points,
        dtype=np.float64,
    )

    tree = cKDTree(points)

    distances, _ = tree.query(
        points,
        k=2,
        workers=-1,
    )

    return distances[:, 1]


# ============================================================
# Load master cortex
# ============================================================

print("=" * 78)
print("BUILD NESTED CORTICAL SOURCE SPACES")
print("=" * 78)

print(f"\nInput:\n{INPUT_CSV}")

df = pd.read_csv(INPUT_CSV)

if len(df) != 25_000:
    raise RuntimeError(
        f"Expected 25,000 master vertices, "
        f"found {len(df):,}."
    )

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
        "Some vertices do not have LH/RH assignment."
    )

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

n_master = len(df)
n_lh = len(lh_df)
n_rh = len(rh_df)

print(f"\nMaster vertices : {n_master:,}")
print(f"LH vertices     : {n_lh:,}")
print(f"RH vertices     : {n_rh:,}")


# ============================================================
# Determine maximum hemisphere sample sizes
# ============================================================

max_lh = int(
    round(
        MAX_P
        * n_lh
        / n_master
    )
)

max_rh = MAX_P - max_lh

print("\nMaximum hierarchy size:")
print(f"  Total : {MAX_P:,}")
print(f"  LH    : {max_lh:,}")
print(f"  RH    : {max_rh:,}")


# ============================================================
# Build ONE ordered hierarchy per hemisphere
# ============================================================

print("\n" + "=" * 78)
print("LEFT HEMISPHERE ORDERED FPS")
print("=" * 78)

lh_order = farthest_point_order(
    lh_xyz,
    max_lh,
)

print("\n" + "=" * 78)
print("RIGHT HEMISPHERE ORDERED FPS")
print("=" * 78)

rh_order = farthest_point_order(
    rh_xyz,
    max_rh,
)


# ============================================================
# Create candidate source spaces
# ============================================================

candidate_sets = {}

for target_p in TARGETS:

    print("\n" + "=" * 78)
    print(f"BUILDING P = {target_p:,}")
    print("=" * 78)

    p_lh = int(
        round(
            target_p
            * n_lh
            / n_master
        )
    )

    p_rh = target_p - p_lh

    print(f"\nTarget LH : {p_lh:,}")
    print(f"Target RH : {p_rh:,}")

    # --------------------------------------------------------
    # Take prefixes from the SAME ordered hierarchy
    # --------------------------------------------------------

    lh_selected = (
        lh_df
        .iloc[lh_order[:p_lh]]
        .copy()
    )

    rh_selected = (
        rh_df
        .iloc[rh_order[:p_rh]]
        .copy()
    )

    lh_selected["hemisphere"] = "LH"
    rh_selected["hemisphere"] = "RH"

    selected = pd.concat(
        [
            lh_selected,
            rh_selected,
        ],
        ignore_index=True,
    )

    if len(selected) != target_p:
        raise RuntimeError(
            f"P={target_p}: incorrect source count."
        )

    if selected["vertex"].nunique() != target_p:
        raise RuntimeError(
            f"P={target_p}: duplicate master IDs."
        )

    # Source index is specific to this candidate space.
    selected["source_index"] = np.arange(
        target_p,
        dtype=int,
    )

    # --------------------------------------------------------
    # Spacing statistics
    # --------------------------------------------------------

    print("\nNearest-neighbor spacing:")

    for hemi_name in ["LH", "RH"]:

        hemi_xyz = (
            selected.loc[
                selected["hemisphere"] == hemi_name,
                COORD_COLS,
            ]
            .to_numpy(dtype=float)
        )

        nn = nearest_neighbor_spacing(
            hemi_xyz
        )

        print(f"\n  {hemi_name}:")
        print(
            f"    sources : {len(hemi_xyz):,}"
        )
        print(
            f"    minimum : {nn.min():.3f} mm"
        )
        print(
            f"    median  : {np.median(nn):.3f} mm"
        )
        print(
            f"    mean    : {nn.mean():.3f} mm"
        )
        print(
            f"    95th    : "
            f"{np.percentile(nn, 95):.3f} mm"
        )
        print(
            f"    maximum : {nn.max():.3f} mm"
        )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

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

    output_path = (
        OUTPUT_DIR
        / f"source_space_p{target_p}.csv"
    )

    selected.to_csv(
        output_path,
        index=False,
    )

    print(f"\nSaved:\n{output_path}")

    candidate_sets[target_p] = set(
        selected["vertex"].astype(int)
    )


# ============================================================
# Explicit nesting validation
# ============================================================

print("\n" + "=" * 78)
print("NESTING VALIDATION")
print("=" * 78)

s2500 = candidate_sets[2500]
s5000 = candidate_sets[5000]
s10000 = candidate_sets[10000]

check_2500_5000 = s2500.issubset(
    s5000
)

check_5000_10000 = s5000.issubset(
    s10000
)

check_2500_10000 = s2500.issubset(
    s10000
)

print(
    f"\nP2500 subset P5000  : "
    f"{check_2500_5000}"
)

print(
    f"P5000 subset P10000 : "
    f"{check_5000_10000}"
)

print(
    f"P2500 subset P10000 : "
    f"{check_2500_10000}"
)

if not (
    check_2500_5000
    and check_5000_10000
    and check_2500_10000
):
    raise RuntimeError(
        "Nested hierarchy validation failed."
    )


# ============================================================
# Compare with the earlier standalone P=2500 file
# ============================================================

old_p2500 = (
    OUTPUT_DIR
    / "source_space_p2500.csv"
)

# At this point this path has already been overwritten by the
# hierarchy-generated P2500 candidate. Therefore this script
# intentionally establishes the nested hierarchy as the
# authoritative candidate set from now on.


# ============================================================
# Final summary
# ============================================================

print("\n" + "=" * 78)
print("FINAL SUMMARY")
print("=" * 78)

print("""
Nested cortical source spaces successfully created:

    P = 2,500
        subset of
    P = 5,000
        subset of
    P = 10,000
        subset of
    25,000 master cortical vertices

The ico4 BEM geometry has NOT been modified.

All selected source coordinates remain original master
MNI152 cortical coordinates.
""")

print("NESTED SOURCE-SPACE HIERARCHY: PASS")
print("=" * 78)