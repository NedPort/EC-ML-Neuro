from pathlib import Path

import mne
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent

# High-resolution validated master surfaces
MASTER_DIR = ROOT / "surfaces_master"

# NEW directory.
# We deliberately keep ico4 separate from our validated ico5
# surfaces in surfaces_mne/.
OUTPUT_DIR = ROOT / "surfaces_mne_ico4"

TARGET_TRIANGLES = 5_120

SURFACES = [
    "inner_skull",
    "outer_skull",
    "outer_skin",
]


# ============================================================
# Decimation
# ============================================================

def decimate_surface(name):

    input_path = MASTER_DIR / f"{name}.vtk"
    output_path = OUTPUT_DIR / f"{name}_5120.vtk"

    print("\n" + "=" * 72)
    print(f"ICO4 SPHERICAL DECIMATION: {name.upper()}")
    print("=" * 72)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Master surface not found:\n{input_path}"
        )

    # --------------------------------------------------------
    # Load master surface
    # --------------------------------------------------------

    mesh = pv.read(input_path)
    mesh = mesh.triangulate().clean()

    points = mesh.points.copy()
    triangles = mesh.faces.reshape(-1, 4)[:, 1:].copy()

    print("\nMASTER")
    print(f"  Vertices : {len(points):,}")
    print(f"  Triangles: {len(triangles):,}")

    # --------------------------------------------------------
    # MNE / FreeSurfer spherical decimation
    # --------------------------------------------------------

    print("\nMNE / FreeSurfer spherical decimation")
    print(f"  Target triangles: {TARGET_TRIANGLES:,}")

    rr_dec, tris_dec = mne.decimate_surface(
        points,
        triangles,
        TARGET_TRIANGLES,
        method="sphere",
    )

    print("\nICO4 CANDIDATE")
    print(f"  Vertices : {len(rr_dec):,}")
    print(f"  Triangles: {len(tris_dec):,}")

    # --------------------------------------------------------
    # Sanity checks
    # --------------------------------------------------------

    if len(tris_dec) != TARGET_TRIANGLES:
        raise RuntimeError(
            f"{name}: expected {TARGET_TRIANGLES:,} triangles, "
            f"but got {len(tris_dec):,}"
        )

    expected_vertices = 2_562

    if len(rr_dec) != expected_vertices:
        print(
            "\nWARNING:"
            f" Expected approximately {expected_vertices:,} vertices, "
            f"but got {len(rr_dec):,}."
        )

    # --------------------------------------------------------
    # Convert to PyVista
    # --------------------------------------------------------

    faces_pv = []

    for tri in tris_dec:
        faces_pv.extend(
            [
                3,
                int(tri[0]),
                int(tri[1]),
                int(tri[2]),
            ]
        )

    reduced_mesh = pv.PolyData(
        rr_dec,
        faces_pv,
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    reduced_mesh.save(output_path)

    print("\nSAVED")
    print(f"  {output_path}")

    return output_path


# ============================================================
# Main
# ============================================================

print("=" * 72)
print("ICO4 BEM SPHERICAL DECIMATION")
print("=" * 72)

print("\nIMPORTANT:")
print("  High-resolution master surfaces are READ ONLY.")
print("  Existing ico5 surfaces are NOT modified.")
print("  ico4 candidates are written to surfaces_mne_ico4/.")
print(f"  Target = {TARGET_TRIANGLES:,} triangles per surface.")


outputs = []

for surface_name in SURFACES:
    output = decimate_surface(surface_name)
    outputs.append(output)


print("\n" + "=" * 72)
print("ICO4 DECIMATION COMPLETE")
print("=" * 72)

for output in outputs:
    print(f"  {output.name}")

print("\nMaster surfaces were NOT modified.")
print("Existing ico5 surfaces were NOT modified.")
print("ico4 surfaces are CANDIDATES pending validation.")
print("=" * 72)