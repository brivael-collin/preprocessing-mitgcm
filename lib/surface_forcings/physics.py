"""Atmospheric quantities computed from the interpolated weather variables (humidity, longwave radiation)."""
import numpy as np


def calculate_specific_humidity(Temp, RelHum, AtmPress):
    """
    Specific humidity from air temperature, relative humidity and atmospheric pressure.
    Inputs:
      Temp (float or xr.DataArray)     - air temperature [K]
      RelHum (float or xr.DataArray)   - relative humidity [%]
      AtmPress (float or xr.DataArray) - atmospheric pressure [Pa]
    Output:
      (same type) - specific humidity [kg/kg]
    """
    TempCelsius = Temp - 273.15
    AtmPressHpa = AtmPress / 100.0
    # Saturation vapour pressure, then actual vapour pressure [hPa]
    SaturationPressure = 6.112 * np.exp((17.67 * TempCelsius) / (TempCelsius + 243.5))
    VapourPressure = (RelHum / 100) * SaturationPressure

    return (0.622 * VapourPressure) / (AtmPressHpa - 0.378 * VapourPressure)


def compute_vapor_pressure(ATemp, RelHum):
    """
    Vapour pressure with the Magnus formula.
    Inputs:
      ATemp (float or xr.DataArray)  - air temperature [K]
      RelHum (float or xr.DataArray) - relative humidity [%]
    Output:
      (same type) - vapour pressure [hPa]
    """
    MagnusA = 17.27
    MagnusB = 237.7
    ATempCelsius = ATemp - 273.15
    SaturationPressure = 6.112 * np.exp((MagnusA * ATempCelsius) / (ATempCelsius + MagnusB))

    return (RelHum / 100.0) * SaturationPressure


def compute_longwave_radiation(ATemp, RelHum, CloudCover, ALw=1.09):
    """
    Incoming longwave radiation from air temperature, humidity and cloud cover.
    Inputs:
      ATemp (float or xr.DataArray)      - air temperature [K]
      RelHum (float or xr.DataArray)     - relative humidity [%]
      CloudCover (float or xr.DataArray) - cloud cover [%]
      ALw (float)                        - calibration parameter of the atmospheric emissivity
    Output:
      (same type) - longwave radiation [W/m2]
    """
    CloudFraction = CloudCover / 100
    VaporPressure = compute_vapor_pressure(ATemp, RelHum)  # [hPa]
    InfraredAlbedo = 0.03

    # Atmospheric emissivity, then Stefan-Boltzmann law
    Emissivity = ALw * (1 + 0.17 * np.power(CloudFraction, 2)) * 1.24 * np.power(VaporPressure / ATemp, 1. / 7)

    return (1 - InfraredAlbedo) * 5.67e-8 * Emissivity * np.power(ATemp, 4)
