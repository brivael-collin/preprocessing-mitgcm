#!/usr/bin/env python3
import xmitgcm as xm
import numpy as np
import os

ds = xm.open_mdsdataset("!results_folder!", grid_dir="../run", ref_date="!formatted_ref_date!", prefix='3Dsnaps', delta_t=!time_step!, endian=">")

ds_crop = ds[['THETA','UVEL','VVEL']].isel(Z=0)

output_dir = "../crop_results"
os.makedirs(output_dir, exist_ok=True)

output_file = os.path.join(output_dir, "surface.nc")
ds_crop.to_netcdf(output_file)

print(f'Surface results saved at: {output_file}')
