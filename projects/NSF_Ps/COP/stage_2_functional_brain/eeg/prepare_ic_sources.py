from pathlib import Path

import mne
import numpy as np
import pandas as pd


# ============================================================
# Paths
# ============================================================

BASE_DIR = Path("stage_2_functional_brain/eeg")

ICA_PATH = (
    BASE_DIR
    / "ica_results"
    / "sub-1_ses-0_acq-train_run-0_ica.fif"
)

ICLABEL_CSV = (
    BASE_DIR
    / "ica_results"
    / "sub-1_ses-0_acq-train_run-0_iclabel.csv"
)

ELECTRODES_TSV = Path(
    "eeg_data/sub-1/ses-0/eeg/"
    "sub-1_ses-0_space-CapTrak_electrodes.tsv"
)

OUTPUT_DIR = BASE_DIR / "source_localization"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SENSOR_GEOMETRY_CSV = (
    OUTPUT_DIR
    / "sub-1_ses-0_captrak_sensor_geometry.csv"
)

SCALP_MAPS_CSV = (
    OUTPUT_DIR
    / "sub-1_ses-0_retained_ic_scalp_maps.csv"
)


# ============================================================
# 1. Load fitted ICA
# ============================================================

print("\nLoading ICA...")
ica = mne.preprocessing.read_ica(ICA_PATH)

ica_channels = list(ica.ch_names)

print(f"ICA channels     : {len(ica_channels)}")
print(f"ICA components   : {ica.n_components_}")


# ============================================================
# 2. Read final manual IC decisions
# ============================================================

print("\nLoading manual IC decisions...")
decisions = pd.read_csv(ICLABEL_CSV)

if "ManualDecision" not in decisions.columns:
    raise ValueError(
        "Could not find 'ManualDecision' column in ICLabel CSV."
    )

manual = (
    decisions["ManualDecision"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)

keep_ics = decisions.index[manual == "KEEP"].to_numpy(dtype=int)

print(f"KEEP components  : {len(keep_ics)}")
print(f"KEEP indices     : {keep_ics.tolist()}")

if len(keep_ics) != 44:
    raise RuntimeError(
        f"Expected 44 KEEP components, found {len(keep_ics)}."
    )


# ============================================================
# 3. Load actual CapTrak electrode coordinates
# ============================================================

print("\nLoading CapTrak electrode coordinates...")
electrodes = pd.read_csv(ELECTRODES_TSV, sep="\t")

required_columns = {"name", "x", "y", "z"}

missing_columns = required_columns - set(electrodes.columns)

if missing_columns:
    raise ValueError(
        f"Electrode TSV is missing columns: {missing_columns}"
    )

electrodes["name"] = electrodes["name"].astype(str)

print(f"CapTrak electrodes: {len(electrodes)}")


# ============================================================
# 4. Verify channel names
# ============================================================

captrak_names = electrodes["name"].tolist()

ica_set = set(ica_channels)
captrak_set = set(captrak_names)

missing_from_captrak = sorted(ica_set - captrak_set)
extra_in_captrak = sorted(captrak_set - ica_set)

print("\nChannel-name comparison:")
print(f"  Missing from CapTrak : {missing_from_captrak}")
print(f"  Extra in CapTrak     : {extra_in_captrak}")

if missing_from_captrak:
    raise RuntimeError(
        "Some ICA channels do not have CapTrak coordinates."
    )


# ============================================================
# 5. Reorder CapTrak coordinates to EXACT ICA channel order
# ============================================================

electrodes_indexed = electrodes.set_index("name")

electrodes_ordered = electrodes_indexed.loc[ica_channels].reset_index()

ordered_names = electrodes_ordered["name"].tolist()

if ordered_names != ica_channels:
    raise RuntimeError(
        "CapTrak channel order does not match ICA channel order."
    )

sensor_xyz = electrodes_ordered[
    ["x", "y", "z"]
].to_numpy(dtype=float)

if not np.all(np.isfinite(sensor_xyz)):
    raise RuntimeError(
        "Non-finite values found in CapTrak coordinates."
    )

print("\nChannel order successfully aligned.")

print("\nSensor coordinate matrix shape:")
print(sensor_xyz.shape)

print("\nCoordinate ranges [m]:")
print(
    f"  x: {sensor_xyz[:, 0].min(): .4f} "
    f"to {sensor_xyz[:, 0].max(): .4f}"
)
print(
    f"  y: {sensor_xyz[:, 1].min(): .4f} "
    f"to {sensor_xyz[:, 1].max(): .4f}"
)
print(
    f"  z: {sensor_xyz[:, 2].min(): .4f} "
    f"to {sensor_xyz[:, 2].max(): .4f}"
)


# ============================================================
# 6. Extract ICA scalp projection maps
# ============================================================

# Shape:
#   sensors x ICA components
component_maps = ica.get_components()

print("\nFull ICA component-map shape:")
print(component_maps.shape)

if component_maps.shape[0] != len(ica_channels):
    raise RuntimeError(
        "Number of rows in ICA component maps does not match "
        "number of ICA channels."
    )

keep_maps = component_maps[:, keep_ics]

print("\nRetained component-map shape:")
print(keep_maps.shape)

expected_shape = (128, 44)

if keep_maps.shape != expected_shape:
    raise RuntimeError(
        f"Expected retained map shape {expected_shape}, "
        f"found {keep_maps.shape}."
    )


# ============================================================
# 7. Save CapTrak geometry in ICA channel order
# ============================================================

geometry_df = electrodes_ordered[
    ["name", "x", "y", "z"]
].copy()

geometry_df.insert(
    0,
    "channel_index",
    np.arange(len(geometry_df))
)

geometry_df = geometry_df.rename(
    columns={"name": "channel"}
)

geometry_df.to_csv(
    SENSOR_GEOMETRY_CSV,
    index=False
)


# ============================================================
# 8. Save long-form retained IC scalp maps
# ============================================================

rows = []

for local_idx, ic_idx in enumerate(keep_ics):

    for channel_idx, channel_name in enumerate(ica_channels):

        rows.append(
            {
                "IC_index": int(ic_idx),
                "IC_name": f"ICA{ic_idx:03d}",
                "channel_index": channel_idx,
                "channel": channel_name,
                "x_m": sensor_xyz[channel_idx, 0],
                "y_m": sensor_xyz[channel_idx, 1],
                "z_m": sensor_xyz[channel_idx, 2],
                "scalp_weight": keep_maps[
                    channel_idx,
                    local_idx
                ],
            }
        )

scalp_maps_df = pd.DataFrame(rows)

scalp_maps_df.to_csv(
    SCALP_MAPS_CSV,
    index=False
)


# ============================================================
# Final summary
# ============================================================

print("\n============================================")
print("SOURCE-PREPARATION CHECK COMPLETE")
print("============================================")

print(f"\nKEEP components : {len(keep_ics)}")

print("\nSensor geometry:")
print(f"  Shape : {sensor_xyz.shape}")

print("\nRetained IC scalp maps:")
print(f"  Shape : {keep_maps.shape}")

print("\nScalp-map table rows:")
print(len(scalp_maps_df))

print("\nSaved sensor geometry:")
print(SENSOR_GEOMETRY_CSV.resolve())

print("\nSaved retained IC scalp maps:")
print(SCALP_MAPS_CSV.resolve())

print(
    "\nNo coordinate registration or source localization "
    "was performed."
)