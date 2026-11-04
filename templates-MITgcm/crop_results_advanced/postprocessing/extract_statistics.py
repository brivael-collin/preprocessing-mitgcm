#!/usr/bin/env python3
import xmitgcm as xm
import numpy as np
import xarray as xr
import os
import pylake

ds = xm.open_mdsdataset("../run", ref_date="!formatted_ref_date!", prefix='3Dsnaps', delta_t=!time_step!, endian=">")

def convert_ds_to_little_endian(mitgcm_ds):
    mitgcm_ds = mitgcm_ds.astype('<f8')
    mitgcm_ds= mitgcm_ds.assign(Z=mitgcm_ds['Z'].astype('<f8'))
    mitgcm_ds= mitgcm_ds.assign(XC=mitgcm_ds['XC'].astype('<f8'))
    mitgcm_ds= mitgcm_ds.assign(YC=mitgcm_ds['YC'].astype('<f8'))
    mitgcm_ds= mitgcm_ds.assign(XG=mitgcm_ds['XG'].astype('<f8'))
    mitgcm_ds= mitgcm_ds.assign(YG=mitgcm_ds['YG'].astype('<f8'))
    mitgcm_ds= mitgcm_ds.assign(Zp1=mitgcm_ds['Zp1'].astype('<f8'))
    mitgcm_ds= mitgcm_ds.assign(Zu=mitgcm_ds['Zu'].astype('<f8'))
    mitgcm_ds= mitgcm_ds.assign(Zl=mitgcm_ds['Zl'].astype('<f8'))
    
    return mitgcm_ds

ds_conv = convert_ds_to_little_endian(ds)

upper_layer_temp = ds_conv['THETA'].interp(Z=np.arange(0, -61, -1))
#%%
depth = upper_layer_temp.Z.values
bthA = np.ones(61)
bthD = depth
#%%
def compute_heat_content(ds_temp: xr.DataArray, bthA: np.ndarray, bthD: np.ndarray, depth: xr.DataArray = None, s: float = 0.2) -> xr.DataArray:
    '''
    Calculates the heat content of the water column using temperature and bathymetry data.
    
    Parameters
    -----------
    ds_temp : xr.DataArray
        Water temperature in degrees Celsius, indexed by depth.
    bthA : np.ndarray
        Cross-sectional areas (m^2) corresponding to bthD depths.
    bthD : np.ndarray
        Depths (m) corresponding to areal measures in bthA.
    depth : xr.DataArray, optional
        Depth (m) corresponding to Temp measurements. If None, Temp must have depth as a coordinate.
    s : float, optional
        Salinity in PSU, default is 0.2.
    
    Returns
    ---------
    U : xr.DataArray
        Internal energy in Joules per square meter.
    '''
    dz = 0.1  # Layer thickness (m)
    cw = 4186  # Specific heat capacity of water (J/kg/K)
    
    if depth is None:
        depth = ds_temp.coords['Z']
    
    # Calculate density
    rhoL = pylake.dens0(s=s, t=ds_temp)  # Assumes dens0 is a function that computes density
    
    # Create a fine-resolution depth grid
    layerD = np.arange(depth.min().item(), depth.max().item(), dz)
    
    # Interpolate temperature, density, and area to the fine grid
    layerP = rhoL.interp(Z=layerD)
    layerT = ds_temp.interp(Z=layerD)
    layerA = xr.DataArray(np.interp(layerD, bthD, bthA), 
                          coords={'Z': layerD},
                            dims=("Z",)  # Ensures proper alignment along 'Z'
                            )
    
    # Compute volume and mass per layer
    v_i = layerA * dz  # Volume per layer
    m_i = layerP * v_i  # Mass per layer
    u_i = layerT * m_i * cw  # Energy per layer
    
    # Compute total internal energy per unit surface area
    U = u_i.sum(dim='Z') / layerA[0]
    
    return U
#%%

heat_content_map = compute_heat_content(upper_layer_temp, bthA=bthA, bthD=bthD, depth=depth, s=0.2)

output_dir = "../crop_results"
os.makedirs(output_dir, exist_ok=True)

output_file = os.path.join(output_dir, "heat_content_map.nc")
heat_content_map.to_netcdf(output_file)

print(f'Heat fluxes saved at: {output_file}')
