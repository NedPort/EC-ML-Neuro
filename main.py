# % Matlab codes for checking the dimentions of  Otput
# and bad files
   ## Calculating GPDC, model fitting and ..




# % %%  Calculating GPDC for each data in the directory
# % 
# % % EEGLAB batch processing for GPDC connectivity
# % % ---------------------------------------------
# % [ALLEEG, EEG, CURRENTSET, ALLCOM] = eeglab;
# % 
# % % Define directory
# % indir  = 'C:\\Users\\nedpo\\Desktop\\fNIRS_Paper_revise_2\\mat\\processed\\';
# % outdir = 'C:\\Users\\nedpo\\Desktop\\fNIRS_Paper_revise_2\\mat\\processed\\';
# % 
# % % Get list of all .set files
# % filelist = dir(fullfile(indir, '*.set'));
# % 
# % for i = 1:length(filelist)
# %     
# %     % Get base name
# %     [~, fname, ~] = fileparts(filelist(i).name);
# %     
# %     % Skip if this is already a _conn file
# %     if contains(fname, '_conn')
# %         fprintf('Skipping already processed (has _conn): %s\n', fname);
# %         continue;
# %     end
# %     
# %     % Build output filename (_conn.set)
# %     out_name = [fname '_conn.set'];
# %     
# %     % Skip if output file already exists
# %     if exist(fullfile(outdir, out_name), 'file')
# %         fprintf('Skipping (already saved): %s\n', out_name);
# %         continue;
# %     end
# %     
# %     % Load dataset
# %     EEG = pop_loadset('filename', filelist(i).name, 'filepath', indir);
# %     [ALLEEG, EEG, CURRENTSET] = eeg_store(ALLEEG, EEG, 0);
# %     
# %     % Run preprocessing
# %     EEG = pop_pre_prepData(EEG);
# %     [ALLEEG, EEG, CURRENTSET] = pop_newset(ALLEEG, EEG, 1,'gui','off');
# %     
# %     % Fit MVAR model
# %     EEG = pop_est_fitMVAR(EEG,0);
# %     [ALLEEG, EEG] = eeg_store(ALLEEG, EEG, CURRENTSET);
# %     
# %     % Compute connectivity (GPDC)
# %     EEG = pop_est_mvarConnectivity(EEG);
# %     [ALLEEG, EEG] = eeg_store(ALLEEG, EEG, CURRENTSET);
# %     
# %     % Save results
# %     EEG = pop_saveset(EEG, 'filename', out_name, 'filepath', outdir);
# %     [ALLEEG, EEG] = eeg_store(ALLEEG, EEG, CURRENTSET);
# %     
# %     eeglab redraw; % optional
# %     fprintf('Finished %d/%d: %s -> %s\n', i, length(filelist), fname, out_name);
# % end



# %% checking the bad files
# %% Initialize EEGLAB
# [ALLEEG, EEG, CURRENTSET, ALLCOM] = eeglab;

# % Define directory
# indir = 'C:\Users\nedpo\Desktop\fNIRS_Paper_revise_2\mat\processed\';

# % Get list of all .set files that end with _conn
# filelist = dir(fullfile(indir, '*_conn.set'));

# % Open log file for saving problematic files
# logFile = fullfile(indir, 'bad_files.txt');
# fid = fopen(logFile, 'w');

# for i = 1:length(filelist)
#     % File name
#     fname = filelist(i).name;
#     fprintf('Loading file %d/%d: %s\n', i, length(filelist), fname);

#     % Load dataset
#     EEG = pop_loadset('filename', fname, 'filepath', indir);

#     % Store in ALLEEG
#     [ALLEEG, EEG, CURRENTSET] = eeg_store(ALLEEG, EEG, 0);

#     % Extract GPDC
#     Four_D_GPDC = EEG.CAT.Conn.GPDC;

#     % Check the 3rd dimension
#     if size(Four_D_GPDC, 3) ~= 9
#         fprintf(fid, '%s (3rd dim = %d)\n', fname, size(Four_D_GPDC,3)); % Write to log file
#         fprintf('❌ Problem: %s (3rd dim = %d)\n', fname, size(Four_D_GPDC,3));
#     else
#         fprintf('✅ OK: %s\n', fname);
#     end
# end

# % Close log file
# fclose(fid);

# fprintf('Done. List of bad files saved in %s\n', logFile);






# % %%   Recalculating GPDC for bad files
# % clc
# % clear
# % close all
# % % EEGLAB batch processing for GPDC connectivity
# % % ---------------------------------------------
# % [ALLEEG, EEG, CURRENTSET, ALLCOM] = eeglab;
# % 
# % % Define directory
# % indir  = 'C:\\Users\\nedpo\\Desktop\\fNIRS_Paper_revise_2\\mat\\processed\\';
# % outdir = 'C:\\Users\\nedpo\\Desktop\\fNIRS_Paper_revise_2\\mat\\processed\\';
# % 
# % % Get list of all .set files
# % filelist = { ...
# %     'RS4_SL_4216_coe_conn.set', ...
# %     'RS4_SL_4219_oxy_conn.set', ...
# %     'RS4_SL_4280_coe_conn.set', ...
# %     'RS4_SL_4297_coe_conn.set', ...
# %     'RS4_SL_4301_oxy_conn.set', ...
# %     'RS4_SL_4453_coe_conn.set', ...
# %     'RS4_SL_4456_coe_conn.set', ...
# %     'RS4_SL_4485_coe_conn.set', ...
# %     'RS4_SL_4527_coe_conn.set', ...
# %     'RS4_SL_4615_coe_conn.set', ...
# %     'RS4_SL_4618_coe_conn.set', ...
# %     'RS4_SL_4653_coe_conn.set' ...
# % };
# % 
# % 
# % for i = 1:length(filelist)
# %     % File name (from cell array)
# %     fname_full = filelist{i};             % <- access cell content
# %     [~, fname, ~] = fileparts(fname_full); % extract base name
# %     
# %     % Load dataset
# %     EEG = pop_loadset('filename', fname_full, 'filepath', indir);
# %     [ALLEEG, EEG, CURRENTSET] = eeg_store(ALLEEG, EEG, 0);
# %     
# %     % Run preprocessing
# %     EEG = pop_pre_prepData(EEG);
# %     [ALLEEG, EEG, CURRENTSET] = pop_newset(ALLEEG, EEG, 1,'gui','off');
# %     
# %     % Fit MVAR model
# %     EEG = pop_est_fitMVAR(EEG,0);
# %     [ALLEEG, EEG] = eeg_store(ALLEEG, EEG, CURRENTSET);
# %     
# %     % Compute connectivity (GPDC)
# %     EEG = pop_est_mvarConnectivity(EEG);
# %     [ALLEEG, EEG] = eeg_store(ALLEEG, EEG, CURRENTSET);
# %     
# %     % Save results
# %     out_name = [fname '.set'];
# %     EEG = pop_saveset(EEG, 'filename', out_name, 'filepath', outdir);
# %     fprintf('Finished %d/%d: %s\n', i, length(filelist), out_name);
# % end

