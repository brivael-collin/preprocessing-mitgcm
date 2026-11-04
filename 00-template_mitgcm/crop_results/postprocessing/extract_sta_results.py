#!/usr/bin/env python3
import xmitgcm as xm
import numpy as np
import os

ds = xm.open_mdsdataset("!results_folder!", grid_dir="../run", ref_date="!formatted_ref_date!", prefix='3Dsnaps', delta_t=!time_step!, endian=">")

x_sta = # station x in local MITgcm coordinates [m] (to fill in for Lake Zug)
y_sta = # station y in local MITgcm coordinates [m] (to fill in for Lake Zug)

i_xc = np.argmin(np.abs(ds['XC'].values - x_sta))
i_yc = np.argmin(np.abs(ds['YC'].values - y_sta))
i_xg = np.argmin(np.abs(ds['XG'].values - x_sta))
i_yg = np.argmin(np.abs(ds['YG'].values - y_sta))

ds_crop = ds[['THETA','UVEL','VVEL']].isel(XC=i_xc, YC=i_yc, XG=i_xg, YG=i_yg)

output_dir = "../crop_results"
os.makedirs(output_dir, exist_ok=True)

output_file = os.path.join(output_dir, "sta_depth_time.nc")
ds_crop.to_netcdf(output_file)

print(f'Station time series saved at: {output_file}')
