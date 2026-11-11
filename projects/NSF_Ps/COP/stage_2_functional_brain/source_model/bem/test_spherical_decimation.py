from pathlib import Path

import mne
import pyvista as pv


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent

MASTER_DIR = ROOT / "surfaces_master"
OUTPUT_DIR = ROOT / "surfaces_mne"

TARGET_TRIANGLES = 20_480

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
    output_path = OUTPUT_DIR / f"{name}_20480.vtk"

    print("\n" + "=" * 70)
    print(f"SPHERICAL DECIMATION: {name.upper()}")
    print("=" * 70)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Master surface not found:\n{input_path}"
        )

    # --------------------------------------------------------
    # Load master
    # --------------------------------------------------------

    mesh = pv.read(input_path).triangulate()

    points = mesh.points.copy()
    triangles = mesh.faces.reshape(-1, 4)[:, 1:].copy()

    print("\nMASTER")
    print(f"  Vertices : {len(points):,}")
    print(f"  Triangles: {len(triangles):,}")

    # --------------------------------------------------------
    # Spherical decimation
    # --------------------------------------------------------

    print("\nMNE / FreeSurfer spherical decimation")
    print(f"  Target triangles: {TARGET_TRIANGLES:,}")

    rr_dec, tris_dec = mne.decimate_surface(
        points,
        triangles,
        TARGET_TRIANGLES,
        method="sphere",
    )

    print("\nREDUCED")
    print(f"  Vertices : {len(rr_dec):,}")
    print(f"  Triangles: {len(tris_dec):,}")

    # --------------------------------------------------------
    # Triangle-count validation
    # --------------------------------------------------------

    if len(tris_dec) != TARGET_TRIANGLES:
        raise RuntimeError(
            f"{name}: expected {TARGET_TRIANGLES:,} triangles, "
            f"got {len(tris_dec):,}"
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
    # Save computational candidate
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

print("=" * 70)
print("BEM SPHERICAL DECIMATION")
print("=" * 70)

print("\nIMPORTANT:")
print("  Master surfaces are READ ONLY.")
print("  No files inside surfaces_master/ will be modified.")
print(f"  Target = {TARGET_TRIANGLES:,} triangles per surface.")


outputs = []

for surface_name in SURFACES:
    output = decimate_surface(surface_name)
    outputs.append(output)


print("\n" + "=" * 70)
print("DECIMATION COMPLETE")
print("=" * 70)

for output in outputs:
    print(f"  {output.name}")

print("\nMaster surfaces were NOT modified.")
print("Reduced surfaces are CANDIDATES pending validation.")
print("=" * 70)