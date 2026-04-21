# KMALL to PKL Converter

A standalone GUI application to convert KMALL and ALL files to optimized PKL files for use with the Swath Coverage Plotter.

## Features

- **Simple GUI Interface**: Easy-to-use graphical interface (Fusion dark theme) for file selection and conversion
- **Batch Processing**: Convert multiple files at once
- **Directory Support**: Add entire directories; optional "Include Subdirectories" to search recursively
- **Archive Mode**: Optional **Make Archive PKL** mode creates one archive PKL from all selected raw files
- **Progress Tracking**: Real-time progress bar and status updates
- **Compression Support**: Optional gzip compression for 30-70% smaller files
- **Overwrite Option**: Option to overwrite existing PKL files
- **Error Handling**: Comprehensive error reporting and logging
- **File Validation**: Automatic detection of up-to-date files (skip if newer when overwrite is off)
- **Session Persistence**: Remembers last directories and settings; "Clear Settings" to reset

## Requirements

### Python Dependencies
- Python 3.8 or later
- PyQt6 (GUI framework)
- NumPy (numerical computing)
- SciPy (scientific computing)

### Optional Dependencies
- pyproj (coordinate transformations)
- utm (UTM coordinate conversions)

### Multibeam Tools Libraries
The converter uses the `libs` folder in the same directory as the script:
- `swath_fun.py`
- `kmall.py`
- `parseEM.py`
(Other libs may be pulled in as dependencies.)

## Installation

### 1. Install Python Dependencies
```bash
pip install PyQt6 numpy scipy
```
(Optional: `pip install pyinstaller` if you plan to build the Windows executable.)

### 2. Verify Directory Structure
Ensure the project structure includes the `libs` folder:
```
SwathCoverage/
├── libs/
│   ├── swath_fun.py
│   ├── kmall.py
│   ├── parseEM.py
│   └── ...
├── kmall_to_pkl_converter.py
└── ...
```

## Usage

### Method 1: Python Script
```bash
python kmall_to_pkl_converter.py
```

### Method 2: Windows Executable
```bash
KMALL_to_SwathPKL_Converter_v2026.03.exe
```
Executables are named `KMALL_to_SwathPKL_Converter_v` + version (from the script). Build with (run from the project directory):
```bash
pyinstaller KMALL_to_PKL_Converter.spec --clean
```
Or run the project build script:
```bash
build_kmall_exe.bat
```

## How to Use

1. **Launch the Application**
   - Run the converter via script or the built executable.

2. **Select Input Files**
   - **Select KMALL/ALL Files**: Choose one or more .kmall or .all files, or
   - **Select Directory**: Add all .kmall/.all files in a folder. Check **Include Subdirectories When Adding A Directory** to search subfolders recursively.
   - The application shows the number of selected files.

3. **Choose Output Directory**
   - Click "Select Output Directory" and choose where to save the converted PKL files.

4. **Set Options**
   - **Enable compression**: For smaller files (recommended). Uncheck for faster conversion and larger files.
   - **Overwrite existing PKL files**: Check to replace existing outputs; leave unchecked to skip files that are already up-to-date.
   - **Make Archive PKL**: When enabled, replaces per-file output and creates one archive PKL from all selected raw files.

5. **Start Conversion**
   - Click "Start Conversion" and monitor the progress bar and log.
   - If **Make Archive PKL** is enabled, enter the archive basename when prompted.
   - A summary dialog appears when done.

6. **Review Results**
   - Check the summary and log for converted, skipped, and failed counts and any errors.

## Output Files

The converter creates PKL files with the following naming convention:
- Input: `survey_data.kmall`
- Output: `survey_data.pkl`

In **Make Archive PKL** mode:
- Output: `<archive_basename>.pkl`
- Contents: one archive detection dictionary combining all selected files, compatible with the plotter's Archive PKL loader.

### PKL File Contents
Each PKL file contains optimized data structures for fast loading:
- **Coordinates**: X, Y, Z positions for port and starboard soundings
- **Backscatter**: Acoustic backscatter values
- **Metadata**: File information, conversion time, compression status
- **Parameters**: Ping mode, pulse form, swath mode, frequency data

## Performance Tips

### For Large Files
- Enable compression to reduce file sizes by 30-70%
- The converter automatically handles memory management
- Progress is shown in real-time

### For Batch Processing
- Select multiple files or use "Select Directory" (with optional "Include Subdirectories") for batch conversion.
- The converter skips files that are already up-to-date unless "Overwrite existing PKL files" is checked.
- Failed files are reported in the summary and log.

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```
   Error: Could not import libraries from libs folder
   ```
   **Solution**: Ensure the `libs/` folder is present next to the script (or executable) with the required modules.

2. **PyQt6 Not Found**
   ```
   Error: PyQt6 is not installed
   ```
   **Solution**: Install PyQt6: `pip install PyQt6`

3. **File Permission Errors**
   ```
   Permission denied when writing to output directory
   ```
   **Solution**: Choose a different output directory or run as administrator

4. **Memory Errors with Large Files**
   ```
   Out of memory error
   ```
   **Solution**: Process files individually or increase system memory

### Getting Help

If you encounter issues:
1. Check the log area for detailed error messages
2. Ensure all dependencies are installed and the `libs/` folder is present
3. Try converting a single small file first

## Technical Details

### File Format Support
- **KMALL**: Kongsberg's modern multibeam format
- **ALL**: Kongsberg's legacy format
- **PKL**: Optimized pickle format for fast loading

### Compression
- Uses gzip compression with level 6 (good balance of speed vs. compression)
- Reduces file sizes by 30-70% typically
- Slightly slower conversion but much faster loading

### Data Processing
1. **Parse**: Extract data from KMALL/ALL files
2. **Process**: Convert to plotting-compatible format
3. **Mode Handling**: Apply mode interpretation and coverage sorting compatible with plotter expectations
4. **Optimize**: Create efficient data structures
5. **Compress**: Apply gzip compression (optional)
6. **Save**: Write optimized PKL output (per-file or archive)

## License

This converter is part of the Swath Coverage Analysis Tools project. See the project LICENSE file for details.

## Version History

- **v2026.03**: Added **Make Archive PKL** mode with basename prompt and single-file archive output compatible with plotter archive loading
- **v2026.01**: Dark theme (Fusion + dark palette); executable naming `KMALL_to_SwathPKL_Converter_v` + version
- **v2025.02**: Include subdirectories when adding a directory; updated executable naming
- **v2025.01**: Initial release
  - GUI interface
  - Batch processing
  - Compression support
  - Progress tracking
  - Error handling
