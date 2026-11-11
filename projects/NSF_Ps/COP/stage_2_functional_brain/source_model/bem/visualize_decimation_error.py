from pathlib import Path
import pyvista as pv


ROOT = Path(__file__).resolve().parent

ERROR_MAP = (
    ROOT
    / "surfaces_mne"
    / "inner_skull_20480_error_map.vtk"
)

mesh = pv.read(ERROR_MAP)

plotter = pv.Plotter()

plotter.add_mesh(
    mesh,
    scalars="decimation_error_mm",
    show_edges=False,
    scalar_bar_args={
        "title": "Master -> Reduced Error (mm)"
    },
)

plotter.add_axes()
plotter.show_grid()

plotter.show()