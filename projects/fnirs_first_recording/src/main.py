# %%
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ==================================================
# 1. Project paths
# ==================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

file_path = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "NedaSignal.txt"
)

figure_dir = (
    PROJECT_ROOT
    / "results"
    / "figures"
    / "raw"
)

figure_dir.mkdir(parents=True, exist_ok=True)

print(f"Reading: {file_path}")
print(f"File exists: {file_path.exists()}")


# ==================================================
# 2. Raw acquisition columns
# ==================================================

columns = [
    "Channel",
    "Sensor",
    "Wavelength",
    "Raw_V",
    "Raw_us",
    "LED_off_us",
    "D0",
    "D0_us",
    "D1",
    "D1_us",
    "D2",
    "D2_us",
    "D3",
    "D3_us",
]


# ==================================================
# 3. Load raw recording
# ==================================================

df = pd.read_csv(
    file_path,
    header=None,
    names=columns,
    on_bad_lines="skip",
)


# ==================================================
# 4. Validate rows
# ==================================================

valid_wavelengths = [730, 850]

invalid_rows = df[
    ~df["Wavelength"].isin(valid_wavelengths)
]

df_valid = df[
    df["Wavelength"].isin(valid_wavelengths)
].copy()


print("\n-----------------------------------")
print("DATA VALIDATION")
print("-----------------------------------")

print("Original rows:", len(df))
print("Valid rows:", len(df_valid))
print("Removed rows:", len(df) - len(df_valid))

if len(invalid_rows) > 0:
    print("\nInvalid rows:")
    print(invalid_rows)


# ==================================================
# 5. Basic recording information
# ==================================================

print("\n-----------------------------------")
print("RECORDING STRUCTURE")
print("-----------------------------------")

print("\nValid data shape:")
print(df_valid.shape)

print("\nChannels:")
print(sorted(df_valid["Channel"].unique()))

print("\nWavelengths:")
print(sorted(df_valid["Wavelength"].unique()))

print("\nSamples per channel:")
print(
    df_valid["Channel"]
    .value_counts()
    .sort_index()
)


# ==================================================
# 6. Create time axis
# ==================================================

start_time_us = df_valid["Raw_us"].min()

df_valid["Time_s"] = (
    df_valid["Raw_us"] - start_time_us
) / 1_000_000


recording_duration = (
    df_valid["Raw_us"].max()
    - df_valid["Raw_us"].min()
) / 1_000_000

print(
    f"\nRecording duration: "
    f"{recording_duration:.2f} seconds "
    f"({recording_duration / 60:.2f} minutes)"
)


# ==================================================
# 7. Sampling frequency
# ==================================================

print("\n-----------------------------------")
print("SAMPLING FREQUENCY")
print("-----------------------------------")

sampling_results = []

for channel in sorted(df_valid["Channel"].unique()):

    channel_data = (
        df_valid[df_valid["Channel"] == channel]
        .sort_values("Raw_us")
    )

    dt_sec = (
        channel_data["Raw_us"]
        .diff()
        .dropna()
        / 1_000_000
    )

    mean_dt = dt_sec.mean()
    fs = 1 / mean_dt

    sampling_results.append(
        {
            "Channel": channel,
            "Samples": len(channel_data),
            "Mean_dt_s": mean_dt,
            "Fs_Hz": fs,
        }
    )


sampling_df = pd.DataFrame(sampling_results)

print(
    sampling_df.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}"
    )
)


# ==================================================
# 8. Raw signal QC statistics
# ==================================================

print("\n-----------------------------------")
print("RAW SIGNAL QC STATISTICS")
print("-----------------------------------")

stats = (
    df_valid
    .groupby("Channel")["Raw_V"]
    .agg(
        count="count",
        min="min",
        max="max",
        mean="mean",
        std="std",
    )
)

stats["range"] = (
    stats["max"] - stats["min"]
)

print(stats.round(6))


# ==================================================
# 9. Plot all 8 optical channels
# ==================================================

print("\n-----------------------------------")
print("GENERATING RAW SIGNAL PLOTS")
print("-----------------------------------")


