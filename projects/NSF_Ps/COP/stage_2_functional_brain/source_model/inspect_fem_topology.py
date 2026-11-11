from pathlib import Path

import nibabel as nib
import numpy as np


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


# ============================================================
# Tissue labels
# ============================================================

LABELS = {
    0: "background",
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
volume = np.asarray(img.dataobj, dtype=np.uint8)

print("Shape:", volume.shape)
print("Voxel size:", img.header.get_zooms()[:3])
print("Labels:", np.unique(volume))


# ============================================================
# 2. Count face-sharing adjacency
# ============================================================

print("\n============================================")
print("FACE-SHARING TISSUE ADJACENCY")
print("============================================")

# Dictionary:
# (smaller_label, larger_label) -> number of shared voxel faces
adjacency = {}

# Check neighbors along X, Y, and Z.
for axis in range(3):

    slicer_a = [slice(None)] * 3
    slicer_b = [slice(None)] * 3

    slicer_a[axis] = slice(0, -1)
    slicer_b[axis] = slice(1, None)

    a = volume[tuple(slicer_a)]
    b = volume[tuple(slicer_b)]

    # Only positions where neighboring labels differ
    different = a != b

    a_diff = a[different]
    b_diff = b[different]

    # Sort each pair so A-B and B-A are treated identically.
    low = np.minimum(a_diff, b_diff)
    high = np.maximum(a_diff, b_diff)

    pairs = np.column_stack((low, high))

    unique_pairs, counts = np.unique(
        pairs,
        axis=0,
        return_counts=True,
    )

    for pair, count in zip(unique_pairs, counts):

        key = (int(pair[0]), int(pair[1]))

        adjacency[key] = (
            adjacency.get(key, 0)
            + int(count)
        )


# ============================================================
# 3. Print all detected interfaces
# ============================================================

for (label_a, label_b), count in sorted(adjacency.items()):

    name_a = LABELS[label_a]
    name_b = LABELS[label_b]

    print(
        f"{name_a:>10} <-> {name_b:<10} "
        f": {count:,} shared faces"
    )


# ============================================================
# 4. Tissue-to-tissue adjacency matrix
# ============================================================

print("\n============================================")
print("TISSUE ADJACENCY MATRIX")
print("============================================")

tissue_labels = [1, 2, 3, 4, 5]
tissue_names = [LABELS[x] for x in tissue_labels]

matrix = np.zeros(
    (len(tissue_labels), len(tissue_labels)),
    dtype=np.int64,
)

for i, label_a in enumerate(tissue_labels):

    for j, label_b in enumerate(tissue_labels):

        if i == j:
            continue

        key = tuple(sorted((label_a, label_b)))

        matrix[i, j] = adjacency.get(key, 0)


header = "".join(
    f"{name:>12}"
    for name in [""] + tissue_names
)

print(header)

for i, name in enumerate(tissue_names):

    row = f"{name:>12}"

    for j in range(len(tissue_names)):
        row += f"{matrix[i, j]:>12,}"

    print(row)


# ============================================================
# 5. Expected vs unexpected contacts
# ============================================================

print("\n============================================")
print("TOPOLOGY SUMMARY")
print("============================================")

# Expected anatomical neighboring tissue pairs.
expected_pairs = {
    (1, 2),  # skin-bone
    (2, 3),  # bone-CSF
    (3, 4),  # CSF-gray
    (4, 5),  # gray-white
}

for pair in sorted(expected_pairs):

    count = adjacency.get(pair, 0)

    print(
        f"Expected: "
        f"{LABELS[pair[0]]} <-> {LABELS[pair[1]]}: "
        f"{count:,}"
    )


print("\nUnexpected direct tissue contacts:")

unexpected_found = False

for (label_a, label_b), count in sorted(adjacency.items()):

    # Ignore background interfaces here.
    if label_a == 0 or label_b == 0:
        continue

    pair = (label_a, label_b)

    if pair not in expected_pairs:

        unexpected_found = True

        print(
            f"  {LABELS[label_a]} <-> "
            f"{LABELS[label_b]}: "
            f"{count:,}"
        )


if not unexpected_found:
    print("  None")


# ============================================================
# 6. Background contact
# ============================================================

print("\n============================================")
print("BACKGROUND CONTACT")
print("============================================")

for label in tissue_labels:

    key = (0, label)

    count = adjacency.get(key, 0)

    print(
        f"background <-> {LABELS[label]:<5}: "
        f"{count:,}"
    )