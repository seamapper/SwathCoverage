# Swath Coverage Analysis Tools

A comprehensive toolkit for analyzing swath coverage data from from Kongsberg multibeam systems. This project provides two main applications for processing, converting, and visualizing the swath coverage  data.

**Center for Coastal and Ocean Mapping (CCOM) / Joint Hydrographic Center (JHC), University of New Hampshire**

## Overview

This toolkit consists of two complementary applications:

1. **KMALL to PKL Converter** - Converts raw KMALL/ALL files to optimized PKL format for faster processing
2. **Swath Coverage Plotter** - Comprehensive GUI application for analyzing multibeam sonar data during a swath coverage test

## Applications

### 1. KMALL to PKL Converter

A standalone GUI application that converts Kongsberg multibeam data files (KMALL and ALL formats) to optimized PKL (pickle) files for faster loading and processing in the Swath Coverage Plotter.

#### Key Features
- **Simple GUI Interface**: Easy-to-use graphical interface for file selection and conversion
- **Batch Processing**: Convert multiple files at once
- **Directory Support**: Add entire directories with optional recursive subdirectory search
- **Progress Tracking**: Real-time progress bar and status updates
- **Compression Support**: Optional gzip compression for 30-70% smaller files
- **Error Handling**: Comprehensive error reporting and logging
- **File Validation**: Automatic detection of up-to-date files (skip if newer)

#### Usage

**Method 1: Python Script**
```bash
python kmall_to_pkl_converter.py
```

**Method 2: Windows Executable**
```bash
KMALL to SwathPKL Converter V2025.02.exe
```

**Basic Workflow:**
1. Launch the application
2. Add files using one of the following methods:
   - Click "Select KMALL/ALL Files" to choose individual files
   - Click "Select Directory" to add all KMALL/ALL files from a directory
   - Enable "Include Subdirectories" checkbox to recursively search subdirectories
3. Choose an output directory for the converted PKL files
4. Optionally enable compression for smaller file sizes
5. Click "Start Conversion" and monitor progress

### 2. Swath Coverage Plotter

A comprehensive GUI application for analyzing and visualizing multibeam echosounder data with extensive plotting and analysis capabilities.

#### Key Features
- **Multiple Data Sources**: Load raw KMALL/ALL files, Swath PKL files, or archived data
- **Comprehensive Plotting**: Generate plots for depth, backscatter, ping mode, pulse form, swath mode, frequency, data rate, and timing
- **Interactive Visualization**: Hover over data points to see file information
- **Coverage Analysis**: Calculate and visualize swath coverage trends
- **Data Filtering**: Filter by angle, depth, backscatter, ping interval, and runtime parameters
- **Archive Management**: Archive processed data for later comparison
- **Export Functionality**: Export plots and coverage trends (e.g., for Gap Filler)
- **Parameter Search**: Search acquisition parameters by mode, frequency, angles, and more
- **Theoretical Performance**: Overlay theoretical coverage specification curves
- **Session Persistence**: Remember directory preferences and settings

#### Usage

**Method 1: Python Script**
```bash
python swath_coverage_plotter.py
```

**Method 2: Windows Executable**
```bash
Swath Coverage Plotter V2025.11.exe
```

**Basic Workflow:**
1. Launch the application
2. Load data using one of the following methods:
   - **Raw Files**: Add KMALL/ALL files and calculate coverage
   - **Swath PKL**: Load pre-converted PKL files (faster)
   - **Archive PKL**: Load previously archived data for comparison
3. Configure plot settings (colors, limits, filters, etc.)
4. Generate and explore plots across multiple tabs
5. Export plots or coverage trends as needed

## Installation

### Requirements

#### Python Dependencies
- Python 3.8 or later
- PyQt6 (GUI framework)
- NumPy (numerical computing)
- SciPy (scientific computing)
- Matplotlib (plotting)

#### Optional Dependencies
- pyproj (coordinate transformations)
- utm (UTM coordinate conversions)

#### Installation Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/seamapper/SwathCoverage.git
   cd SwathCoverage
   ```

2. **Install Python dependencies**
   ```bash
   pip install PyQt6 numpy scipy matplotlib
   ```

3. **Verify directory structure**
   ```
   SwathCoverage/
   ├── libs/
   │   ├── swath_fun.py
   │   ├── swath_coverage_lib.py
   │   ├── kmall.py
   │   ├── parseEM.py
   │   ├── file_fun.py
   │   └── gui_widgets.py
   ├── kmall_to_pkl_converter.py
   ├── swath_coverage_plotter.py
   └── media/
   ```

### Building Executables (Optional)

Windows executables can be built using PyInstaller:

```bash
# Build converter executable
pyinstaller KMALL_to_PKL_Converter.spec

# Build plotter executable
pyinstaller SwathCoveragePlotter.spec
```

Or use the provided build scripts:
```bash
# Windows Batch
build_exe.bat