for channel_number in range(1, 9):

    channel_730_name = f"{channel_number}A"
    channel_850_name = f"{channel_number}B"

    ch_730 = df_valid[
        df_valid["Channel"] == channel_730_name
    ]

    ch_850 = df_valid[
        df_valid["Channel"] == channel_850_name
    ]

    # ----------------------------------------------
    # Create figure
    # ----------------------------------------------

    plt.figure(figsize=(12, 5))

    plt.plot(
        ch_730["Time_s"],
        ch_730["Raw_V"],
        label=f"730 nm ({channel_730_name})",
        linewidth=1,
    )

    plt.plot(
        ch_850["Time_s"],
        ch_850["Raw_V"],
        label=f"850 nm ({channel_850_name})",
        linewidth=1,
    )

    plt.xlabel("Time (seconds)")
    plt.ylabel("Raw detector voltage (V)")

    plt.title(
        f"Channel {channel_number} — Raw fNIRS Signal"
    )

    plt.legend()

    plt.grid(
        alpha=0.3
    )

    plt.tight_layout()


    # ----------------------------------------------
    # Save figure
    # ----------------------------------------------

    output_file = (
        figure_dir
        / f"channel_{channel_number}_raw.png"
    )

    plt.savefig(
        output_file,
        dpi=300,
        bbox_inches="tight",
    )

    print(
        f"Saved Channel {channel_number}: "
        f"{output_file}"
    )

    plt.close()


print("\nFinished.")
# ==================================================
# 10. Dark measurement statistics
# ==================================================

print("\n-----------------------------------")
print("DARK MEASUREMENT STATISTICS")
print("-----------------------------------")

dark_stats = (
    df_valid
    .groupby("Channel")[["Raw_V", "D0", "D1", "D2", "D3"]]
    .mean()
)

print(dark_stats.round(6))


# ==================================================
# 11. Difference between dark measurements and Raw_V
# ==================================================

dark_difference = dark_stats.copy()

dark_difference["D0_minus_Raw"] = (
    dark_difference["D0"] - dark_difference["Raw_V"]
)

dark_difference["D1_minus_Raw"] = (
    dark_difference["D1"] - dark_difference["Raw_V"]
)

dark_difference["D2_minus_Raw"] = (
    dark_difference["D2"] - dark_difference["Raw_V"]
)

dark_difference["D3_minus_Raw"] = (
    dark_difference["D3"] - dark_difference["Raw_V"]
)

print("\n-----------------------------------")
print("DARK - RAW DIFFERENCES")
print("-----------------------------------")

print(
    dark_difference[
        [
            "D0_minus_Raw",
            "D1_minus_Raw",
            "D2_minus_Raw",
            "D3_minus_Raw",
        ]
    ].round(6)
)


# ==================================================
# 12. Plot Raw -> D0 -> D1 -> D2 -> D3
# ==================================================

dark_figure_dir = (
    PROJECT_ROOT
    / "results"
    / "figures"
    / "dark"
)

dark_figure_dir.mkdir(
    parents=True,
    exist_ok=True
)

measurement_steps = [
    "Raw_V",
    "D0",
    "D1",
    "D2",
    "D3",
]


for channel_number in range(1, 9):

    channel_730 = f"{channel_number}A"
    channel_850 = f"{channel_number}B"

    values_730 = (
        dark_stats
        .loc[channel_730, measurement_steps]
        .values
    )

    values_850 = (
        dark_stats
        .loc[channel_850, measurement_steps]
        .values
    )

    plt.figure(figsize=(9, 5))

    plt.plot(
        measurement_steps,
        values_730,
        marker="o",
        label=f"730 nm ({channel_730})",
    )

    plt.plot(
        measurement_steps,
        values_850,
        marker="o",
        label=f"850 nm ({channel_850})",
    )

    plt.xlabel("Measurement step")
    plt.ylabel("Mean detector voltage (V)")

    plt.title(
        f"Channel {channel_number} — "
        f"Raw and Dark Measurements"
    )

    plt.legend()
    plt.grid(alpha=0.3)

    plt.tight_layout()

    output_file = (
        dark_figure_dir
        / f"channel_{channel_number}_dark.png"
    )

    plt.savefig(
        output_file,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Saved dark plot for Channel {channel_number}: "
        f"{output_file}"
    )

    # ==================================================
# 13. Dark measurement timing
# ==================================================

print("\n-----------------------------------")
print("DARK MEASUREMENT TIMING")
print("-----------------------------------")

# Time from the raw measurement to LED switch-off
df_valid["Raw_to_LEDoff_ms"] = (
    df_valid["LED_off_us"] - df_valid["Raw_us"]
) / 1000

