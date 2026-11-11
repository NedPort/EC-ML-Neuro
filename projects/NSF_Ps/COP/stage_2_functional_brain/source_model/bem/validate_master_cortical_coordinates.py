from pathlib import Path

import numpy as np
import pandas as pd
import pyvista as pv
from scipy.spatial import cKDTree


# ============================================================
# Paths
# ============================================================

BEM_ROOT = Path(__file__).resolve().parent
COP_ROOT = BEM_ROOT.parents[2]

ANATOMY_DIR = COP_ROOT / "hm_icbm152"

CSV_PATH = ANATOMY_DIR / "brain_vertex_coordinates.csv"
HIGH_CORTEX_PATH = ANATOMY_DIR / "cortex_pial_high_mni152.obj"

INNER_SKULL_PATH = (
    BEM_ROOT
    / "surfaces_mne_ico4"
    / "inner_skull_5120.vtk"
)


# ============================================================
# Header
# ============================================================

print("=" * 78)
print("MASTER CORTICAL COORDINATE VALIDATION")
print("=" * 78)

print("\nFiles:")
print(f"  CSV          : {CSV_PATH}")
print(f"  High cortex  : {HIGH_CORTEX_PATH}")
print(f"  Inner skull  : {INNER_SKULL_PATH}")


# ============================================================
# File checks
# ============================================================

for path in [CSV_PATH, HIGH_CORTEX_PATH, INNER_SKULL_PATH]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file:\n{path}")

print("\nFile check: PASS")


# ============================================================
# Load CSV
# ============================================================

print("\n" + "=" * 78)
print("1. CSV STRUCTURE")
print("=" * 78)

df = pd.read_csv(CSV_PATH)

print(f"\nRows    : {len(df):,}")
print(f"Columns : {len(df.columns)}")
print(f"Names   : {list(df.columns)}")

required = [
    "vertex",
    "fsaverage_vertex",
    "parcel",
    "mni152_r",
    "mni152_a",
    "mni152_s",
]

missing = [c for c in required if c not in df.columns]

if missing:
    raise RuntimeError(
        f"Missing required columns: {missing}"
    )

print("\nRequired columns: PASS")


# ============================================================
# Vertex IDs
# ============================================================

print("\n" + "=" * 78)
print("2. VERTEX IDENTIFIERS")
print("=" * 78)

vertex_ids = df["vertex"].to_numpy()

print(f"\nUnique vertex IDs : {df['vertex'].nunique():,}")
print(f"Minimum ID        : {vertex_ids.min()}")
print(f"Maximum ID        : {vertex_ids.max()}")

expected_ids = np.arange(len(df))

sequential = np.array_equal(vertex_ids, expected_ids)

print(f"Sequential 0..N-1 : {sequential}")

if len(df) == 25_000:
    print("Row count 25,000  : PASS")
else:
    print("Row count 25,000  : WARNING")


# ============================================================
# Physical MNI coordinates
# ============================================================

print("\n" + "=" * 78)
print("3. MNI152 PHYSICAL COORDINATES")
print("=" * 78)

xyz = df[
    ["mni152_r", "mni152_a", "mni152_s"]
].to_numpy(dtype=float)

finite_mask = np.isfinite(xyz).all(axis=1)

print(
    f"\nFinite coordinate rows : "
    f"{finite_mask.sum():,} / {len(xyz):,}"
)

if not finite_mask.all():
    raise RuntimeError(
        "Non-finite cortical coordinates detected."
    )

unique_xyz = np.unique(xyz, axis=0)

print(f"Unique XYZ rows        : {len(unique_xyz):,}")

duplicate_count = len(xyz) - len(unique_xyz)

print(f"Duplicate XYZ rows     : {duplicate_count:,}")

print("\nMNI152 bounds:")
print(f"  x: {xyz[:, 0].min():.3f} to {xyz[:, 0].max():.3f}")
print(f"  y: {xyz[:, 1].min():.3f} to {xyz[:, 1].max():.3f}")
print(f"  z: {xyz[:, 2].min():.3f} to {xyz[:, 2].max():.3f}")

print("\nCoordinate center:")
center = xyz.mean(axis=0)

print(
    f"  ({center[0]:.3f}, "
    f"{center[1]:.3f}, "
    f"{center[2]:.3f})"
)


# ============================================================
# Hemisphere assignment
# ============================================================

print("\n" + "=" * 78)
print("4. HEMISPHERE ASSIGNMENT")
print("=" * 78)

parcel = df["parcel"].astype(str)

lh_mask = parcel.str.endswith("_LH", na=False)
rh_mask = parcel.str.endswith("_RH", na=False)

known_hemi = lh_mask | rh_mask
unknown_hemi = ~known_hemi

print(f"\nLH vertices      : {lh_mask.sum():,}")
print(f"RH vertices      : {rh_mask.sum():,}")
print(f"Unknown vertices : {unknown_hemi.sum():,}")

if unknown_hemi.any():

    print("\nUnknown hemisphere parcel examples:")

    examples = (
        parcel[unknown_hemi]
        .drop_duplicates()
        .head(20)
        .tolist()
    )

    for item in examples:
        print(f"  {item}")


# ============================================================
# Parcel structure
# ============================================================

print("\n" + "=" * 78)
print("5. PARCELLATION")
print("=" * 78)

n_parcels = df["parcel"].nunique(dropna=False)

print(f"\nUnique parcel labels : {n_parcels:,}")

parcel_counts = (
    df.groupby("parcel", dropna=False)
    .size()
    .sort_values()
)

print("\nSmallest parcels:")
print(parcel_counts.head(10).to_string())

print("\nLargest parcels:")
print(parcel_counts.tail(10).to_string())


