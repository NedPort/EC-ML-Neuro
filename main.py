
#%% extracting the hbo, hbr and calculating coe 
# from the precessed data for each subject ____-----
import os
import scipy.io as sio

# Path to your .mat files
folder_path = r"C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\mat"

#%%
# Output folder (can be same as input)
out_folder = os.path.join(folder_path, "processed")
os.makedirs(out_folder, exist_ok=True)

for file_name in os.listdir(folder_path):
    if file_name.endswith(".mat"):
        file_path = os.path.join(folder_path, file_name)
        mat = sio.loadmat(file_path, squeeze_me=True, struct_as_record=False)

        # Access ALLEEG struct
        ALLEEG = mat["rsData"]

        # Get setname (safe string for filename and dict key)
        setname = str(ALLEEG.name).replace(" ", "_").replace("-", "_")

        # Extract GSR oxy & deoxy
        oxy   = ALLEEG.GSR_oxy
        deoxy = ALLEEG.GSR_deoxy

        # Compute coe
        coe = deoxy - oxy

        # Save into a new .mat file
        out_file = os.path.join(out_folder, f"{setname}_gsr.mat")
        sio.savemat(out_file, {"oxy": oxy, "deoxy": deoxy, "coe": coe})

        print(f"Saved {out_file}")
# %%