# Time from LED switch-off to each dark measurement
df_valid["LEDoff_to_D0_ms"] = (
    df_valid["D0_us"] - df_valid["LED_off_us"]
) / 1000

df_valid["LEDoff_to_D1_ms"] = (
    df_valid["D1_us"] - df_valid["LED_off_us"]
) / 1000

df_valid["LEDoff_to_D2_ms"] = (
    df_valid["D2_us"] - df_valid["LED_off_us"]
) / 1000

df_valid["LEDoff_to_D3_ms"] = (
    df_valid["D3_us"] - df_valid["LED_off_us"]
) / 1000


# Time between consecutive dark measurements
df_valid["D0_to_D1_ms"] = (
    df_valid["D1_us"] - df_valid["D0_us"]
) / 1000

df_valid["D1_to_D2_ms"] = (
    df_valid["D2_us"] - df_valid["D1_us"]
) / 1000

df_valid["D2_to_D3_ms"] = (
    df_valid["D3_us"] - df_valid["D2_us"]
) / 1000


timing_columns = [
    "Raw_to_LEDoff_ms",
    "LEDoff_to_D0_ms",
    "LEDoff_to_D1_ms",
    "LEDoff_to_D2_ms",
    "LEDoff_to_D3_ms",
    "D0_to_D1_ms",
    "D1_to_D2_ms",
    "D2_to_D3_ms",
]


# ==================================================
# 14. Overall timing statistics
# ==================================================

print("\nMean timing across the recording (ms):")

timing_summary = (
    df_valid[timing_columns]
    .agg(["mean", "std", "min", "max"])
    .T
)

print(timing_summary.round(3))


# ==================================================
# 15. Timing by channel
# ==================================================

print("\nMean timing by channel (ms):")

channel_timing = (
    df_valid
    .groupby("Channel")[timing_columns]
    .mean()
)

print(channel_timing.round(3))
# ============================================================
# HEARTBEAT SANITY CHECK
# ============================================================

from scipy.signal import welch, detrend

# Start with one relatively stable channel
heartbeat_channel = "2A"

signal_df = df_valid[df_valid["Channel"] == heartbeat_channel].copy()

# Sort by acquisition time
signal_df = signal_df.sort_values("Raw_us")

# Raw detector voltage
x = signal_df["Raw_V"].to_numpy()

# Remove the mean / slow linear trend for spectral inspection
x_detrended = detrend(x)

# Sampling frequency calculated from timestamps
time_s = signal_df["Raw_us"].to_numpy() / 1e6
dt = np.diff(time_s)
fs = 1 / np.mean(dt)

print("\nHeartbeat sanity check")
print("----------------------")
print(f"Channel: {heartbeat_channel}")
print(f"Sampling frequency: {fs:.4f} Hz")
print(f"Nyquist frequency: {fs/2:.4f} Hz")

# Power spectral density
frequencies, psd = welch(
    x_detrended,
    fs=fs,
    nperseg=min(256, len(x_detrended))
)

# Plot PSD
plt.figure(figsize=(9, 5))
plt.plot(frequencies, psd)

plt.xlabel("Frequency (Hz)")
plt.ylabel("Power Spectral Density")
plt.title(f"PSD - Channel {heartbeat_channel}")
plt.xlim(0, fs / 2)
plt.grid(True)

heartbeat_figure_dir = PROJECT_ROOT / "results" / "figures" / "heartbeat"
heartbeat_figure_dir.mkdir(parents=True, exist_ok=True)

plt.savefig(
    heartbeat_figure_dir / f"{heartbeat_channel}_PSD.png",
    dpi=300,
    bbox_inches="tight"
)

plt.close()



# Look at a short segment in the time domain
start_time = 50
end_time = 80

relative_time = time_s - time_s[0]

mask = (relative_time >= start_time) & (relative_time <= end_time)

plt.figure(figsize=(12, 5))

plt.plot(
    relative_time[mask],
    x[mask],
    marker="o",
    markersize=4
)

plt.xlabel("Time (s)")
plt.ylabel("Raw Voltage (V)")
plt.title(f"Channel {heartbeat_channel}: {start_time}-{end_time} s")
plt.grid(True)

plt.savefig(
    heartbeat_figure_dir / f"{heartbeat_channel}_50_80s.png",
    dpi=300,
    bbox_inches="tight"
)

plt.close()