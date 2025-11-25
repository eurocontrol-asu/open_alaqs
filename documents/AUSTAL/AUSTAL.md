# AUSTAL Setup Guide

## Overview

AUSTAL is a dispersion model and the reference implementation to Annex 2 of the German Environment Agency's Technical Instructions on Air Quality Control (TA Luft). It is freely available under the GNU Public Licence.

## Download

AUSTAL can be downloaded from the official webpage of the German Environment Agency:

**[AUSTAL Download Page](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/download)**

Download the base package appropriate for your operating system:
- **Windows**: `AUSTAL_3.3.0_Windows.zip`
- **Linux**: `AUSTAL_3.3.0_Linux.tar.gz`

Current version: AUSTAL 3.3.0 (released 22.03.2024)

## Installation

1. Download the AUSTAL base package for your operating system from the link above
2. Extract the package to your desired location
3. Ensure the AUSTAL executable is accessible from your system PATH or configure the path in OpenALAQS settings

### Important: Configuration File Setup

After extracting AUSTAL, you must replace the default `austal.settings` file with the one provided in the OpenALAQS package:

- Locate `austal.settings` in the AUSTAL installation directory
- Replace it with the `austal.settings` file provided with OpenALAQS
- This ensures proper integration and configuration for OpenALAQS simulations

The English language files (`AST_en` and `DIA_en`) are already included in the AUSTAL distribution. If they are not provided, use the ones from this folder.

## Configuration Files

### austal.settings

The `austal.settings` file is the main configuration file for AUSTAL simulations within OpenALAQS. This file contains:

- Model parameters (grid resolution, time steps, etc.)
- Meteorological data specifications
- Receptor grid definitions
- Output format and locations
- Source configuration details

### Files to Add/Modify

When setting up AUSTAL for use with OpenALAQS, ensure the following files are in place:

| File | Purpose | Status |
|------|---------|--------|
| `austal.settings` | Main AUSTAL configuration | Create/Modify |


## Additional Resources

- [AUSTAL Documentation](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/overview)
- [Janicke Consulting](https://www.janicke.de/) - AUSTAL developers
