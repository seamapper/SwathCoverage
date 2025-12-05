# KMALL to PKL Converter

A standalone GUI application to convert KMALL and ALL files to optimized PKL files for use with the Swath Coverage Plotter.

## Features

- **Simple GUI Interface**: Easy-to-use graphical interface for file selection and conversion
- **Batch Processing**: Convert multiple files at once
- **Progress Tracking**: Real-time progress bar and status updates
- **Compression Support**: Optional gzip compression for 30-70% smaller files
- **Error Handling**: Comprehensive error reporting and logging
- **File Validation**: Automatic detection of up-to-date files (skip if newer)

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
The converter requires the multibeam_tools libraries from the main MultibeamToolsAI project:
- `swath_fun.py`
- `swath_coverage_lib.py`
- `kmall.py`
- `parseEM.py`
- `file_fun.py`

## Installation

### 1. Install Python Dependencies
```bash
pip install -r converter_requirements.txt
```

### 2. Verify Directory Structure
Ensure the MultibeamToolsAI directory structure is correct:
```
MultibeamToolsAI/
├── multibeam_tools/
│   └── libs/
│       ├── swath_fun.py
│       ├── swath_coverage_lib.py
│       ├── kmall.py
│       ├── parseEM.py
│       └── file_fun.py
└── kmall_to_pkl_converter.py
```

## Usage

### Method 1: Python Script
```bash
python kmall_to_pkl_converter.py
```

### Method 2: Windows Batch File
```bash
run_converter.bat
```

## How to Use

1. **Launch the Application**
   - Run the converter using one of the methods above

2. **Select Input Files**
   - Click "Select KMALL/ALL Files"
   - Choose one or more .kmall or .all files
   - The application will show the number of selected files

3. **Choose Output Directory**
   - Click "Select Output Directory"
   - Choose where to save the converted PKL files

4. **Set Options**
   - Check "Enable compression" for smaller files (recommended)
   - Uncheck for faster conversion (larger files)

5. **Start Conversion**
   - Click "Start Conversion"
   - Monitor progress in the progress bar and log area
   - The application will show real-time status updates

6. **Review Results**
   - A summary dialog will show conversion results
   - Check the log area for detailed information

## Output Files

The converter creates PKL files with the following naming convention:
- Input: `survey_data.kmall`
- Output: `survey_data.pkl`

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
- Select multiple files at once for efficient batch conversion
- The converter skips files that are already up-to-date
- Failed files are reported in the summary

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```
   Error: Could not import multibeam_tools libraries
   ```
   **Solution**: Ensure the MultibeamToolsAI directory structure is correct

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
2. Ensure all dependencies are installed correctly
3. Verify the MultibeamToolsAI directory structure
4. Try converting a single small file first

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
3. **Optimize**: Create efficient data structures
4. **Compress**: Apply gzip compression (optional)
5. **Save**: Write optimized PKL file

## License

This converter is part of the MultibeamToolsAI project. See the main project LICENSE file for details.

## Version History

- **v1.0**: Initial release with basic conversion functionality
  - GUI interface
  - Batch processing
  - Compression support
  - Progress tracking
  - Error handling
