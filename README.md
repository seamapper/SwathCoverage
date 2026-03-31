# Swath Coverage Analysis Tools

A comprehensive toolkit for analyzing swath coverage data from Kongsberg multibeam systems. This project provides two main applications for processing, converting, and visualizing swath coverage data.

**Center for Coastal and Ocean Mapping (CCOM) / Joint Hydrographic Center (JHC), University of New Hampshire**

## Overview

This toolkit consists of two complementary applications:

1. **KMALL to PKL Converter** - Converts raw KMALL/ALL files to optimized PKL format for faster processing
2. **Swath Coverage Plotter** - Comprehensive GUI application for analyzing multibeam sonar data during a swath coverage test

---

## Applications

### 1. KMALL to PKL Converter

A standalone GUI application that converts Kongsberg multibeam data files (KMALL and ALL formats) to optimized PKL (pickle) files for faster loading and processing in the Swath Coverage Plotter.

#### Key Features
- **Simple GUI Interface**: Easy-to-use graphical interface for file selection and conversion (Fusion dark theme)
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
```
KMALL_to_SwathPKL_Converter_v2026.01.exe
```
Executables are named `KMALL_to_SwathPKL_Converter_v` + version from the code.

**Basic Workflow:**
1. Launch the application
2. Add files using one of the following methods:
   - Click "Select KMALL/ALL Files" to choose individual files
   - Click "Select Directory" to add all KMALL/ALL files from a directory
   - Enable "Include Subdirectories" checkbox to recursively search subdirectories
3. Choose an output directory for the converted PKL files
4. Optionally enable compression for smaller file sizes
5. Click "Start Conversion" and monitor progress

---

### 2. Swath Coverage Plotter

A comprehensive GUI application for analyzing and visualizing multibeam echosounder data with extensive plotting and analysis capabilities. The window is fixed at **1600 × 1100 px** and uses a dark Fusion theme.

#### Key Features
- **Multiple Data Sources**: Load raw KMALL/ALL files, Swath PKL files, or archived data
  - Add Directory with optional subdirectory search for Swath PKL and Archive PKL
  - Show Path toggle for each file list
  - "Convert to Swath PKL" button with optional gzip compression
- **Comprehensive Plotting**: Generate plots for depth, backscatter, ping mode, pulse form, swath mode, frequency, data rate, and timing
- **Interactive Visualization**: Hover over data points to see the source filename in the status bar
- **Coverage Trend Analysis**: Calculate, edit, digitize, and export swath coverage trends
- **Data Filtering**: Filter by angle, depth, width, backscatter, ping interval, and runtime parameters
- **Archive Management**: Archive processed data for later comparison
- **Export Functionality**: Save all plots and export coverage trends (e.g., for Gap Filler)
- **Parameter Search**: Search acquisition parameters by mode, frequency, angles, and more
- **Theoretical Performance**: Overlay theoretical coverage specification curves
- **Session Persistence**: Remember directory preferences and settings
- **Dark Theme**: Fusion style with dark palette for consistent appearance

#### Usage

**Method 1: Python Script**
```bash
python swath_coverage_plotter.py
```

**Method 2: Windows Executable**
```
Swath_Coverage_Plotter_v2026.03.exe
```
Executables are named `Swath_Coverage_Plotter_v` + version from the code.

**Basic Workflow:**
1. Launch the application
2. Load data using one of the following methods:
   - **Raw Files tab**: Add KMALL/ALL files and click "Calc Coverage"
   - **Swath PKL tab**: Load pre-converted PKL files (faster loading)
   - **Archive PKL tab**: Load previously archived data for comparison
3. Configure plot settings on the **Plot** tab (colors, limits, point style, etc.)
4. Apply filters on the **Filter** tab as needed
5. Explore plots across the nine center-panel tabs
6. Use the **Trend** tab to calculate or digitize a coverage trend and export it

---

## GUI Layout

### Left Panel — Sources & Log
- **Sources** groupbox (tabbed):
  - *Raw Files*: file list, Raw File Management, Process Raw Files (Calc Coverage, Scan Params Only, Convert to Swath PKL, Convert to Archive PKL)
  - *Swath PKL*: file list, Swath PKL Management
  - *Archive PKL*: file list, Archive PKL Management
  - *Spec Curve*: specification curve files
- **Export Plots** groupbox: Save All Plots button
- **Activity Log**: color-coded scrolling log
- **Status / Progress** area:
  - Current file label (updates during processing)
  - Cursor label (shows hovered filename)
  - *Total Progress* bar (used when loading PKL files)
  - *Converting to PKL* bar (appears only while "Convert to Swath PKL" is running; shows "File X of Y")

### Center Panel — Plots (9 tabs)
| Tab | Content |
|---|---|
| Depth | Main swath coverage scatter plot, colored by depth |
| Backscatter | Backscatter intensity scatter plot |
| Ping Mode | Depth mode over time |
| Pulse Form | CW vs. FM pulse form over time |
| Swath Mode | Single vs. Dual swath over time |
| Frequency | Operating frequency over time |
| Data Rate | Data acquisition rate over time |
| Timing | Ping interval / timing analysis |
| Parameters | Runtime parameter log (searchable) |

