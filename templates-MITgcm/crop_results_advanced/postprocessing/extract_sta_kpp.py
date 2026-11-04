#!/usr/bin/env python3
import xmitgcm as xm
import numpy as np
import os

ds = xm.open_mdsdataset("../run", ref_date="!formatted_ref_date!", prefix='kpp_diag', delta_t=!time_step!, endian=">")

x_sta = # station x in local MITgcm coordinates [m] (to fill in for Lake Zug)
y_sta = # station y in local MITgcm coordinates [m] (to fill in for Lake Zug)

i_xc = np.argmin(np.abs(ds['XC'].values - x_sta))
i_yc = np.argmin(np.abs(ds['YC'].values - y_sta))

ds_crop = ds[['KPPhbl','MXLDEPTH','KPPfrac']].isel(XC=i_xc, YC=i_yc)

output_dir = "../crop_results"
os.makedirs(output_dir, exist_ok=True)

output_file = os.path.join(output_dir, "sta_kpp.nc")
ds_crop.to_netcdf(output_file)

print(f'Station kpp time series saved at: {output_file}')
