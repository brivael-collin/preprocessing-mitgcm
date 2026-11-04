#!/usr/bin/env python3
import xmitgcm as xm
import numpy as np
import os

ds = xm.open_mdsdataset("../run", ref_date="!formatted_ref_date!", prefix='heatflux', delta_t=!time_step!, endian=">")

output_dir = "../crop_results"
os.makedirs(output_dir, exist_ok=True)

output_file = os.path.join(output_dir, "heatfluxes.nc")
ds.to_netcdf(output_file)

print(f'Heat fluxes saved at: {output_file}')