### Right Panel — Controls (4 tabs, 240 px wide)

#### Plot Tab
- Custom system information (model, ship name, cruise)
- Depth reference (Waterline / Origin / TX Array / Raw Data)
- Point style (color mode, single color, opacity, point size)
- Custom plot limits (depth, swath width, data rate, ping interval)
- Swath angle reference lines
- Water depth multiple lines
- Other options: grid lines, colorbar, spec lines, histogram, **Show Coverage Trend**

#### Filter Tab
- **Angle** filter (on by default): Min/Max degrees
- **Depth (swath/archive)** filter (on): separate ranges for new and archive data
- **Width (swath/archive)** filter (off by default): Min/Max width in meters; enabling also sets the Swath Width custom plot limit
- **Backscatter** filter (on): Min/Max dB
- **Ping Interval** filter (on): Min/Max seconds
- **Hide angles near runtime limits** (on): angle buffer
- **Hide coverage near runtime limits** (on): coverage buffer
- **Limit plotted point count** (on): max points and decimation factor
- **Swath PKL Memory Management** (off): max points per file and decimation factor

#### Trend Tab
- **Show Coverage Trend** checkbox (mirrors the Plot tab checkbox, bidirectionally synced)
- *Calculate* groupbox:
  - **Calculate Coverage Trend** button
  - **Source** pulldown (Swath / Archive)
  - **Method** pulldown: Mean | Mean+σ | Mean+2σ | Spline
  - **# of Steps** pulldown: 5 / 10 / 15 / 20 / 25 (default 10) — number of depth bands
  - **Min Points** field (default 10): depth bands with fewer points are assigned width = 0
- **Digitize Trend** button: click points directly on the depth plot to build the trend table; toggle button reads "Digitizing. Click here to stop." while active
- *Edit Width* groupbox:
  - **Edit Depth Band Width** button: drag trend points left/right on the depth plot for symmetric width adjustment; original point shown in blue, dragged position in red; negative widths are prevented
- **Trend table**: three columns — Depth (m), Width (m), # Points (non-editable); grid lines visible
- **Clear All Points** button: clears the entire trend table and underlying data
- *Export* groupbox (visible only when Show Coverage Trend is on):
  - **Export Gap Filler** button: exports the current trend as a Gap Filler import file

#### Search Tab
- Search acquisition parameters (ANY/ALL condition) with checkable rows for depth mode, swath mode, pulse form, swath angle, swath coverage, frequency
- Installation parameter search (waterline, array offsets, position offsets)
- Update Search and Save Search Log buttons

---

## Installation

### Requirements

#### Python Dependencies
- Python 3.8 or later
- PyQt6 (GUI framework)
- NumPy (numerical computing)
- SciPy (scientific computing — required for Spline trend method)
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
   ├── media/
   │   └── mac.ico
   ├── kmall_to_pkl_converter.py
   ├── swath_coverage_plotter.py
   ├── SwathCoveragePlotter.spec
   └── KMALL_to_PKL_Converter.spec
   ```

### Building Executables (Optional)

Windows executables can be built using PyInstaller. Both spec files read the version number automatically from the source code.

```bash
# Build plotter executable
pyinstaller SwathCoveragePlotter.spec --clean

