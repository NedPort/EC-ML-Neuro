from pathlib import Path

import mne
import numpy as np


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent

BEM_MODEL_PATH = (
    ROOT
    / "icbm152-ico4-bem.fif"
)

BEM_SOLUTION_PATH = (
    ROOT
    / "icbm152-ico4-bem-sol.fif"
)


# ============================================================
# Header
# ============================================================

print()
print("=" * 72)
print("ICO4 THREE-LAYER BEM NUMERICAL SOLUTION")
print("=" * 72)

print("\nInput BEM surface model:")
print(BEM_MODEL_PATH)

print("\nOutput BEM solution:")
print(BEM_SOLUTION_PATH)


# ============================================================
# Input check
# ============================================================

if not BEM_MODEL_PATH.exists():

    raise FileNotFoundError(
        "Validated ico4 BEM surface model "
        "was not found:\n"
        f"{BEM_MODEL_PATH}"
    )


# ============================================================
# Read validated surface model
# ============================================================

print()
print("=" * 72)
print("READING VALIDATED ICO4 BEM MODEL")
print("=" * 72)

bem_model = mne.read_bem_surfaces(
    BEM_MODEL_PATH,
    verbose=True,
)

print(
    f"\nNumber of surfaces: "
    f"{len(bem_model)}"
)


# ============================================================
# Pre-solution sanity check
# ============================================================

print()
print("=" * 72)
print("PRE-SOLUTION SURFACE CHECK")
print("=" * 72)


for i, surf in enumerate(
    bem_model,
    start=1,
):

    rr = np.asarray(
        surf["rr"]
    )

    tris = np.asarray(
        surf["tris"]
    )

    sigma = surf.get(
        "sigma",
        np.nan,
    )

    print()
    print(f"Surface {i}")

    print(
        f"  conductivity : "
        f"{sigma} S/m"
    )

    print(
        f"  vertices     : "
        f"{len(rr):,}"
    )

    print(
        f"  triangles    : "
        f"{len(tris):,}"
    )

    if len(rr) != 2_562:
        raise RuntimeError(
            f"Surface {i}: expected "
            f"2,562 vertices."
        )

    if len(tris) != 5_120:
        raise RuntimeError(
            f"Surface {i}: expected "
            f"5,120 triangles."
        )


# ============================================================
# Compute numerical BEM solution
# ============================================================

print()
print("=" * 72)
print("COMPUTING NUMERICAL BEM SOLUTION")
print("=" * 72)

print(
    "\nThis is the computationally intensive step."
)

print(
    "No geometry is being modified."
)

print()


try:

    bem_solution = mne.make_bem_solution(
        bem_model,
        verbose=True,
    )

except Exception as exc:

    print()
    print("=" * 72)
    print("BEM SOLUTION: FAIL")
    print("=" * 72)

    print("\nMNE could not compute the BEM solution.")

    print("\nError:")
    print(repr(exc))

    print(
        "\nDo NOT modify the validated "
        "surfaces based only on this failure."
    )

    raise


# ============================================================
# Basic solution inspection
# ============================================================

print()
print()
print("=" * 72)
print("BEM SOLUTION COMPUTED")
print("=" * 72)

print("\nSolution type:")
print(type(bem_solution))

print("\nBEM solution summary:")
print(bem_solution)


# ============================================================
# Numerical sanity checks
# ============================================================

print()
print("=" * 72)
print("NUMERICAL SANITY CHECK")
print("=" * 72)


# MNE BEM solution normally stores the numerical matrix
# under the "solution" entry.
if "solution" not in bem_solution:

    raise RuntimeError(
        "BEM solution does not contain "
        "the expected 'solution' matrix."
    )


solution_matrix = np.asarray(
    bem_solution["solution"]
)


print(
    f"\nSolution matrix shape: "
    f"{solution_matrix.shape}"
)

print(
    f"Matrix dtype         : "
    f"{solution_matrix.dtype}"
)


finite_mask = np.isfinite(
    solution_matrix
)

finite_count = int(
    np.count_nonzero(
        finite_mask
    )
)

total_count = int(
    solution_matrix.size
)


print(
    f"Finite entries       : "
    f"{finite_count:,} / "
    f"{total_count:,}"
)


if finite_count != total_count:

    raise RuntimeError(
        "BEM solution contains NaN "
        "or infinite values."
    )


print(
    f"Minimum value        : "
    f"{solution_matrix.min():.6e}"
)

print(
    f"Maximum value        : "
    f"{solution_matrix.max():.6e}"
)

print(
    f"Mean value           : "
    f"{solution_matrix.mean():.6e}"
)

print(
    f"Std value            : "
    f"{solution_matrix.std():.6e}"
)


# ============================================================
# Save numerical BEM solution
# ============================================================

print()
print("=" * 72)
print("SAVING NUMERICAL BEM SOLUTION")
print("=" * 72)


mne.write_bem_solution(
    BEM_SOLUTION_PATH,
    bem_solution,
    overwrite=True,
)


print("\nSaved:")
print(BEM_SOLUTION_PATH)


# ============================================================
# Read-back validation
# ============================================================

print()
print("=" * 72)
print("READ-BACK VALIDATION")
print("=" * 72)


bem_check = mne.read_bem_solution(
    BEM_SOLUTION_PATH,
    verbose=True,
)


if "solution" not in bem_check:

    raise RuntimeError(
        "Read-back BEM solution is missing "
        "the numerical solution matrix."
    )


check_matrix = np.asarray(
    bem_check["solution"]
)


print(
    f"\nRead-back matrix shape: "
    f"{check_matrix.shape}"
)


if check_matrix.shape != solution_matrix.shape:

    raise RuntimeError(
        "BEM solution matrix shape changed "
        "after writing and reading."
    )


if not np.all(
    np.isfinite(
        check_matrix
    )
):

    raise RuntimeError(
        "Read-back BEM solution contains "
        "NaN or infinite values."
    )


print(
    "Read-back finite values: PASS"
)


# ============================================================
# Final result
# ============================================================

print()
print("=" * 72)
print("ICO4 NUMERICAL BEM SOLUTION: PASS")
print("=" * 72)

print(
    "\nThe validated three-layer ico4 "
    "geometry was successfully converted "
    "into an MNE numerical BEM solution."
)

print("\nOutput:")
print(BEM_SOLUTION_PATH)

print(
    "\nNo BEM geometry was modified."
)

print(
    "\nNext scientific stage:"
)

print(
    "Validate the solution output and then "
    "prepare the cortical source space and "
    "EEG forward model."
)

print("=" * 72)