# ============================================================
# fsaverage mapping
# ============================================================

print("\n" + "=" * 78)
print("6. FSAVERAGE VERTEX MAPPING")
print("=" * 78)

fs_vertices = df["fsaverage_vertex"]

print(f"\nFinite values      : {fs_vertices.notna().sum():,}")
print(f"Unique values      : {fs_vertices.nunique(dropna=True):,}")

if fs_vertices.notna().any():
    print(f"Minimum value      : {fs_vertices.min()}")
    print(f"Maximum value      : {fs_vertices.max()}")

duplicate_fs = (
    fs_vertices.notna().sum()
    - fs_vertices.nunique(dropna=True)
)

print(f"Duplicate mappings : {duplicate_fs:,}")


# ============================================================
# Load high-resolution physical cortex
# ============================================================

print("\n" + "=" * 78)
print("7. DISTANCE TO HIGH-RESOLUTION MNI CORTEX")
print("=" * 78)

high_cortex = (
    pv.read(HIGH_CORTEX_PATH)
    .triangulate()
    .clean()
)

high_xyz = np.asarray(high_cortex.points, dtype=float)

print(f"\nHigh-resolution cortex vertices : {len(high_xyz):,}")

print("\nBuilding nearest-neighbor tree...")

tree = cKDTree(high_xyz)

distances, nearest_indices = tree.query(
    xyz,
    k=1,
    workers=-1,
)

print("\n25k point -> nearest high-resolution cortex vertex:")
print(f"  minimum : {distances.min():.6f} mm")
print(f"  median  : {np.median(distances):.6f} mm")
print(f"  mean    : {distances.mean():.6f} mm")
print(f"  95th    : {np.percentile(distances, 95):.6f} mm")
print(f"  99th    : {np.percentile(distances, 99):.6f} mm")
print(f"  maximum : {distances.max():.6f} mm")

thresholds = [
    0.1,
    0.5,
    1.0,
    2.0,
    3.0,
    5.0,
]

print("\nDistance thresholds:")

for threshold in thresholds:

    count = np.sum(distances <= threshold)
    pct = 100.0 * count / len(distances)

    print(
        f"  <= {threshold:3.1f} mm : "
        f"{count:6,d} "
        f"({pct:7.3f}%)"
    )


# ============================================================
# Worst matches
# ============================================================

print("\nWorst 10 nearest-cortex distances:")

worst = np.argsort(distances)[-10:][::-1]

for idx in worst:

    p = xyz[idx]

    print(
        f"  CSV vertex {int(df.iloc[idx]['vertex']):6d} | "
        f"d={distances[idx]:8.4f} mm | "
        f"xyz=({p[0]:8.3f}, {p[1]:8.3f}, {p[2]:8.3f}) | "
        f"parcel={df.iloc[idx]['parcel']}"
    )


# ============================================================
# Inner-skull containment
# ============================================================

print("\n" + "=" * 78)
print("8. ICO4 INNER-SKULL CONTAINMENT")
print("=" * 78)

inner_skull = (
    pv.read(INNER_SKULL_PATH)
    .triangulate()
    .clean()
)

print(
    f"\nInner-skull mesh: "
    f"{inner_skull.n_points:,} vertices / "
    f"{inner_skull.n_cells:,} triangles"
)

# Create point cloud from the 25k MNI coordinates.
point_cloud = pv.PolyData(xyz)

selection = point_cloud.select_enclosed_points(
    inner_skull,
    tolerance=0.0,
    check_surface=True,
)

inside = np.asarray(
    selection["SelectedPoints"]
).astype(bool)

n_inside = inside.sum()
n_outside = len(inside) - n_inside

print(f"\nInside inner skull  : {n_inside:,}")
print(f"Outside inner skull : {n_outside:,}")
print(
    f"Containment         : "
    f"{100.0 * n_inside / len(inside):.6f}%"
)

if n_outside > 0:

    print("\nFirst outside points:")

    outside_indices = np.where(~inside)[0][:20]

    for idx in outside_indices:

        p = xyz[idx]

        print(
            f"  vertex={int(df.iloc[idx]['vertex']):6d} | "
            f"xyz=({p[0]:8.3f}, "
            f"{p[1]:8.3f}, "
            f"{p[2]:8.3f}) | "
            f"parcel={df.iloc[idx]['parcel']}"
        )


# ============================================================
# Final summary
# ============================================================

print("\n" + "=" * 78)
print("SUMMARY")
print("=" * 78)

print(f"""
Master computational vertices : {len(df):,}

LH vertices                   : {lh_mask.sum():,}
RH vertices                   : {rh_mask.sum():,}
Unknown hemisphere            : {unknown_hemi.sum():,}

Unique parcels                : {n_parcels:,}

Finite MNI coordinates        : {finite_mask.sum():,}/{len(df):,}
Unique MNI coordinates        : {len(unique_xyz):,}/{len(df):,}

Distance to high-res cortex:
    median                    : {np.median(distances):.6f} mm
    95th percentile           : {np.percentile(distances, 95):.6f} mm
    maximum                   : {distances.max():.6f} mm

Inside ico4 inner skull       : {n_inside:,}/{len(inside):,}
Outside ico4 inner skull      : {n_outside:,}
""")

if (
    len(df) == 25_000
    and finite_mask.all()
    and duplicate_count == 0
    and unknown_hemi.sum() == 0
    and n_outside == 0
):
    print("BASIC MASTER CORTICAL COORDINATE CHECKS: PASS")
else:
    print(
        "BASIC MASTER CORTICAL COORDINATE CHECKS: "
        "REVIEW REQUIRED"
    )

print("=" * 78)