# Build converter executable
pyinstaller KMALL_to_PKL_Converter.spec --clean
```

Output is placed in the `dist/` folder, named with the current version (e.g., `Swath_Coverage_Plotter_v2026.03.exe`).

---

## Supported File Formats

### Input Formats
- **KMALL** (.kmall): Kongsberg's modern multibeam format
- **ALL** (.all): Kongsberg's legacy format

### Output / Intermediate Formats
- **PKL** (.pkl): Optimized pickle format for fast loading
  - Optional gzip compression (30–70% size reduction)
  - Contains coordinates, backscatter, metadata, and acquisition parameters

---

## Supported Multibeam Systems

The toolkit supports Kongsberg EM series multibeam systems:
- EM 2040 / EM 2042
- EM 302 / EM 304
- EM 710 / EM 712
- EM 122 / EM 124

---

## Plot Types

1. **Depth**: Swath coverage scatter plot, colored by depth (shallow = red, deep = blue)
2. **Backscatter**: Acoustic backscatter amplitude visualization
3. **Ping Mode**: Depth mode over time (Very Shallow, Shallow, Medium, Deep, etc.)
4. **Pulse Form**: Continuous Wave (CW) vs. Frequency Modulated (FM) pulse forms
5. **Swath Mode**: Single vs. Dual swath operation
6. **Frequency**: Operating frequency over time
7. **Data Rate**: Data acquisition rate over time
8. **Timing**: Ping interval and timing analysis
9. **Parameters**: Runtime parameter log and search

---

## Coverage Trend Analysis

The **Trend** tab provides a full workflow for determining and exporting the swath coverage trend:

1. **Calculate**: Choose a source (Swath or Archive), a calculation method, the number of depth bands (steps), and a minimum point count per band, then click "Calculate Coverage Trend".
2. **Digitize**: Click "Digitize Trend" and click directly on the depth plot to manually add depth/width points. New points are merged with existing ones, sorted by depth.
3. **Edit**: Use "Edit Depth Band Width" to drag trend points interactively. Negative widths are prevented; the original position is shown in blue and the dragged position in red.
4. **Review**: The trend table shows Depth (m), Width (m), and # Points for each band. Cells in the Width column are editable; the # Points column is read-only.
5. **Export**: With "Show Coverage Trend" enabled, click "Export Gap Filler" to export the trend as a Gap Filler import text file.

### Calculation Methods
| Method | Description |
|---|---|
| Mean | Mean of absolute swath width per depth band |
| Mean+σ | Mean + one standard deviation (~84th percentile for Gaussian data) |
| Mean+2σ | Mean + two standard deviations (~97.7th percentile) |
| Spline | Cubic smoothing spline anchored through the origin |

---

## Performance Tips

### For Large Datasets
- **Use PKL Files**: Convert raw files to PKL format first for significantly faster loading
- **Enable Compression**: Reduces file sizes by 30–70% with minimal performance impact
- **Limit Point Count**: Use the Filter tab "Limit plotted point count" option for faster rendering
- **Apply Filters**: Reduce data before plotting using depth, angle, or width filters

### For Batch Processing
- Convert multiple files to PKL format using the KMALL to PKL Converter or the "Convert to Swath PKL" button in the plotter
- Load PKL files directly in the plotter for faster processing
- Use the Archive functionality to compare different datasets

---

## Troubleshooting

### Common Issues

1. **No data plotted after loading a .all file**
   - Ensure the `libs/parseEM.py` module is present in the `libs/` folder — it provides the `.all` datagram parsers

2. **Import Errors**
   ```
   Error: Could not import libraries from libs folder
   ```
   Ensure the `libs/` folder is present in the same directory as the scripts

3. **PyQt6 Not Found**
   ```
   Error: PyQt6 is not installed
   ```
   Install PyQt6: `pip install PyQt6`

4. **Memory Errors with Large Files**
   - Convert raw files to PKL format first
   - Enable "Limit plotted point count" in the Filter tab
   - Process files individually

5. **File Permission Errors when writing PKL files**
   - Choose a different output directory or run as administrator

### Getting Help

1. Check the **Activity Log** in the left panel for detailed error messages
2. Ensure all dependencies are installed correctly
3. Verify the directory structure is correct
4. Try processing a single small file first

---

## Version History

### Swath Coverage Plotter
- **v2026.03**: Fixed .all file loading (corrected `parseEM` import in `readALLswath`); fixed `last_depth_clim` crash on first plot with no valid data; fixed empty array crash in `plot_coverage`
- **v2026.02**: Coverage trend tab overhaul — Method pulldown (Mean, Mean+σ, Mean+2σ, Spline), # of Steps pulldown, Min Points parameter, # Points column in trend table, Digitize Trend button, Edit Depth Band Width drag editing, Clear All Points button, mirrored Show Coverage Trend checkbox, Width (Swath/Archive) filter, cursor shows filename only, Converting to PKL progress bar below Activity Log
- **v2026.01**: Dark theme (Fusion + dark palette), Export Plots groupbox moved to left panel, Archive PKL Add Directory and Include Subdirectories, Show Path for all file lists, layout and naming updates
- **v2025.12**: Fixed layout for Swath PKL and Archive PKL management; Export Plots groupbox; relabeled "Include Subdirectories"
- **v2025.11**: Fixed plot decimation to only run when filter settings are changed
- **v2025.10**: Reorganized sources area into tabs
- **v2025.09**: GUI improvements, fixed plot scaling
- **v2025.08**: Enhanced theoretical performance plotting
- **v2025.07**: Improved swath coverage curve specification plotting
- **v2025.06**: Fixed issue with loading new PKL files, added loading directory
- **v2025.05**: Fixed frequency plot export size and text field styling
- **v2025.03**: Fixed various issues with the swath coverage plotter
- **v2025.02**: New features, new swath PKL format, GUI redesign

### KMALL to PKL Converter
- **v2026.01**: Dark theme (Fusion + dark palette); executable naming `KMALL_to_SwathPKL_Converter_v` + version
- **v2025.02**: Added subdirectory search option
- **v2025.01**: Initial release — GUI interface, batch processing, compression support, progress tracking, error handling

---

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

- **Email**: kjerram@ccom.unh.edu, pjohnson@ccom.unh.edu
- **Repository**: https://github.com/seamapper/SwathCoverage
- **Issues**: https://github.com/seamapper/SwathCoverage/issues
