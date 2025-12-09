#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KMALL to Swath PKL Converter

A standalone GUI application to convert KMALL files to optimized PKL files
for use with the Swath Coverage Plotter.

Features:
- Simple GUI for file selection and output directory
- Progress tracking with progress bar
- Compression options for smaller file sizes
- Batch processing of multiple files
- Error handling and logging

Author: Paul Johnson
"""
# __version__ = "2025.01"  # First Release of the program
__version__ = "2025.02"  # Added subdirectory search option

import sys
import os
import pickle
import gzip
import time
import datetime
from pathlib import Path
from time import process_time
import json

# PyQt6 imports
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                           QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
                           QMessageBox, QCheckBox, QGroupBox, QWidget, QGridLayout)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Add the current directory to the path to allow importing from libs folder
# Handle PyInstaller onefile mode (extracts to temporary directory)
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    current_dir = sys._MEIPASS
else:
    # Running as script
    current_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, current_dir)

try:
    # Try importing from the libs folder
    from libs.swath_fun import readKMALLswath, readALLswath
    print("Successfully imported libraries from libs folder")
    MULTIBEAM_TOOLS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import libraries from libs folder: {e}")
    print("Please ensure the libs folder is present in the same directory as this script")
    # We'll handle this gracefully in the GUI
    MULTIBEAM_TOOLS_AVAILABLE = False


def load_session_config():
    """Load session configuration from file"""
    # Get the directory where the executable or script is located
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - save config next to exe
        exe_dir = os.path.dirname(sys.executable)
    else:
        # Running as script
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(exe_dir, 'converter_session.json')
    default_config = {
        'last_input_dir': '',
        'last_output_dir': '',
        'last_compression_setting': True,
        'last_include_subdirs_setting': False
    }
    
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
                # Merge with defaults to handle missing keys
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
    except Exception as e:
        print(f"Warning: Could not load session config: {e}")
    
    return default_config


def save_session_config(config):
    """Save session configuration to file"""
    # Get the directory where the executable or script is located
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - save config next to exe
        exe_dir = os.path.dirname(sys.executable)
    else:
        # Running as script
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(exe_dir, 'converter_session.json')
    
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save session config: {e}")


class ConversionWorker(QThread):
    """Worker thread for file conversion to prevent GUI freezing"""
    progress_updated = pyqtSignal(int, str)  # progress value, status message
    conversion_complete = pyqtSignal(dict)  # results dictionary
    error_occurred = pyqtSignal(str)  # error message
    
    def __init__(self, input_files, output_dir, use_compression=True, overwrite_existing=False):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.use_compression = use_compression
        self.overwrite_existing = overwrite_existing
        self.cancelled = False
    
    def run(self):
        """Main conversion process"""
        try:
            # Start timing for the entire conversion process
            total_start_time = time.time()
            
            results = {
                'converted': 0,
                'skipped': 0,
                'failed': 0,
                'total_size_saved': 0,
                'errors': []
            }
            
            for i, input_file in enumerate(self.input_files):
                if self.cancelled:
                    break
                
                filename = os.path.basename(input_file)
                self.progress_updated.emit(i, f"Converting {filename}...")
                
                # Start timing for this file
                start_time = time.time()
                
                try:
                    # Check if output file already exists and is newer
                    output_file = os.path.join(self.output_dir, 
                                             filename + '.pkl')
                    
                    if os.path.exists(output_file) and not self.overwrite_existing:
                        input_mtime = os.path.getmtime(input_file)
                        output_mtime = os.path.getmtime(output_file)
                        if output_mtime > input_mtime:
                            results['skipped'] += 1
                            self.progress_updated.emit(i + 1, f"Skipped {filename} (already up-to-date)")
                            continue
                    
                    # Convert the file
                    success = self.convert_single_file(input_file, output_file)
                    
                    # Calculate conversion time
                    end_time = time.time()
                    conversion_time = end_time - start_time
                    
                    if success:
                        results['converted'] += 1
                        # Calculate size savings
                        input_size = os.path.getsize(input_file)
                        if os.path.exists(output_file):
                            output_size = os.path.getsize(output_file)
                            size_saved = input_size - output_size
                            results['total_size_saved'] += size_saved
                            self.progress_updated.emit(i + 1, 
                                                     f"Converted {filename} in {conversion_time:.2f}s "
                                                     f"({input_size/(1024*1024):.1f}MB → {output_size/(1024*1024):.1f}MB)")
                        else:
                            # Output file wasn't created (shouldn't happen if success=True, but handle gracefully)
                            self.progress_updated.emit(i + 1, 
                                                     f"Converted {filename} in {conversion_time:.2f}s "
                                                     f"({input_size/(1024*1024):.1f}MB → output file not found)")
                    else:
                        results['failed'] += 1
                        results['errors'].append(f"Failed to convert {filename}")
                        self.progress_updated.emit(i + 1, f"Failed to convert {filename} (after {conversion_time:.2f}s)")
                        
                except Exception as e:
                    # Calculate time even for failed conversions
                    end_time = time.time()
                    conversion_time = end_time - start_time
                    
                    results['failed'] += 1
                    error_msg = f"Error converting {filename} (after {conversion_time:.2f}s): {str(e)}"
                    results['errors'].append(error_msg)
                    self.progress_updated.emit(i + 1, error_msg)
                    print(f"Detailed error for {filename}: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Calculate total conversion time
            total_end_time = time.time()
            total_conversion_time = total_end_time - total_start_time
            results['total_time'] = total_conversion_time
            
            self.conversion_complete.emit(results)
            
        except Exception as e:
            self.error_occurred.emit(f"Conversion process failed: {str(e)}")
    
    def convert_single_file(self, input_file, output_file):
        """Convert a single file from KMALL/ALL to PKL format"""
        try:
            start_time = process_time()
            
            # Check if multibeam_tools libraries are available
            if not MULTIBEAM_TOOLS_AVAILABLE:
                print(f"Multibeam tools libraries not available - creating minimal PKL file for {input_file}")
                return self.create_minimal_pkl(input_file, output_file)
            
            # Determine file type and parse accordingly
            if input_file.lower().endswith('.kmall'):
                # Parse KMALL file
                data = self.parse_kmall_file(input_file)
            elif input_file.lower().endswith('.all'):
                # Parse ALL file
                data = self.parse_all_file(input_file)
            else:
                raise ValueError(f"Unsupported file format: {input_file}")
            
            if not data:
                return False
            
            # Process the data for plotting
            processed_data = self.process_data_for_plotting(data)
            
            # If processing failed, don't create a PKL file
            if processed_data is None:
                print(f"Data processing failed for {input_file} - no PKL file will be created")
                return False
            
            # The processed_data already has the correct nested structure with metadata
            optimized_data = processed_data
            
            # Save as pickle file
            if self.use_compression:
                with gzip.open(output_file, 'wb', compresslevel=6) as f:
                    pickle.dump(optimized_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            else:
                with open(output_file, 'wb') as f:
                    pickle.dump(optimized_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            return True
            
        except Exception as e:
            print(f"Error converting {input_file}: {e}")
            return False
    
    def create_minimal_pkl(self, input_file, output_file):
        """Create a minimal PKL file when multibeam_tools libraries are not available"""
        try:
            # Create minimal data structure
            minimal_data = {
                'fname': os.path.basename(input_file),
                'fsize': os.path.getsize(input_file),
                'fsize_wc': os.path.getsize(input_file),
                'conversion_time': datetime.datetime.now().isoformat(),
                'compressed': self.use_compression,
                'y_port': [],
                'y_stbd': [],
                'z_port': [],
                'z_stbd': [],
                'bs_port': [],
                'bs_stbd': [],
                'ping_mode': [],
                'pulse_form': [],
                'swath_mode': [],
                'frequency': [],
                'note': 'Minimal PKL file - multibeam_tools libraries not available'
            }
            
            # Save as pickle file
            if self.use_compression:
                with gzip.open(output_file, 'wb', compresslevel=6) as f:
                    pickle.dump(minimal_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            else:
                with open(output_file, 'wb') as f:
                    pickle.dump(minimal_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            return True
            
        except Exception as e:
            print(f"Error creating minimal PKL for {input_file}: {e}")
            return False
    
    def parse_kmall_file(self, filename):
        """Parse KMALL file using the proper readKMALLswath function for correct swath data extraction"""
        if not MULTIBEAM_TOOLS_AVAILABLE:
            raise ImportError("Multibeam tools libraries not available")
        
        try:
            # Import the proper readKMALLswath function
            from libs.swath_fun import readKMALLswath
            import os
            
            # Use the proper readKMALLswath function which handles coordinate conversion correctly
            data = readKMALLswath(self, filename, print_updates=True, read_mode='full')
            
            # Add file size information
            data['fsize'] = os.path.getsize(filename)
            data['fsize_wc'] = os.path.getsize(filename)
            
            print(f"Successfully parsed KMALL file: {filename}")
            print(f"Found {len(data['XYZ'])} pings")
            return data
            
        except Exception as e:
            print(f"Error parsing KMALL file {filename}: {e}")
            raise
    
    def parse_all_file(self, filename):
        """Parse ALL file using the proper readALLswath function for correct swath data extraction"""
        if not MULTIBEAM_TOOLS_AVAILABLE:
            raise ImportError("Multibeam tools libraries not available")
        
        try:
            import os
            from libs.swath_fun import readALLswath, convertXYZ
            
            # Use the proper readALLswath function which handles coordinate conversion correctly
            data = readALLswath(self, filename, print_updates=True, parse_outermost_only=False)
            
            # Convert XYZ coordinates for ALL files (required step)
            converted_data = convertXYZ({0: data}, print_updates=True)
            data = converted_data[0]
            
            # Add file size information
            data['fsize'] = os.path.getsize(filename)
            data['fsize_wc'] = os.path.getsize(filename)
            
            print(f"Successfully parsed ALL file: {filename}")
            print(f"Found {len(data['XYZ'])} pings")
            return data
                
        except Exception as e:
            print(f"Error parsing ALL file {filename}: {e}")
            raise
    
    def process_data_for_plotting(self, data):
        """Process parsed data for PKL conversion - match plotter's convert_files_to_pickle structure"""
        if not MULTIBEAM_TOOLS_AVAILABLE:
            print("Multibeam tools libraries not available - conversion will fail")
            return None

        try:
            print("Processing data for PKL conversion...")
            
            # The parsed data is a dictionary, so we need to access it differently
            if isinstance(data, dict):
                # Check if we have XYZ data directly in the dictionary
                if 'XYZ' in data:
                    xyz_data = data['XYZ']
                    print(f"Found XYZ data with {len(xyz_data)} pings")
                    
                    # Get file information
                    fname = data.get('fname', 'unknown')
                    fsize = data.get('fsize', 0)
                    fsize_wc = data.get('fsize_wc', 0)
                    
                    # Ensure fname is a string, not a list
                    if isinstance(fname, list) and len(fname) > 0:
                        fname = fname[0]  # Take the first element if it's a list
                    elif not isinstance(fname, str):
                        fname = str(fname)  # Convert to string if it's not already
                    
                    if not xyz_data:
                        print("No XYZ data found in parsed file")
                        return None
                    
                    # Replicate sortDetectionsCoverage functionality to create the exact structure
                    # that the plotter expects in its PKL files
                    det_key_list = ['fname', 'model', 'datetime', 'date', 'time', 'sn',
                                  'y_port', 'y_stbd', 'z_port', 'z_stbd', 'bs_port', 'bs_stbd', 
                                  'rx_angle_port', 'rx_angle_stbd',
                                  'ping_mode', 'pulse_form', 'swath_mode', 'frequency',
                                  'max_port_deg', 'max_stbd_deg', 'max_port_m', 'max_stbd_m',
                                  'tx_x_m', 'tx_y_m', 'tx_z_m', 'tx_r_deg', 'tx_p_deg', 'tx_h_deg',
                                  'rx_x_m', 'rx_y_m', 'rx_z_m', 'rx_r_deg', 'rx_p_deg', 'rx_h_deg',
                                  'aps_num', 'aps_x_m', 'aps_y_m', 'aps_z_m', 'wl_z_m',
                                  'bytes', 'fsize', 'fsize_wc']
                    
                    det = {k: [] for k in det_key_list}
                    
                    # Process each ping to find outermost valid soundings
                    for p in range(len(xyz_data)):
                        ping_data = xyz_data[p]
                        
                        # Get ping info
                        ping_info = data.get('pingInfo', [])
                        if p < len(ping_info):
                            ping_info_data = ping_info[p]
                        else:
                            ping_info_data = {}
                        
                        # Extract sounding data
                        if 'z_reRefPoint_m' in ping_data and 'y_reRefPoint_m' in ping_data:
                            z_values = ping_data['z_reRefPoint_m']
                            y_values = ping_data['y_reRefPoint_m']
                            bs_values = ping_data.get('reflectivity1_dB', [])
                            angle_values = ping_data.get('beamAngleReRx_deg', [])
                            
                            if len(z_values) > 0 and len(y_values) > 0:
                                # Find outermost valid soundings (port and starboard)
                                port_idx = None
                                stbd_idx = None
                                
                                # Find outermost port sounding (most negative y)
                                for i, y in enumerate(y_values):
                                    if y < 0:  # Port side
                                        if port_idx is None or y < y_values[port_idx]:
                                            port_idx = i
                                
                                # Find outermost starboard sounding (most positive y)
                                for i, y in enumerate(y_values):
                                    if y > 0:  # Starboard side
                                        if stbd_idx is None or y > y_values[stbd_idx]:
                                            stbd_idx = i
                                
                                # Add port and starboard soundings (one entry per ping, not two)
                                if port_idx is not None:
                                    det['y_port'].append(y_values[port_idx])
                                    det['z_port'].append(z_values[port_idx])
                                    det['bs_port'].append(bs_values[port_idx] if port_idx < len(bs_values) else 0)
                                    det['rx_angle_port'].append(angle_values[port_idx] if port_idx < len(angle_values) else 0)
                                else:
                                    det['y_port'].append(0)
                                    det['z_port'].append(0)
                                    det['bs_port'].append(0)
                                    det['rx_angle_port'].append(0)
                                
                                if stbd_idx is not None:
                                    det['y_stbd'].append(y_values[stbd_idx])
                                    det['z_stbd'].append(z_values[stbd_idx])
                                    det['bs_stbd'].append(bs_values[stbd_idx] if stbd_idx < len(bs_values) else 0)
                                    det['rx_angle_stbd'].append(angle_values[stbd_idx] if stbd_idx < len(angle_values) else 0)
                                else:
                                    det['y_stbd'].append(0)
                                    det['z_stbd'].append(0)
                                    det['bs_stbd'].append(0)
                                    det['rx_angle_stbd'].append(0)
                                
                                # Add file info (one entry per ping)
                                det['fname'].append(fname)
                                
                                # Add acquisition parameters (one entry per ping)
                                det['ping_mode'].append(ping_info_data.get('depthMode', 0))
                                det['pulse_form'].append(ping_info_data.get('pulseForm', 0))
                                det['swath_mode'].append(ping_info_data.get('swathMode', 0))
                                det['frequency'].append(ping_info_data.get('frequencyMode_Hz', 0))
                                
                                # Add other required fields with default values (one entry per ping)
                                for key in ['model', 'datetime', 'date', 'time', 'sn', 'max_port_deg', 'max_stbd_deg', 
                                          'max_port_m', 'max_stbd_m', 'tx_x_m', 'tx_y_m', 'tx_z_m', 'tx_r_deg', 
                                          'tx_p_deg', 'tx_h_deg', 'rx_x_m', 'rx_y_m', 'rx_z_m', 'rx_r_deg', 
                                          'rx_p_deg', 'rx_h_deg', 'aps_num', 'aps_x_m', 'aps_y_m', 'aps_z_m', 
                                          'wl_z_m', 'bytes']:
                                    det[key].append(0)
                    
                    # Create the optimized data structure exactly like the plotter does
                    optimized_data = {}
                    
                    # Copy essential fields for plotting (exactly like the plotter)
                    essential_fields = [
                        'fname', 'model', 'datetime', 'date', 'time', 'sn',
                        'y_port', 'y_stbd', 'z_port', 'z_stbd', 
                        'bs_port', 'bs_stbd', 'rx_angle_port', 'rx_angle_stbd',
                        'ping_mode', 'pulse_form', 'swath_mode', 'frequency',
                        'max_port_deg', 'max_stbd_deg', 'max_port_m', 'max_stbd_m',
                        'tx_x_m', 'tx_y_m', 'tx_z_m', 'tx_r_deg', 'tx_p_deg', 'tx_h_deg',
                        'rx_x_m', 'rx_y_m', 'rx_z_m', 'rx_r_deg', 'rx_p_deg', 'rx_h_deg',
                        'aps_num', 'aps_x_m', 'aps_y_m', 'aps_z_m', 'wl_z_m',
                        'bytes', 'fsize', 'fsize_wc'
                    ]
                    
                    for field in essential_fields:
                        if field in det:
                            optimized_data[field] = det[field]
                    
                    # Ensure fname is set correctly - it should be a string, not a list
                    if 'fname' in optimized_data and isinstance(optimized_data['fname'], list):
                        # If fname is a list, take the first element
                        optimized_data['fname'] = optimized_data['fname'][0] if optimized_data['fname'] else fname
                    elif 'fname' not in optimized_data or optimized_data['fname'] is None:
                        optimized_data['fname'] = fname
                    
                    # Add minimal XYZ data with only essential fields (like the plotter)
                    if 'XYZ' in data:
                        optimized_data['XYZ'] = []
                        for xyz_entry in data['XYZ']:
                            minimal_xyz = {
                                'bytes_from_last_ping': xyz_entry.get('bytes_from_last_ping', 0),
                                'z_reRefPoint_m': xyz_entry.get('z_reRefPoint_m', []),
                                'y_reRefPoint_m': xyz_entry.get('y_reRefPoint_m', []),
                                'x_reRefPoint_m': xyz_entry.get('x_reRefPoint_m', []),
                                'deltaLatitude_deg': xyz_entry.get('deltaLatitude_deg', []),
                                'deltaLongitude_deg': xyz_entry.get('deltaLongitude_deg', []),
                                'detectionType': xyz_entry.get('detectionType', []),
                                'reflectivity1_dB': xyz_entry.get('reflectivity1_dB', []),
                                'beamAngleReRx_deg': xyz_entry.get('beamAngleReRx_deg', []),
                                'PING_MODE': xyz_entry.get('PING_MODE', 0),
                                'PULSE_FORM': xyz_entry.get('PULSE_FORM', 0),
                                'FREQUENCY': xyz_entry.get('FREQUENCY', 'NA')
                            }
                            optimized_data['XYZ'].append(minimal_xyz)
                    
                    # Add essential HDR data required by interpretMode function (one per ping)
                    optimized_data['HDR'] = []
                    if 'HDR' in data and len(data['HDR']) > 0:
                        for hdr_entry in data['HDR']:
                            minimal_hdr = {
                                'echoSounderID': hdr_entry.get('echoSounderID', 712),
                                'dgdatetime': hdr_entry.get('dgdatetime', datetime.datetime.now())
                            }
                            optimized_data['HDR'].append(minimal_hdr)
                    else:
                        # Create HDR data with one entry per ping
                        for _ in range(len(xyz_data)):
                            minimal_hdr = {
                                'echoSounderID': 712,
                                'dgdatetime': datetime.datetime.now()
                            }
                            optimized_data['HDR'].append(minimal_hdr)
                    
                    # Add essential RTP data required by interpretMode function (one per ping)
                    optimized_data['RTP'] = []
                    if 'RTP' in data and len(data['RTP']) > 0:
                        for rtp_entry in data['RTP']:
                            minimal_rtp = {
                                'depthMode': rtp_entry.get('depthMode', 0),
                                'pulseForm': rtp_entry.get('pulseForm', 0)
                            }
                            optimized_data['RTP'].append(minimal_rtp)
                    else:
                        # Create RTP data with one entry per ping
                        for _ in range(len(xyz_data)):
                            minimal_rtp = {
                                'depthMode': 0,
                                'pulseForm': 0
                            }
                            optimized_data['RTP'].append(minimal_rtp)
                    
                    # Add essential IP data required by sortDetectionsCoverage
                    if 'IP' in data:
                        optimized_data['IP'] = {
                            'install_txt': data['IP'].get('install_txt', ['SN=0,SWLZ=0,TRAI_TX1X=0;Y=0;Z=0;R=0;P=0;H=0,TRAI_RX1X=0;Y=0;Z=0;R=0;P=0;H=0'])
                        }
                    
                    # Add essential IOP data required by sortDetectionsCoverage
                    if 'IOP' in data:
                        optimized_data['IOP'] = {
                            'header': data['IOP'].get('header', [{'dgdatetime': datetime.datetime.now()}]),
                            'runtime_txt': data['IOP'].get('runtime_txt', ['Max angle Port: 0\nMax angle Starboard: 0\nMax coverage Port: 0\nMax coverage Starboard: 0'])
                        }
                    
                    # Ensure fname is properly set as a string (final fix)
                    optimized_data['fname'] = str(fname)
                    
                    # Set fsize and fsize_wc as integers (not lists)
                    optimized_data['fsize'] = fsize
                    optimized_data['fsize_wc'] = fsize_wc
                    
                    # Add start_byte as a list (one per ping, like the plotter)
                    optimized_data['start_byte'] = [0] * len(xyz_data)
                    
                    # Add cmnPart field (required by the plotter) - one per ping
                    if 'cmnPart' in data:
                        optimized_data['cmnPart'] = data['cmnPart']
                    else:
                        # Create cmnPart data with one entry per ping
                        optimized_data['cmnPart'] = [0] * len(xyz_data)
                    
                    # Create the final data structure - the plotter expects the file data directly
                    # with metadata, not nested under an index
                    optimized_data['_pickle_metadata'] = {
                        'source_file': fname,  # Use the actual filename
                        'source_mtime': 0,
                        'conversion_time': datetime.datetime.now().isoformat(),
                        'version': '2.1',
                        'optimized': True,
                        'compressed': True
                    }
                    
                    data_dict = optimized_data
                    
                    print(f"Successfully processed {len(xyz_data)} pings from {fname}")
                    return data_dict
                else:
                    print("No XYZ data found in parsed file")
                    print(f"Available keys in data: {list(data.keys())}")
                    return None
            else:
                print("Data is not a dictionary - cannot process")
                return None

        except Exception as e:
            print(f"Error processing data for plotting: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def cancel(self):
        """Cancel the conversion process"""
        self.cancelled = True


class KMALLToPKLConverter(QMainWindow):
    """Main application window for KMALL to Swath PKL conversion"""
    
    def __init__(self):
        super().__init__()
        self.input_files = []
        self.output_dir = ""
        self.worker = None
        
        # Load session configuration
        self.session_config = load_session_config()
        self.last_input_dir = self.session_config.get('last_input_dir', '')
        self.last_output_dir = self.session_config.get('last_output_dir', '')
        
        self.init_ui()
        self.setup_connections()
        
        # Set output directory from session config if available
        if self.last_output_dir:
            self.output_dir = self.last_output_dir
            self.output_label.setText(f"Output: {self.last_output_dir}")
            self.update_convert_button_state()
        
        # Check if libraries are available
        if not MULTIBEAM_TOOLS_AVAILABLE:
            self.log_message("WARNING: Libraries not available")
            self.log_message("Conversion will create empty PKL files")
            self.log_message("Please ensure the libs folder is present in the same directory as this script")
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle(f"KMALL to Swath PKL Converter - V{__version__} - pjohnson@ccom.unh.edu")
        self.setGeometry(100, 100, 600, 500)
        
        # Set application-wide style to ensure text visibility
        # Use system colors that adapt to dark/light themes
        self.setStyleSheet("""
            QLabel { 
                color: palette(window-text); 
                background-color: transparent; 
            }
            QGroupBox { 
                color: palette(window-text); 
                font-weight: bold; 
            }
            QGroupBox::title { 
                color: palette(window-text); 
            }
            QPushButton { 
                color: palette(button-text); 
                background-color: palette(button); 
            }
            QCheckBox { 
                color: palette(window-text); 
            }
            QTextEdit { 
                color: palette(text); 
                background-color: palette(base); 
                border: 1px solid palette(mid); 
            }
        """)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Title
        title_label = QLabel("KMALL to Swath PKL Converter")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # File selection group
        file_group = QGroupBox("File Selection")
        file_layout = QVBoxLayout(file_group)
        
        # Input files
        input_layout = QHBoxLayout()
        self.input_label = QLabel("No files selected")
        self.input_label.setStyleSheet("border: 1px solid palette(mid); padding: 5px; background-color: palette(base); color: palette(text);")
        self.select_files_btn = QPushButton("Select KMALL/ALL Files")
        self.select_dir_btn = QPushButton("Select Directory")
        input_layout.addWidget(self.input_label, 1)
        input_layout.addWidget(self.select_files_btn)
        input_layout.addWidget(self.select_dir_btn)
        file_layout.addLayout(input_layout)
        
        # Output directory
        output_layout = QHBoxLayout()
        self.output_label = QLabel("No output directory selected")
        self.output_label.setStyleSheet("border: 1px solid palette(mid); padding: 5px; background-color: palette(base); color: palette(text);")
        self.select_output_btn = QPushButton("Select Output Directory")
        output_layout.addWidget(self.output_label, 1)
        output_layout.addWidget(self.select_output_btn)
        file_layout.addLayout(output_layout)
        
        main_layout.addWidget(file_group)
        
        # Options group
        options_group = QGroupBox("Conversion Options")
        options_layout = QVBoxLayout(options_group)
        
        self.compression_checkbox = QCheckBox("Enable compression (30-70% smaller files)")
        # Load last compression setting
        last_compression = self.session_config.get('last_compression_setting', True)
        self.compression_checkbox.setChecked(last_compression)
        options_layout.addWidget(self.compression_checkbox)
        
        self.overwrite_checkbox = QCheckBox("Overwrite existing PKL files")
        # Load last overwrite setting (default to False)
        last_overwrite = self.session_config.get('last_overwrite_setting', False)
        self.overwrite_checkbox.setChecked(last_overwrite)
        options_layout.addWidget(self.overwrite_checkbox)
        
        self.include_subdirs_checkbox = QCheckBox("Include Subdirectories When Adding A Directory")
        # Load last include subdirs setting (default to False)
        last_include_subdirs = self.session_config.get('last_include_subdirs_setting', False)
        self.include_subdirs_checkbox.setChecked(last_include_subdirs)
        options_layout.addWidget(self.include_subdirs_checkbox)
        
        main_layout.addWidget(options_group)
        
        # Progress group
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready to convert files")
        self.status_label.setStyleSheet("color: palette(window-text); font-weight: bold;")
        progress_layout.addWidget(self.status_label)
        
        # Log area
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: palette(base); color: palette(text); border: 1px solid palette(mid);")
        progress_layout.addWidget(self.log_text)
        
        main_layout.addWidget(progress_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.convert_btn = QPushButton("Start Conversion")
        self.convert_btn.setEnabled(False)
        self.convert_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 8px; }")
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 8px; }")
        
        self.clear_config_btn = QPushButton("Clear Settings")
        self.clear_config_btn.setToolTip("Clear remembered directories and settings")
        self.clear_config_btn.setStyleSheet("QPushButton { background-color: #ff9800; color: white; font-weight: bold; padding: 8px; }")
        
        button_layout.addWidget(self.convert_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.clear_config_btn)
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
        # Add some spacing
        main_layout.addStretch()
    
    def setup_connections(self):
        """Setup signal connections"""
        self.select_files_btn.clicked.connect(self.select_input_files)
        self.select_dir_btn.clicked.connect(self.select_input_directory)
        self.select_output_btn.clicked.connect(self.select_output_directory)
        self.convert_btn.clicked.connect(self.start_conversion)
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.compression_checkbox.stateChanged.connect(self.save_compression_setting)
        self.overwrite_checkbox.stateChanged.connect(self.save_overwrite_setting)
        self.include_subdirs_checkbox.stateChanged.connect(self.save_include_subdirs_setting)
        self.clear_config_btn.clicked.connect(self.clear_session_config)
    
    def select_input_files(self):
        """Select input KMALL/ALL files"""
        # Use last input directory if available
        start_dir = self.last_input_dir if self.last_input_dir else ""
        
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select KMALL or ALL files to convert",
            start_dir,
            "Multibeam Files (*.kmall *.all);;KMALL Files (*.kmall);;ALL Files (*.all);;All Files (*)"
        )
        
        if files:
            self.input_files = files
            file_count = len(files)
            if file_count == 1:
                self.input_label.setText(f"1 file selected: {os.path.basename(files[0])}")
            else:
                self.input_label.setText(f"{file_count} files selected")
            
            # Remember the directory of the first file
            if files:
                self.last_input_dir = os.path.dirname(files[0])
                self.session_config['last_input_dir'] = self.last_input_dir
                save_session_config(self.session_config)
            
            self.log_message(f"Selected {file_count} file(s) for conversion")
            self.update_convert_button_state()
    
    def select_input_directory(self):
        """Select a directory and automatically include all KMALL/ALL files in it"""
        # Use last input directory if available
        start_dir = self.last_input_dir if self.last_input_dir else ""
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select directory containing KMALL/ALL files",
            start_dir
        )
        
        if directory:
            # Check if subdirectories should be included
            include_subdirs = self.include_subdirs_checkbox.isChecked()
            
            # Find all KMALL and ALL files in the directory
            kmall_files = []
            all_files = []
            
            if include_subdirs:
                # Recursively search subdirectories
                for root, dirs, files in os.walk(directory):
                    for filename in files:
                        if filename.lower().endswith('.kmall'):
                            kmall_files.append(os.path.join(root, filename))
                        elif filename.lower().endswith('.all'):
                            all_files.append(os.path.join(root, filename))
            else:
                # Only search the selected directory (original behavior)
                for filename in os.listdir(directory):
                    filepath = os.path.join(directory, filename)
                    if os.path.isfile(filepath):
                        if filename.lower().endswith('.kmall'):
                            kmall_files.append(filepath)
                        elif filename.lower().endswith('.all'):
                            all_files.append(filepath)
            
            # Combine and sort the files
            all_input_files = sorted(kmall_files + all_files)
            
            if all_input_files:
                self.input_files = all_input_files
                file_count = len(all_input_files)
                search_type = "directory and subdirectories" if include_subdirs else "directory"
                self.input_label.setText(f"{file_count} files from {search_type}: {os.path.basename(directory)}")
                
                # Remember the directory
                self.last_input_dir = directory
                self.session_config['last_input_dir'] = self.last_input_dir
                save_session_config(self.session_config)
                
                self.log_message(f"Selected directory: {directory}")
                if include_subdirs:
                    self.log_message("Searching subdirectories recursively...")
                self.log_message(f"Found {len(kmall_files)} KMALL files and {len(all_files)} ALL files")
                self.log_message(f"Total: {file_count} file(s) for conversion")
                self.update_convert_button_state()
            else:
                search_type = "directory and subdirectories" if include_subdirs else "directory"
                self.log_message(f"No KMALL or ALL files found in {search_type}: {directory}")
                QMessageBox.information(self, "No Files Found", 
                                      f"No KMALL or ALL files found in the selected {search_type}:\n{directory}")
    
    def select_output_directory(self):
        """Select output directory for PKL files"""
        # Use last output directory if available
        start_dir = self.last_output_dir if self.last_output_dir else ""
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select output directory for PKL files",
            start_dir
        )
        
        if directory:
            self.output_dir = directory
            self.output_label.setText(f"Output: {directory}")
            
            # Remember the output directory
            self.last_output_dir = directory
            self.session_config['last_output_dir'] = self.last_output_dir
            save_session_config(self.session_config)
            
            self.log_message(f"Output directory set to: {directory}")
            self.update_convert_button_state()
    
    def update_convert_button_state(self):
        """Update the state of the convert button"""
        can_convert = bool(self.input_files) and bool(self.output_dir)
        self.convert_btn.setEnabled(can_convert)
    
    def save_compression_setting(self):
        """Save the compression setting to session config"""
        self.session_config['last_compression_setting'] = self.compression_checkbox.isChecked()
        save_session_config(self.session_config)
    
    def save_overwrite_setting(self):
        """Save the overwrite setting to session config"""
        self.session_config['last_overwrite_setting'] = self.overwrite_checkbox.isChecked()
        save_session_config(self.session_config)
    
    def save_include_subdirs_setting(self):
        """Save the include subdirectories setting to session config"""
        self.session_config['last_include_subdirs_setting'] = self.include_subdirs_checkbox.isChecked()
        save_session_config(self.session_config)
    
    def start_conversion(self):
        """Start the conversion process"""
        if not self.input_files or not self.output_dir:
            QMessageBox.warning(self, "Missing Information", 
                              "Please select input files and output directory.")
            return
        
        # Disable controls during conversion
        self.convert_btn.setEnabled(False)
        self.select_files_btn.setEnabled(False)
        self.select_output_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.input_files))
        self.progress_bar.setValue(0)
        
        # Start conversion worker thread
        self.worker = ConversionWorker(
            self.input_files,
            self.output_dir,
            self.compression_checkbox.isChecked(),
            self.overwrite_checkbox.isChecked()
        )
        
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.conversion_complete.connect(self.conversion_complete)
        self.worker.error_occurred.connect(self.conversion_error)
        
        self.worker.start()
        
        self.log_message("Conversion started...")
    
    def cancel_conversion(self):
        """Cancel the conversion process"""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        
        self.reset_ui()
        self.log_message("Conversion cancelled by user")
    
    def update_progress(self, value, message):
        """Update progress bar and status"""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        self.log_message(message)
    
    def conversion_complete(self, results):
        """Handle conversion completion"""
        self.reset_ui()
        
        # Show completion message
        converted = results['converted']
        skipped = results['skipped']
        failed = results['failed']
        size_saved = results['total_size_saved']
        
        message = f"Conversion complete!\n\n"
        message += f"Converted: {converted} files\n"
        message += f"Skipped: {skipped} files (already up-to-date)\n"
        message += f"Failed: {failed} files\n"
        
        if 'total_time' in results:
            total_time = results['total_time']
            message += f"Total time: {total_time:.2f} seconds\n"
        
        if size_saved > 0:
            message += f"Total space saved: {size_saved/(1024*1024):.1f} MB"
        
        if results['errors']:
            message += f"\n\nErrors:\n" + "\n".join(results['errors'])
        
        QMessageBox.information(self, "Conversion Complete", message)
        
        # Log summary
        self.log_message(f"Conversion completed: {converted} converted, {skipped} skipped, {failed} failed")
        if size_saved > 0:
            self.log_message(f"Total space saved: {size_saved/(1024*1024):.1f} MB")
    
    def conversion_error(self, error_message):
        """Handle conversion errors"""
        self.reset_ui()
        QMessageBox.critical(self, "Conversion Error", f"An error occurred during conversion:\n{error_message}")
        self.log_message(f"Error: {error_message}")
    
    def reset_ui(self):
        """Reset UI to initial state"""
        self.convert_btn.setEnabled(True)
        self.select_files_btn.setEnabled(True)
        self.select_output_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ready to convert files")
    
    def log_message(self, message):
        """Add message to log"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.log_text.append(log_entry)
        
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())
    
    def clear_session_config(self):
        """Clear session configuration and reset to defaults"""
        try:
            # Get the directory where the executable or script is located
            if getattr(sys, 'frozen', False):
                # Running as compiled executable - save config next to exe
                exe_dir = os.path.dirname(sys.executable)
            else:
                # Running as script
                exe_dir = os.path.dirname(os.path.abspath(__file__))
            config_file = os.path.join(exe_dir, 'converter_session.json')
            if os.path.exists(config_file):
                os.remove(config_file)
            
            # Reset to defaults
            self.session_config = {
                'last_input_dir': '',
                'last_output_dir': '',
                'last_compression_setting': True,
                'last_include_subdirs_setting': False
            }
            self.last_input_dir = ''
            self.last_output_dir = ''
            
            # Reset UI
            self.input_files = []
            self.output_dir = ""
            self.input_label.setText("No files selected")
            self.output_label.setText("No output directory selected")
            self.compression_checkbox.setChecked(True)
            self.include_subdirs_checkbox.setChecked(False)
            self.update_convert_button_state()
            
            self.log_message("Session configuration cleared - settings reset to defaults")
        except Exception as e:
            self.log_message(f"Error clearing session config: {e}")


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("KMALL to PKL Converter")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("MultibeamToolsAI")
    
    # Create and show main window
    window = KMALLToPKLConverter()
    window.show()
    
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