# Windows PowerShell
build_exe.ps1
```

## Supported File Formats

### Input Formats
- **KMALL**: Kongsberg's modern multibeam format (.kmall)
- **ALL**: Kongsberg's legacy format (.all)

### Output Formats
- **PKL**: Optimized pickle format for fast loading (.pkl)
  - Optional gzip compression (30-70% size reduction)
  - Contains coordinates, backscatter, metadata, and parameters

## Supported Multibeam Systems

The toolkit supports Kongsberg EM series multibeam systems:
- EM 2040
- EM 2042
- EM 302
- EM 304
- EM 710
- EM 712
- EM 122
- EM 124

## Plot Types

The Swath Coverage Plotter provides the following plot types:

1. **Depth**: Swath coverage with depth coloring
2. **Backscatter**: Acoustic backscatter visualization
3. **Ping Mode**: Depth mode visualization (Very Shallow, Shallow, Medium, Deep, etc.)
4. **Pulse Form**: Continuous Wave (CW) vs. Frequency Modulated (FM) pulse forms
5. **Swath Mode**: Single vs. Dual swath operation
6. **Frequency**: Operating frequency visualization
7. **Data Rate**: Data acquisition rate over time
8. **Timing**: Ping interval and timing analysis
9. **Parameters**: Runtime parameter log and search

## Data Processing Features

### Filtering Options
- **Angle Filtering**: Filter by nominal swath angles
- **Depth Filtering**: Filter by depth ranges (separate for new/archive data)
- **Backscatter Filtering**: Filter by backscatter amplitude
- **Ping Interval Filtering**: Filter by time between pings
- **Runtime Parameter Filtering**: Hide angles/coverage near runtime limits

### Analysis Features
- **Coverage Trend Calculation**: Calculate and visualize coverage trends
- **Parameter Search**: Search acquisition parameters by multiple criteria
- **Theoretical Performance**: Overlay theoretical coverage specification curves
- **Data Archiving**: Archive processed data for later comparison
- **Export to Gap Filler**: Export coverage trends for Gap Filler import

## Performance Tips

### For Large Datasets
- **Use PKL Files**: Convert raw files to PKL format first for faster loading
- **Enable Compression**: Reduces file sizes by 30-70% with minimal performance impact
- **Use Point Count Limits**: Limit plotted points for faster rendering
- **Apply Filters**: Use filters to reduce data before plotting

### For Batch Processing
- Convert multiple files to PKL format using the converter
- Load PKL files directly in the plotter for faster processing
- Use archive functionality to compare different datasets

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```
   Error: Could not import libraries from libs folder
   ```
   **Solution**: Ensure the `libs/` folder is present in the same directory as the scripts

2. **PyQt6 Not Found**
   ```
   Error: PyQt6 is not installed
   ```
   **Solution**: Install PyQt6: `pip install PyQt6`

3. **Memory Errors with Large Files**
   ```
   Out of memory error
   ```
   **Solution**: 
   - Use PKL files instead of raw files
   - Enable compression
   - Use point count limits
   - Process files individually

4. **File Permission Errors**
   ```
   Permission denied when writing to output directory
   ```
   **Solution**: Choose a different output directory or run as administrator

### Getting Help

If you encounter issues:
1. Check the log area in the application for detailed error messages
2. Ensure all dependencies are installed correctly
3. Verify the directory structure is correct
4. Try processing a single small file first

## Version History

### Swath Coverage Plotter
- **v2025.11**: Fixed plot decimation to only run when filter settings are changed
- **v2025.10**: Reorganized sources area into tabs
- **v2025.09**: GUI improvements, Fixed Plots Scaling
- **v2025.08**: Enhanced theoretical performance plotting
- **v2025.07**: Improved swath coverage curve specification plotting
- **v2025.06**: Fixed issue with loading new PKL files, added loading directory
- **v2025.05**: Fixed frequency plot export size and text field styling
- **v2025.03**: Fixed some issues with the swath coverage plotter
- **v2025.02**: New features, new swath PKL, GUI redesign

### KMALL to PKL Converter
- **v2025.02**: Added subdirectory search option
  - Added checkbox to include subdirectories when adding a directory
  - Updated executable naming format
- **v2025.01**: Initial release
  - GUI interface
  - Batch processing
  - Compression support
  - Progress tracking
  - Error handling

## Contributing

Contributions are welcome! Please feel free to submit issues, fork the repository, and create pull requests.

## License

This project is licensed under the BSD-3-Clause License - see the [LICENSE](LICENSE) file for details.

## Authors

- **kjerram** - kjerram@ccom.unh.edu
- **Paul Johnson** - pjohnson@ccom.unh.edu

## Acknowledgments

Developed at the Center for Coastal and Ocean Mapping (CCOM) / Joint Hydrographic Center (JHC), University of New Hampshire.

## Citation

If you use this software in your research, please cite:

```
Swath Coverage Analysis Tools
Center for Coastal and Ocean Mapping (CCOM) / Joint Hydrographic Center (JHC)
University of New Hampshire
https://github.com/seamapper/SwathCoverage
```

## Contact

For questions, issues, or contributions:
- **Email**: kjerram@ccom.unh.edu, pjohnson@ccom.unh.edu
- **Repository**: https://github.com/seamapper/SwathCoverage
- **Issues**: https://github.com/seamapper/SwathCoverage/issues




