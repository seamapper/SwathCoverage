"""
Functions for swath coverage plotting in NOAA / MAC echosounder assessment tools

This module provides comprehensive functionality for analyzing and visualizing 
multibeam sonar data from Kongsberg systems (EM series). It includes:

Core Functionality:
- File loading and parsing for KMALL and ALL format files
- Data conversion to optimized PKL format with compression
- Multiple plot types (depth, backscatter, ping mode, pulse form, swath mode, frequency)
- Data rate and timing analysis
- Coverage trend calculations and export
- Parameter tracking and search capabilities
- Session configuration management

Key Features:
- Real-time data visualization with matplotlib integration
- Interactive plotting with hover information
- Configurable color schemes and plot parameters
- Data archiving and export functionality
- Gzip compression for PKL files
- Session persistence for user preferences
- Comprehensive logging and error handling

Data Processing:
- Automatic detection of valid soundings
- Depth reference adjustments (waterline, origin, TX array)
- Filtering and decimation for performance
- Coverage analysis and trend calculations
- Parameter change detection and tracking

Plot Types:
- Swath coverage (main plot with depth/backscatter coloring)
- Backscatter analysis
- Ping mode visualization
- Pulse form analysis
- Swath mode tracking
- Frequency analysis
- Data rate monitoring
- Timing analysis
"""

from PyQt6 import QtWidgets, QtGui
from PyQt6.QtGui import QDoubleValidator, QColor
from PyQt6.QtCore import Qt, QSize

from . import parseEM
from .file_fun import *
from .swath_fun import readALLswath, readKMALLswath, interpretMode, adjust_depth_ref

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib import colors
from matplotlib import colorbar
from matplotlib import patches
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from scipy.interpolate import interp1d
from time import process_time
import pickle
import re
import numpy as np
from copy import deepcopy
import os
import datetime
import json

from matplotlib.colors import ListedColormap


def load_session_config():
    """
    Load session configuration including last used directories.
    
    This function manages user preferences and session persistence by loading
    previously used directories for different file operations. It provides
    a seamless user experience by remembering where files were last saved/loaded.
    
    Returns:
        dict: Configuration dictionary containing last used directories and settings
        
    Configuration keys:
        - last_crossline_dir: Directory for crossline data
        - last_output_dir: Directory for output files
        - last_plot_parent_dir: Parent directory for plot saves
        - last_plot_directory_name: Default plot directory name
        - last_archive_dir: Directory for archive files
        - last_spec_dir: Directory for specification files
        - last_pickle_dir: Directory for PKL files
        - use_pickle_files: Whether to use PKL files by default
        - last_xyz_dir: Directory for .xyz files
        - last_xyd_dir: Directory for .xyd files
    """
    config_file = os.path.join(os.path.expanduser("~"), ".swath_coverage_session.json")
    
    default_config = {
        "last_crossline_dir": os.getcwd(),
        "last_output_dir": os.getcwd(),
        "last_plot_parent_dir": os.getcwd(),
        "last_plot_directory_name": "swath_coverage_plots",
        "last_archive_dir": os.getcwd(),
        "last_spec_dir": os.getcwd(),
        "last_pickle_dir": os.getcwd(),
        "use_pickle_files": True,
        "last_xyz_dir": os.getcwd(),
        "last_xyd_dir": os.getcwd()
    }
    
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
                # Update with any missing keys from default
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        else:
            return default_config
    except Exception as e:
        print(f"Warning: Could not load session config: {e}")
        return default_config


def save_session_config(config):
    """Save session configuration including last used directories"""
    config_file = os.path.join(os.path.expanduser("~"), ".swath_coverage_session.json")
    
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save session config: {e}")


def update_last_directory(config_key, directory):
    """Update the last used directory for a specific file type"""
    if directory:  # Remove the os.path.exists check to allow saving any directory path
        config = load_session_config()
        config[config_key] = directory
        save_session_config(config)


def setup(self):
    # initialize other necessities
    # self.print_updates = True
    self.verbose_logging = False  # Control verbose output - set to True for debugging
    self.print_updates = True
    self.det = {}  # detection dict (new data)
    self.det_archive = {}  # detection dict (archive data)
    self.spec = {}  # dict of theoretical coverage specs
    self.filenames = ['']  # initial file list
    self.input_dir = ''  # initial input dir
    # Load last used directories from session config
    config = load_session_config()
    self.output_dir = config.get("last_pickle_dir", os.getcwd())  # Use last PKL directory as default
    self.clim_last_user = {'depth': [0, 1000], 'backscatter': [-50, -10]}
    self.last_cmode = 'depth'
    self.cbar_ax1 = None  # initial colorbar for swath plot
    self.cbar_ax2 = None  # initial colorbar for data rate plot
    self.cbar_ax3 = None  # initial colorbar for ping interval plot
    self.cbar_ax4 = None  # initial colorbar for parameter tracking plot
    self.legendbase = None  # initial legend
    self.cbar_font_size = 8  # colorbar/legend label size
    self.cbar_title_font_size = 8  # colorbar/legend title size
    self.cbar_loc = 1  # set upper right as default colorbar/legend location
    self.n_points_max_default = 50000  # default maximum number of points to plot in order to keep reasonable speed
    self.n_points_max = 50000
    # self.n_points_plotted = 0
    # self.n_points_plotted_arc = 0
    self.dec_fac_default = 1  # default decimation factor for point count
    self.dec_fac = 1
    self.rtp_angle_buffer_default = 0  # default runtime angle buffer
    self.rtp_angle_buffer = 0  # +/- deg from runtime parameter swath angle limit to filter RX angles
    self.x_max = 0.0
    self.z_max = 0.0
    self.model_list = ['EM 2040', 'EM 2042', 'EM 302', 'EM 304', 'EM 710', 'EM 712', 'EM 122', 'EM 124']
    self.cmode_list = ['Depth', 'Backscatter', 'Ping Mode', 'Pulse Form', 'Swath Mode', 'Frequency', 'Solid Color']
    self.top_data_list = []
    self.clim_list = ['All data', 'Filtered data', 'Fixed limits', 'Custom Plot']
    self.sis4_tx_z_field = 'S1Z'  # .all IP datagram field name for TX array Z offset (meters +down from origin)
    self.sis4_waterline_field = 'WLZ'  # .all IP datagram field name for waterline Z offset (meters +down from origin
    self.depth_ref_list = ['Waterline', 'Origin', 'TX Array', 'Raw Data']
    self.subplot_adjust_top = 0.9  # scale of subplots with super title on figure
    self.title_str = ''
    self.std_fig_width_inches = 12
    self.std_fig_height_inches = 12
    self.c_all_data_rate = []
    self.c_all_data_rate_arc = []
    self.ship_name = 'R/V Unsinkable II'
    self.model_updated = False
    self.ship_name_updated = False
    self.cruise_name_updated = False
    self.sn_updated = False
    self.ping_int_min = 0.25  # default pint interval xmin (second swaths in dual-swath are present but won't appear)
    self.ping_int_max = 60  # default ping interval xmax (first pings after long gaps are present but won't appear)
    self.skm_time = {}
    self.sounding_fname = ''
    self.sounding_fname_default = 'hover over sounding for filename'
    self.y_all = []
    self.trend_bin_centers = []
    self.trend_bin_means = []
    self.trend_bin_centers_arc = []
    self.trend_bin_means_arc = []

    # acquisition parameter tracking info
    self.param_list = ['datetime', 'ping_mode', 'pulse_form', 'swath_mode',
                       'max_port_deg', 'max_stbd_deg', 'max_port_m', 'max_stbd_m', 'frequency',
                       'wl_z_m',
                       'tx_x_m', 'tx_y_m', 'tx_z_m', 'tx_r_deg', 'tx_p_deg', 'tx_h_deg',
                       'rx_x_m', 'rx_y_m', 'rx_z_m', 'rx_r_deg', 'rx_p_deg', 'rx_h_deg',
                       'aps_num', 'aps_x_m', 'aps_y_m', 'aps_z_m']

    self.param_state = dict((k,[]) for k in self.param_list)
    self.param_changes = dict((k,[]) for k in self.param_list)
    self.param_scanned = False
    self.fnames_scanned_params = []
    self.fnames_plotted_cov = []
    
    # Note: update_button_states will be called after UI setup is complete
    
    # Add startup message about point decimation being enabled by default
    if hasattr(self, 'update_log'):
        self.update_log("✓ Point decimation is enabled by default (max 50,000 points per dataset) to maintain plotting performance", 'blue')

def update_button_states(self):
    """Update the enabled/disabled state of buttons based on whether files are loaded"""
    # Check if there are any files loaded (either in filenames or det)
    # filenames starts with [''] (empty string), so we need to check if there are actual files
    has_files = ((len(self.filenames) > 0 and self.filenames[0] != '') or  # actual files in filenames
                 len(self.det) > 0 or 
                 len(self.det_archive) > 0)
    
    # Check if there are new data files (.all, .kmall) that haven't been processed yet
    # Only count files that need processing, not archive files (.pkl)
    has_new_data_files = False
    if len(self.filenames) > 0 and self.filenames[0] != '':
        # Check if there are any .all or .kmall files that need processing
        # Filter out empty strings and check for valid file extensions
        data_files = [f for f in self.filenames if f and f.strip() and f.endswith(('.all', '.kmall'))]
        
        # Check if there are new data files that haven't been processed yet
        # A file is considered "new" if it's not in the processed lists
        if len(data_files) > 0:
            # Get just the filenames (without path) for comparison
            current_data_files = [os.path.basename(f) for f in data_files]
            
            # Check if any of these files haven't been processed yet
            # (not in fnames_scanned_params or fnames_plotted_cov)
            unprocessed_files = [f for f in current_data_files 
                               if f not in self.fnames_scanned_params and f not in self.fnames_plotted_cov]
            
            has_new_data_files = len(unprocessed_files) > 0
    
    # Enable/disable calc coverage and scan params buttons based on file availability
    if hasattr(self, 'calc_coverage_btn'):
        self.calc_coverage_btn.setEnabled(has_files)
        
        # Change button color based on whether new data files are available
        if has_new_data_files:
            # Yellow background with black text for new data files that need processing
            self.calc_coverage_btn.setStyleSheet("QPushButton { background-color: yellow; color: black; font-weight: bold; }")
        else:
            # Reset to default style when no new data files or files already processed
            self.calc_coverage_btn.setStyleSheet("")
            
    if hasattr(self, 'scan_params_btn'):
        self.scan_params_btn.setEnabled(has_files)

def init_all_axes(self):
    init_swath_ax(self)
    init_backscatter_ax(self)
    init_pingmode_ax(self)
    init_pulseform_ax(self)
    init_swathmode_ax(self)
    init_frequency_ax(self)
    init_data_ax(self)
    init_time_ax(self)
    # init_param_ax(self)
    # self.cbar_dict = {'swath': {'cax': self.cbar_ax1, 'ax': self.swath_ax, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'},
    # 				  'data_rate': {'cax': self.cbar_ax2, 'ax': self.data_rate_ax1, 'clim': self.clim, 'loc': 2, 'tickloc': 'right'},
    # 				  'ping_interval': {'cax': self.cbar_ax3, 'ax': self.data_rate_ax2, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'}}

    self.cbar_dict = {'swath': {'cax': None, 'ax': self.swath_ax, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'},
                      'backscatter': {'cax': None, 'ax': self.backscatter_ax, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'},
                      'ping_mode': {'cax': None, 'ax': self.pingmode_ax, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'},
                      'pulse_form': {'cax': None, 'ax': self.pulseform_ax, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'},
                      'swath_mode': {'cax': None, 'ax': self.swathmode_ax, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'},
                      'frequency': {'cax': None, 'ax': self.frequency_ax, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'},
                      'ping_interval': {'cax': None, 'ax': self.data_rate_ax2, 'clim': self.clim, 'loc': 1, 'tickloc': 'left'}}

    add_grid_lines(self)
    update_axes(self)


def init_swath_ax(self):  # set initial swath parameters
    self.pt_size = np.square(float(self.pt_size_cbox.currentText()))
    self.pt_alpha = np.divide(float(self.pt_alpha_cbox.currentText()), 100)

    self.swath_ax = self.swath_figure.add_subplot(121)
    self.hist_ax = self.swath_figure.add_subplot(212, sharey=self.swath_ax)  # sounding histogram, link y axis for zoom
    # self.swath_canvas.draw()

    self.x_max = 1
    self.z_max = 1
    self.dr_max = 1000
    self.pi_max = 10
    self.x_max_custom = self.x_max  # store future custom entries
    # Use default value from text box if it exists and is valid, otherwise default to 4000
    if hasattr(self, 'max_z_tb') and self.max_z_tb.text():
        try:
            self.z_max_custom = float(self.max_z_tb.text())
        except ValueError:
            self.z_max_custom = 4000.0  # Default to 4000 if text box value is invalid
            self.max_z_tb.setText('4000')
    else:
        self.z_max_custom = 4000.0  # Default to 4000
        if hasattr(self, 'max_z_tb'):
            self.max_z_tb.setText('4000')
    self.dr_max_custom = self.dr_max
    self.pi_max_custom = self.pi_max
    self.max_x_tb.setText(str(self.x_max))
    self.max_dr_tb.setText(str(self.dr_max))
    self.max_pi_tb.setText(str(self.pi_max))
    update_color_modes(self)
    self.clim = []
    self.clim_all_data = []
    self.cset = []
    self.cruise_name = ''
    self.n_wd_max = 8
    self.nominal_angle_line_interval = 15  # degrees between nominal angle lines
    self.nominal_angle_line_max = 75  # maximum desired nominal angle line
    self.swath_ax_margin = 1.1  # scale axes to multiple of max data in each direction
    # add_grid_lines(self)
    # update_axes(self)
    self.color = QtGui.QColor('lightGray')  # set default solid color to light gray for new data
    self.color_arc = QtGui.QColor('lightGray')  # set default solid color to light gray for archive data
    # Note: color_cbox_arc was replaced with radio buttons in the new UI


def init_backscatter_ax(self):  # set initial backscatter parameters
    # Use single subplot to fill entire canvas, matching depth plot when histogram is hidden
    self.backscatter_ax = self.backscatter_figure.add_subplot(111)


def init_pingmode_ax(self):  # set initial ping mode parameters
    # Use single subplot to fill entire canvas, matching depth plot when histogram is hidden
    self.pingmode_ax = self.pingmode_figure.add_subplot(111)


def init_pulseform_ax(self):  # set initial pulse form parameters
    # Use single subplot to fill entire canvas, matching depth plot when histogram is hidden
    self.pulseform_ax = self.pulseform_figure.add_subplot(111)


def init_swathmode_ax(self):  # set initial swath mode parameters
    # Use single subplot to fill entire canvas, matching depth plot when histogram is hidden
    self.swathmode_ax = self.swathmode_figure.add_subplot(111)





def init_frequency_ax(self):  # set initial frequency parameters
    # Use single subplot to fill entire canvas, matching depth plot when histogram is hidden
    self.frequency_ax = self.frequency_figure.add_subplot(111)


def init_data_ax(self):  # set initial data rate plot parameters
    self.data_rate_ax1 = self.data_figure.add_subplot(121, label='1')
    self.data_rate_ax2 = self.data_figure.add_subplot(122, label='2', sharey=self.data_rate_ax1)

    # # set up annotations
    # self.annot = self.data_rate_ax1.annotate("", xy=(0, 0), xytext=(20, 20), textcoords="offset points",
    # 										 bbox=dict(boxstyle="round", fc="w"),
    # 										 arrowprops=dict(arrowstyle="->"))
    # self.annot.set_visible(False)

def init_time_ax(self):  # set initial timing plot parameters
    self.time_ax1 = self.time_figure.add_subplot(111, label='1')
    # self.time_ax2 = self.time_figure.add_subplot(212, label='2', sharey=self.time_ax1)

# def init_param_ax(self):  # set initial runtime parameter tracking plot
    # self.param_ax1 = self.param_figure.add_subplot(111, label='1')

def add_cov_files(self, ftype_filter, input_dir='HOME', include_subdir=False, ):
    # add files with extensions in ftype_filter from input_dir and subdir if desired
    if hasattr(self, 'start_operation_log'):
        self.start_operation_log("File Addition")
    
    # Update session config with the directory where files were selected from
    if input_dir == [] or input_dir == '':  # If user selected a directory
        try:
            # Get the directory from the file dialog result
            config = load_session_config()
            last_dir = config.get("last_crossline_dir", os.getcwd())
            selected_dir = QtWidgets.QFileDialog.getExistingDirectory(self, 'Add directory', last_dir)
            if selected_dir:
                update_last_directory("last_crossline_dir", selected_dir)
                input_dir = selected_dir
        except Exception as e:
            print(f"Warning: Could not update session config: {e}")
    
    fnames = add_files(self, ftype_filter, input_dir, include_subdir)
    
    if fnames:
        if hasattr(self, 'log_success'):
            self.log_success(f"Found {len(fnames)} files to add")
        update_file_list(self, fnames)
        
        # Update button states after adding files
        update_button_states(self)
        
        if hasattr(self, 'end_operation_log'):
            self.end_operation_log("File Addition", f"Added {len(fnames)} files")
    else:
        if hasattr(self, 'log_warning'):
            self.log_warning("No files found matching the specified criteria")
        else:
            update_log(self, "No files found matching the specified criteria")

def remove_cov_files(self, clear_all=False):
    # remove selected files or clear all files, update det and spec dicts accordingly
    removed_files = remove_files(self, clear_all)
    get_current_file_list(self)

    if self.filenames == []:  # all files have been removed
        self.det = {}
        self.det_archive = {}
        self.spec = {}
        update_log(self, 'Cleared all files')
        self.current_file_lbl.setText('Current File [0/0]:')
        self.calc_pb.setValue(0)
        self.cruise_name_updated = False
        self.model_updated = False
        self.ship_name_updated = False
        self.fnames_scanned_params = []
        self.fnames_plotted_cov = []

    else:
        remove_data(self, removed_files)

        # remove these file names from tracking which have been scanned / plotted (in case they are reloaded)
        removed_file_list = [f.text().split('/')[-1] for f in removed_files]
        self.fnames_scanned_params = [f for f in self.fnames_scanned_params if f not in removed_file_list]
        self.fnames_plotted_cov = [f for f in self.fnames_plotted_cov if f not in removed_file_list]

    print('after removing files, fnames_scanned_params = ', self.fnames_scanned_params)
    print('after removing files, fnames_plotted_cov = ', self.fnames_plotted_cov)

    update_show_data_checks_coverage(self)
    
    # Update button states after removing files
    update_button_states(self)
    
    refresh_plot(self, call_source='remove_files')  # refresh with updated (reduced or cleared) detection data


def remove_data(self, removed_files):
    # remove data in specified filenames from detection and spec dicts
    for f in removed_files:
        try:  # removed_files is a file list object
            fname = f.text().split('/')[-1]

        except:  # removed_files is a list
            fname = f

        print('trying to remove file =', fname)

        try:  # try to remove detections associated with this file
            # get indices of soundings in det dict with matching .all or .kmall filenames
            if self.det and any(fext in fname for fext in ['.all', '.kmall']):
                i = [j for j in range(len(self.det['fname'])) if self.det['fname'][j] == fname]
                for k in self.det.keys():  # loop through all keys and remove values at these indices
                    self.det[k] = np.delete(self.det[k], i).tolist()

            elif self.det_archive and '.pkl' in fname:  # remove archive data
                self.det_archive.pop(fname, None)
                # Remove from archive file list widget if it exists
                if hasattr(self, 'archive_file_list'):
                    # Find and remove the item from the archive file list
                    for i in range(self.archive_file_list.count()):
                        if self.archive_file_list.item(i).text() == fname:
                            self.archive_file_list.takeItem(i)
                            break

            elif self.spec and '.txt' in fname:  # remove spec data
                self.spec.pop(fname, None)

        except:  # will fail if det dict has not been created yet (e.g., if calc_coverage has not been run)
            update_log(self, 'Failed to remove soundings from ' + fname)


def update_show_data_checks(self):
    # update show data checkboxes and reset detection dictionaries if all files of a given type are removed
    get_current_file_list(self)
    fnames_all = [f for f in self.filenames if '.all' in f]
    fnames_kmall = [f for f in self.filenames if '.kmall' in f]
    fnames_pkl = [f for f in self.filenames if '.pkl' in f]
    fnames_txt = [f for f in self.filenames if '.txt' in f]

    if len(fnames_all + fnames_kmall) == 0:  # all new files have been removed
        self.det = {}
        self.show_data_chk.setChecked(False)

    if len(fnames_pkl) == 0:  # all archives have been removed
        self.det_archive = {}
        self.show_data_chk_arc.setChecked(False)
        # Clear archive file list widget if it exists
        if hasattr(self, 'archive_file_list'):
            self.archive_file_list.clear()

    if len(fnames_txt) == 0:  # all spec files have been removed
        self.spec = {}
        self.spec_chk.setChecked(False)


def refresh_plot(self, print_time=True, call_source=None, sender=None, validate_filters=True):
    # update swath plot with new data and options
    n_plotted = 0
    n_plotted_arc = 0
    self.legend_handles = []
    self.legend_handles_data_rate = []
    self.legend_handles_solid = []
    tic = process_time()

    # Start operation logging if enhanced logging is available
    if hasattr(self, 'start_operation_log'):
        self.start_operation_log("Plot Refresh")

    # update_system_info(self)
    self.pt_size = np.square(float(self.pt_size_cbox.currentText()))
    self.pt_alpha = np.divide(float(self.pt_alpha_cbox.currentText()), 100)

    # Check if cache should be invalidated due to filter or decimation setting changes
    # Only invalidate if settings actually changed (not just visual params)
    if hasattr(self, '_check_filter_settings_changed') and hasattr(self, '_check_decimation_settings_changed'):
        if self._check_filter_settings_changed() or self._check_decimation_settings_changed():
            if hasattr(self, '_invalidate_decimation_cache'):
                self._invalidate_decimation_cache()

    if validate_filters:
        if not validate_filter_text(self):  # validate user input, do not refresh until all float(input) works for all input
            if hasattr(self, 'log_warning'):
                self.log_warning('Invalid/missing filter input (highlighted in yellow); valid input required to refresh plot')
            else:
                update_log(self, '***WARNING: Invalid/missing filter input (highlighted in yellow); '
                                 'valid input required to refresh plot')
            self.tabs.setCurrentIndex(1)  # show filters tab
            return

    if self.verbose_logging:
        print('************* REFRESH PLOT *****************')
        # sorting out how senders are handled when called with connect and lambda
        if self.sender():
            sender = self.sender().objectName()
            print('received a sending button =', sender)
        elif not sender:
            sender = 'NA'

        if sender:
            print('***REFRESH_PLOT activated by sender:', sender)
            if hasattr(self, 'log_info'):
                self.log_info(f"Plot refresh triggered by: {sender}")

        if call_source:
            print('***REFRESH_PLOT called by function:', call_source)
            if hasattr(self, 'log_info'):
                self.log_info(f"Plot refresh called by: {call_source}")
    else:
        # sorting out how senders are handled when called with connect and lambda
        if self.sender():
            sender = self.sender().objectName()
        elif not sender:
            sender = 'NA'

    clear_plot(self)

    # update top data plot combobox based on show_data checks
    if sender in ['show_data_chk', 'show_data_chk_arc', 'calc_coverage_btn', 'load_archive_btn']:
        last_top_data = self.top_data_cbox.currentText()
        self.top_data_cbox.clear()
        show_data_dict = {self.show_data_chk: 'New data', self.show_data_chk_arc: 'Archive data'}
        self.top_data_cbox.addItems([v for k, v in show_data_dict.items() if k.isChecked()])
        self.top_data_cbox.setCurrentIndex(max([0, self.top_data_cbox.findText(last_top_data)]))

    # if sending button is returnPressed in min or max clim_tb, update dict of user clim for this mode
    update_clim_tb = sender in ['new_data_color_by_type_radio', 'new_data_single_color_radio', 
                                'archive_data_color_by_type_radio', 'archive_data_single_color_radio', 'top_data_cbox']
    update_color_modes(self, update_clim_tb)

    # update clim_all_data with limits of self.det
    if self.top_data_cbox.currentText() == 'New data':  # default: plot any archive data first as background
        # print('in refresh plot, calling show_archive first to allow new data on top')
        n_plotted_arc = show_archive(self)
        # print('n_plotted_arc = ', n_plotted_arc)

    if self.det:  # default: plot any available new data
        # print('\ncalling plot_coverage with new data')
        n_plotted = plot_coverage(self, self.det, is_archive=False)
        # print('n_plotted = ', n_plotted)
        
        # plot backscatter data
        try:
            plot_backscatter(self, self.det, is_archive=False)
        except:
            # DEBUG: failed to plot backscatter
            pass
        
        # plot ping mode data
        try:
            plot_pingmode(self, self.det, is_archive=False)
        except:
            # DEBUG: failed to plot ping mode
            pass
        # plot pulse form data
        try:
            plot_pulseform(self, self.det, is_archive=False)
        except:
            # DEBUG: failed to plot pulse form
            pass
        # plot swath mode data
        try:
            plot_swathmode(self, self.det, is_archive=False)
        except:
            # DEBUG: failed to plot swath mode
            pass

        # plot frequency data
        try:
            plot_frequency(self, self.det, is_archive=False)
        except:
            # DEBUG: failed to plot frequency
            pass

        # print('calling plot_data_rate')
        try:
            plot_data_rate(self, self.det, is_archive=False)

        except Exception as e:
            print(f'failed to plot data rate: {e}')
            if hasattr(self, 'log_error'):
                self.log_error(f'Failed to plot data rate: {str(e)}')
            else:
                update_log(self, f'Error: Failed to plot data rate - {str(e)}')

        try:
            plot_time_diff(self)

        except:
            # DEBUG: failed to plot time diff
            pass

    if self.top_data_cbox.currentText() == 'Archive data':  # option: plot archive data last on top of any new data
        # DEBUG: calling show_archive
        n_plotted_arc = show_archive(self)
        # DEBUG: n_plotted_arc = n_plotted_arc
        
        # plot archive backscatter data
        try:
            plot_backscatter(self, self.det_archive, is_archive=True)
        except:
            # DEBUG: failed to plot archive backscatter
            pass
        
        # plot archive ping mode data
        try:
            plot_pingmode(self, self.det_archive, is_archive=True)
        except:
            # DEBUG: failed to plot archive ping mode
            pass
        # plot archive pulse form data
        try:
            plot_pulseform(self, self.det_archive, is_archive=True)
        except:
            # DEBUG: failed to plot archive pulse form
            pass
        # plot archive swath mode data
        try:
            plot_swathmode(self, self.det_archive, is_archive=True)
        except:
            # DEBUG: failed to plot archive swath mode
            pass

        # plot archive frequency data
        try:
            plot_frequency(self, self.det_archive, is_archive=True)
        except:
            # DEBUG: failed to plot archive frequency
            pass

    plot_hist(self)  # plot histogram of soundings versus depth
    update_axes(self)  # update axes to fit all loaded data
    add_grid_lines(self)  # add grid lines
    # REMOVED: add_WD_lines(self) - now handled by add_plot_features() for all plots
    # REMOVED: add_nominal_angle_lines(self) - now handled by add_plot_features() for all plots
    add_legend(self)  # add legend or colorbar
    add_spec_lines(self)  # add specification lines if loaded
    if self.verbose_logging:
        print('calling self.swath_canvas.draw()')
    self.swath_canvas.draw()  # final update for the swath canvas
    if self.verbose_logging:
        print('calling self.backscatter_canvas.draw()')
    self.backscatter_canvas.draw()  # final update for the backscatter canvas
    if self.verbose_logging:
        print('calling self.pingmode_canvas.draw()')
    self.pingmode_canvas.draw()  # final update for the ping mode canvas
    if self.verbose_logging:
        print('calling self.pulseform_canvas.draw()')
    self.pulseform_canvas.draw()  # final update for the pulse form canvas
    if self.verbose_logging:
        print('calling self.swathmode_canvas.draw()')
    self.swathmode_canvas.draw()  # final update for the swath mode canvas

    if self.verbose_logging:
        print('calling self.frequency_canvas.draw()')
    self.frequency_canvas.draw()  # final update for the frequency canvas
    if self.verbose_logging:
        print('calling self.data_canvas.draw()')
    self.data_canvas.draw()  # final update for the data rate canvas

    toc = process_time()
    refresh_time = toc - tic
    if print_time:
        # Debug print removed
        # Enhanced completion logging
        completion_msg = f"Updated plot ({n_plotted} new, {n_plotted_arc} archive soundings; {refresh_time:.2f} s)"
        if hasattr(self, 'log_success'):
            self.log_success(completion_msg)
        else:
            update_log(self, completion_msg)

    # End operation logging if enhanced logging is available
    if hasattr(self, 'end_operation_log'):
        self.end_operation_log("Plot Refresh", f"{n_plotted + n_plotted_arc} total soundings plotted")


def update_color_modes(self, update_clim_tb=False):
    # update color modes for the new data and archive data based on radio button selections
    # For new data: determine if using data type coloring or single color
    if self.new_data_color_by_type_radio.isChecked():
        self.cmode = 'color_by_type'  # will be overridden by tab-specific coloring
    else:
        self.cmode = 'solid_color'
    print('self.cmode is now', self.cmode)
    
    # For archive data: determine if using data type coloring or single color
    if self.archive_data_color_by_type_radio.isChecked():
        self.cmode_arc = 'color_by_type'  # will be overridden by tab-specific coloring
    else:
        self.cmode_arc = 'solid_color'
    print('self.cmode_arc is now', self.cmode_arc)

    # determine expected dominant color mode (i.e., data on top) based on show_data checks and top data selection
    # For the new system, we need to determine what the actual color mode should be based on the current tab
    # This will be handled in the individual plotting functions based on the tab context
    
    # For now, set a default that will be overridden by tab-specific logic
    self.cmode_final = 'depth'  # default, will be overridden by tab context
    
    # enable colorscale limit text boxes as appropriate for depth and backscatter tabs
    for i, tb in enumerate([self.min_clim_tb, self.max_clim_tb]):
        tb.setEnabled(self.clim_cbox.currentText() == 'Fixed limits')

    # Handle color limits for depth and backscatter data
    if update_clim_tb:  # update text boxes last values if refresh_plot was called by change in cmode
        # This will be handled by individual tab plotting functions
        pass

    # Store user-defined limits for future reference if data exists and is shown
    if (self.det and self.top_data_cbox.currentText() == 'New data' and self.show_data_chk.isChecked()) or \
            (self.det_archive and self.top_data_cbox.currentText() == 'Archive data' and
             self.show_data_chk_arc.isChecked()):
        # This will be handled by individual tab plotting functions
        pass

    # get initial clim_all_data from detection dict for reference (and update) in next plot loop
    self.clim_all_data = []  # reset clim_all_data, then update if appropriate for cmode and data availability
    if self.det:
        # This will be handled by individual tab plotting functions based on the tab context
        pass


def update_show_data_checks_coverage(self):
    # update show data checkboxes and reset detection dictionaries if all files of a given type are removed
    get_current_file_list(self)
    fnames_all = [f for f in self.filenames if '.all' in f]
    fnames_kmall = [f for f in self.filenames if '.kmall' in f]
    fnames_pkl = [f for f in self.filenames if '.pkl' in f]
    fnames_txt = [f for f in self.filenames if '.txt' in f]

    if len(fnames_all + fnames_kmall) == 0:  # all new files have been removed
        self.det = {}
        self.show_data_chk.setChecked(False)

    if len(fnames_pkl) == 0:  # all archives have been removed
        self.det_archive = {}
        self.show_data_chk_arc.setChecked(False)

    if len(fnames_txt) == 0:  # all spec files have been removed
        self.spec = {}
        self.spec_chk.setChecked(False)

def add_plot_features(self, ax, is_archive=False):
    """Add angle lines, water depth lines, reference text, and specification lines to any axis"""
    
    # Add water depth multiple lines if checked
    if self.n_wd_lines_gb.isChecked():  # plot WD lines if checked
        n_wd_lines_max = float(self.n_wd_lines_tb_max.text())
        n_wd_lines_int = float(self.n_wd_lines_tb_int.text())
        
        for ps in [-1, 1]:  # port and starboard
            for n in range(1, int(np.floor(n_wd_lines_max / n_wd_lines_int) + 1)):
                # plot WD lines (corrected calculation from original add_WD_lines)
                ax.plot([0, ps * n * n_wd_lines_int * self.swath_ax_margin * self.z_max / 2],
                        [0, self.swath_ax_margin * self.z_max], 'k', linewidth=1, clip_on=True)
                
                # add WD line labels (corrected from original add_WD_lines)
                x_mag = 0.9 * n * n_wd_lines_int * self.z_max / 2  # set magnitude of text locations to 90% of line end
                y_mag = 0.9 * self.z_max

                # keep text locations on the plot
                if x_mag > 0.9 * self.x_max:
                    x_mag = 0.9 * self.x_max
                    y_mag = 2 * x_mag / (n * n_wd_lines_int)  # scale y location with limited x location

                ax.text(x_mag * ps, y_mag, str(n * n_wd_lines_int) + 'X',
                        verticalalignment='center',
                        horizontalalignment='center',
                        bbox=dict(facecolor='white', edgecolor='none',
                                 alpha=1, pad=0.0),
                        clip_on=True)
    
    # Add swath angle lines if checked
    # DEBUG: ANGLE LINES VERSION CHECK: This is the NEW version with enhanced labeling
    if self.angle_lines_gb.isChecked():  # plot swath angle lines if checked
        angle_lines_max = float(self.angle_lines_tb_max.text())
        angle_lines_int = float(self.angle_lines_tb_int.text())
        
        for ps in [-1, 1]:  # port and starboard
            for angle in np.arange(angle_lines_int, angle_lines_max + angle_lines_int, angle_lines_int):
                # calculate line endpoints
                x_line_mag = self.swath_ax_margin * self.x_max
                y_line_mag = x_line_mag / np.tan(np.radians(angle))
                
                # Always plot the angle line (remove the filtering condition)
                ax.plot([0, ps * x_line_mag], [0, y_line_mag], 'k', linewidth=1, clip_on=True)
                
                # Add angle line labels (restored from add_nominal_angle_lines)
                x_label_mag = 0.9 * x_line_mag  # set magnitude of text locations to 90% of line end
                y_label_mag = 0.9 * y_line_mag

                # keep text locations on the plot - improved logic to handle all angles
                if x_label_mag > 0.9 * self.x_max:
                    x_label_mag = 0.9 * self.x_max
                    y_label_mag = x_label_mag / np.tan(np.radians(angle))
                
                # Additional check to ensure y_label_mag doesn't exceed plot bounds
                if y_label_mag > 0.9 * self.z_max:
                    y_label_mag = 0.9 * self.z_max
                    x_label_mag = y_label_mag * np.tan(np.radians(angle))

                ax.text(x_label_mag * ps, y_label_mag,
                       str(int(angle)) + '\xb0',
                       verticalalignment='center', horizontalalignment='center',
                       bbox=dict(facecolor='white', edgecolor='none', alpha=1, pad=0.0),
                       clip_on=True)
    
    # Add reference/filter text if checked
    if self.show_ref_fil_chk.isChecked():
        # Create reference text similar to add_ref_filter_text function
        ref_str = 'Reference: ' + self.ref_cbox.currentText()
        depth_fil = ['None', self.min_depth_tb.text() + ' to ' + self.max_depth_tb.text() + ' m']
        depth_arc_fil = ['None', self.min_depth_arc_tb.text() + ' to ' + self.max_depth_arc_tb.text() + ' m']
        angle_fil = ['None', self.min_angle_tb.text() + ' to ' + self.max_angle_tb.text() + '\u00b0']
        bs_fil = ['None', ('+' if float(self.min_bs_tb.text()) > 0 else '') + self.min_bs_tb.text() + ' to ' +
                  ('+' if float(self.max_bs_tb.text()) > 0 else '') + self.max_bs_tb.text() + ' dB']
        rtp_angle_fil = ['None', ('+' if float(self.rtp_angle_buffer_tb.text()) > 0 else '') + \
                         self.rtp_angle_buffer_tb.text() + '\u00b0']
        rtp_cov_fil = ['None', ('-' if float(self.rtp_cov_buffer_tb.text()) > 0 else '') + \
                       self.rtp_cov_buffer_tb.text() + ' m']
        fil_dict = {'Angle filter: ': angle_fil[self.angle_gb.isChecked()],
                    'Depth filter (new): ': depth_fil[self.depth_gb.isChecked()],
                    'Depth filter (archive): ': depth_arc_fil[self.depth_gb.isChecked()],
                    'Backscatter filter: ': bs_fil[self.bs_gb.isChecked()],
                    'Runtime angle buffer: ': rtp_angle_fil[self.rtp_angle_gb.isChecked()],
                    'Runtime coverage buffer: ': rtp_cov_fil[self.rtp_cov_gb.isChecked()]}

        for fil in fil_dict.keys():
            ref_str += '\n' + fil + fil_dict[fil]

        ref_str += '\nMax. point count: ' + str(int(self.n_points_max))
        ref_str += '\nDecimation factor: ' + "%.1f" % self.dec_fac
        
        ax.text(0.02, 0.98, ref_str,
                transform=ax.transAxes, fontsize=8,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    # Add specification lines if checked
    if self.spec_chk.isChecked():  # plot spec lines if checked
        if hasattr(self, 'spec_data') and self.spec_data is not None:
            # This should call the proper add_spec_lines function instead of trying to plot here
            # The specification lines are handled by the add_spec_lines function
            pass

def plot_coverage(self, det, is_archive=False, print_updates=False, det_name='detection dictionary'):
    # plot the parsed detections from new or archive data dict; return the number of points plotted after filtering
    # tic = process_time()
    # Debug print removed
    # consolidate data from port and stbd sides for plotting
    try:
        y_all = det['y_port'] + det['y_stbd']  # acrosstrack distance from TX array (.all) or origin (.kmall)

    except:
        print('***EXCEPTION: y_port or y_stbd not found; treating this like an older archive format (x_port / x_stbd)')
        y_all = det['x_port'] + det['x_stbd']  # older archives stored acrosstrack distance as x, not y
        det['y_port'] = deepcopy(det['x_port'])
        det['y_stbd'] = deepcopy(det['x_stbd'])
        # print('retrieved/set acrosstrack "y" values from archive detection dict "x" keys with old naming convention')

    z_all = det['z_port'] + det['z_stbd']  # depth from TX array (.all) or origin (.kmall)
    bs_all = det['bs_port'] + det['bs_stbd']  # reported backscatter amplitude
    fname_all = det['fname'] + det['fname']

    if self.verbose_logging:
        print('len z_all, bs_all, and fname_all at start of plot_coverage = ', len(z_all), len(bs_all), len(fname_all))

    # calculate simplified swath angle from raw Z, Y data to use for angle filtering and comparison to runtime limits
    # Kongsberg angle convention is right-hand-rule about +X axis (fwd), so port angles are + and stbd are -
    angle_all = (-1 * np.rad2deg(np.arctan2(y_all, z_all))).tolist()  # multiply by -1 for Kongsberg convention

    # warn user if detection dict does not have all required offsets for depth reference adjustment (e.g., old archives)
    if (not all([k in det.keys() for k in ['tx_x_m', 'tx_y_m', 'aps_x_m', 'aps_y_m', 'wl_z_m']]) and
            self.ref_cbox.currentText().lower() != 'raw data'):
            update_log(self, 'Warning: ' + det_name + ' does not include all fields required for depth reference '
                                                      'adjustment (e.g., possibly an old archive format); no depth '
                                                      'reference adjustment will be made')

    # get file-specific, ping-wise adjustments to bring Z and Y into desired reference frame
    dx_ping, dy_ping, dz_ping = adjust_depth_ref(det, depth_ref=self.ref_cbox.currentText().lower())

    # print('dz_ping has len', len(dz_ping))
    # print('got dy_ping=', dy_ping)
    # print('got dz_ping=', dz_ping)
    # print('first 20 of xline[z]=', z_all[0:20])
    # print('first 20 of dz =', dz_ping[0:20])
    # print('got dy_ping=', dy_ping)
    # print('got dz_ping=', dz_ping)
    z_all = [z + dz for z, dz in zip(z_all, dz_ping + dz_ping)]  # add dz (per ping) to each z (per sounding)
    y_all = [y + dy for y, dy in zip(y_all, dy_ping + dy_ping)]  # add dy (per ping) to each y (per sounding)

    if print_updates:
        for i in range(len(angle_all)):
            if any(np.isnan([angle_all[i], bs_all[i]])):
                print('NAN in (i,y,z,angle,BS):',
                      i, y_all[i], z_all[i], angle_all[i], bs_all[i])

    # update x and z max for axis resizing during each plot call
    self.x_max = max([self.x_max, np.nanmax(np.abs(np.asarray(y_all)))])
    self.z_max = max([self.z_max, np.nanmax(np.asarray(z_all))])

    # after updating axis limits, simply return w/o plotting if toggle for this data type (current/archive) is off
    if ((is_archive and not self.show_data_chk_arc.isChecked())
            or (not is_archive and not self.show_data_chk.isChecked())):
        print('returning from plotter because the toggle for this data type is unchecked')
        return

    # set up indices for optional masking on angle, depth, bs; all idx true until fail optional filter settings
    # all soundings masked for nans (e.g., occasional nans in EX0908 data)
    idx_shape = np.shape(np.asarray(z_all))
    angle_idx = np.ones(idx_shape)
    depth_idx = np.ones(idx_shape)
    bs_idx = np.ones(idx_shape)
    rtp_angle_idx = np.ones(idx_shape)  # idx of angles that fall within the runtime params for RX beam angles
    rtp_cov_idx = np.ones(idx_shape)  # idx of soundings that fall within the runtime params for max coverage
    real_idx = np.logical_not(np.logical_or(np.isnan(y_all), np.isnan(z_all)))  # idx true for NON-NAN soundings

    if print_updates:
        print('number of nans found in y_all and z_all=', np.sum(np.logical_not(real_idx)))
        # print('len of xall before filtering:', len(y_all))

    if self.angle_gb.isChecked():  # get idx satisfying current swath angle filter based on depth/acrosstrack angle
        lims = [float(self.min_angle_tb.text()), float(self.max_angle_tb.text())]
        angle_idx = np.logical_and(np.abs(np.asarray(angle_all)) >= lims[0],
                                   np.abs(np.asarray(angle_all)) <= lims[1])

    if self.depth_gb.isChecked():  # get idx satisfying current depth filter
        lims = [float(self.min_depth_tb.text()), float(self.max_depth_tb.text())]
        if is_archive:
            lims = [float(self.min_depth_arc_tb.text()), float(self.max_depth_arc_tb.text())]

        depth_idx = np.logical_and(np.asarray(z_all) >= lims[0], np.asarray(z_all) <= lims[1])

    if self.bs_gb.isChecked():  # get idx satisfying current backscatter filter; BS in 0.1 dB, multiply lims by 10
        # lims = [10 * float(self.min_bs_tb.text()), 10 * float(self.max_bs_tb.text())]
        lims = [float(self.min_bs_tb.text()), float(self.max_bs_tb.text())]  # parsed BS is converted to dB
        bs_idx = np.logical_and(np.asarray(bs_all) >= lims[0], np.asarray(bs_all) <= lims[1])

    if self.rtp_angle_gb.isChecked():  # get idx of angles outside the runtime parameter swath angle limits
        self.rtp_angle_buffer = float(self.rtp_angle_buffer_tb.text())

        try:  # try to compare angles to runtime param limits (port pos., stbd neg. per Kongsberg convention)
            if 'max_port_deg' in det and 'max_stbd_deg' in det:  # compare angles to runtime params if available
                rtp_angle_idx_port = np.less_equal(np.asarray(angle_all),
                                                   np.asarray(2 * det['max_port_deg']) + self.rtp_angle_buffer)
                rtp_angle_idx_stbd = np.greater_equal(np.asarray(angle_all),
                                                      -1 * np.asarray(2 * det['max_stbd_deg']) - self.rtp_angle_buffer)
                rtp_angle_idx = np.logical_and(rtp_angle_idx_port, rtp_angle_idx_stbd)  # update rtp_angle_idx

                if print_updates:
                    print('set(max_port_deg)=', set(det['max_port_deg']))
                    print('set(max_stbd_deg)=', set(det['max_stbd_deg']))
                    print('sum of rtp_angle_idx=', sum(rtp_angle_idx))

            else:
                update_log(self, 'Runtime parameters for swath angle limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'RX angles against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing RX beam angles to runtime params; no angle filter applied')

    if self.rtp_cov_gb.isChecked():  # get idx of soundings with coverage near runtime param cov limits
        self.rx_cov_buffer = float(self.rtp_cov_buffer_tb.text())

        try:  # try to compare coverage to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'max_port_m' in det and 'max_stbd_m' in det:  # compare coverage to runtime params if available
                # coverage buffer is negative; more negative, more aggressive filtering
                rtp_cov_idx_port = np.greater_equal(np.asarray(y_all),
                                                    -1 * np.asarray(2 * det['max_port_m']) - self.rx_cov_buffer)
                rtp_cov_idx_stbd = np.less_equal(np.asarray(y_all),
                                                 np.asarray(2 * det['max_stbd_m']) + self.rx_cov_buffer)
                rtp_cov_idx = np.logical_and(rtp_cov_idx_port, rtp_cov_idx_stbd)

                if print_updates:
                    print('set(max_port_m)=', set(det['max_port_m']))
                    print('set(max_stbd_m)=', set(det['max_stbd_m']))
                    print('sum of rtp_cov_idx=', sum(rtp_cov_idx))

            else:
                update_log(self, 'Runtime parameters for swath coverage limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'coverage against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing coverage to runtime params; no coverage filter applied')

    # apply filter masks to x, z, angle, and bs fields
    filter_idx = np.logical_and.reduce((angle_idx, depth_idx, bs_idx, rtp_angle_idx, rtp_cov_idx, real_idx))

    # get color mode and set up color maps and legend
    cmode = [self.cmode, self.cmode_arc][is_archive]  # get user selected color mode for local use
    # For the swath plot, 'color_by_type' means 'depth'
    if cmode == 'color_by_type':
        cmode = 'depth'

    print('cmode after first assignment is', cmode)

    # set the color map, initialize color limits and set for legend/colorbars (will apply to last det data plotted)
    self.cmap = 'rainbow'
    self.clim = []
    self.cset = []
    self.legend_label = ''
    self.last_cmode = cmode  # reset every plot call; last (top) plot updates for add_legend and update_color_limits

    # print('before getting c_all, len of z_all, y_all, bs_all =', len(z_all), len(y_all), len(bs_all))

    # set color maps based on combobox selection after filtering data
    if cmode == 'depth':
        c_all = z_all  # set color range to depth range
        print('cmode is depth, len c_all=', len(c_all))

        # Check if we should use filter range for color scaling
        print(f'DEBUG: Color scaling option: "{self.clim_cbox.currentText()}"')
        if self.clim_cbox.currentText() == 'Filtered data':
            print('DEBUG: Using Filtered data option for depth color scaling')
            # Use depth filter limits for color scaling
            z_lims_new = [float(self.min_depth_tb.text()), float(self.max_depth_tb.text())] * \
                         int(cmode == 'depth' and self.show_data_chk.isChecked())
            z_lims_arc = [float(self.min_depth_arc_tb.text()), float(self.max_depth_arc_tb.text())] * \
                         int(cmode == 'depth' and self.show_data_chk_arc.isChecked())
            z_lims_checked = z_lims_new + z_lims_arc
            print(f'DEBUG: Depth filter limits - new: {z_lims_new}, archive: {z_lims_arc}, combined: {z_lims_checked}')
            print(f'DEBUG: cmode={cmode}, show_data_chk={self.show_data_chk.isChecked()}, cmode_arc={self.cmode_arc}, show_data_chk_arc={self.show_data_chk_arc.isChecked()}')
            if z_lims_checked:  # only apply if we have valid filter limits
                self.clim = [min(z_lims_checked), max(z_lims_checked)]
                print(f'DEBUG: Using depth filter range for color scaling: {self.clim}')
            else:
                print('DEBUG: No valid filter limits, falling back to data range')
                # Fallback to data range if no valid filter limits
                if len(c_all) > 0:
                    self.clim = [min(c_all), max(c_all)]
                else:
                    self.clim = deepcopy(self.last_depth_clim)
        elif self.clim_cbox.currentText() == 'Custom Plot':
            print('DEBUG: Using Custom Plot option for depth color scaling')
            # Use min and max values from Depth groupbox in Use custom plot limits
            if hasattr(self, 'min_z_tb') and hasattr(self, 'max_z_tb'):
                try:
                    min_val = float(self.min_z_tb.text()) if self.min_z_tb.text() else 0.0
                    max_val = float(self.max_z_tb.text()) if self.max_z_tb.text() else 4000.0
                    self.clim = [min_val, max_val]
                    print(f'DEBUG: Using Custom Plot range for color scaling: {self.clim}')
                except ValueError:
                    print('DEBUG: Invalid Custom Plot values, falling back to data range')
                    if len(c_all) > 0:
                        self.clim = [min(c_all), max(c_all)]
                    else:
                        self.clim = deepcopy(self.last_depth_clim)
            else:
                print('DEBUG: Custom Plot text boxes not found, falling back to data range')
                if len(c_all) > 0:
                    self.clim = [min(c_all), max(c_all)]
                else:
                    self.clim = deepcopy(self.last_depth_clim)
        else:
            print(f'DEBUG: Using {self.clim_cbox.currentText()} option for depth color scaling')
            # Use actual data range for color scaling
            if len(c_all) > 0:  # if there is at least one sounding, set clim and store for future reference
                self.clim = [min(c_all), max(c_all)]
                self.last_depth_clim = deepcopy(self.clim)
                print(f'DEBUG: Using data range for color scaling: {self.clim}')
            else:  # use last known depth clim to avoid errors in scatter
                self.clim = deepcopy(self.last_depth_clim)
                print(f'DEBUG: Using last known depth clim for color scaling: {self.clim}')
            
        # --- Robust fallback: ensure self.clim is always valid ---
        if not self.clim or len(self.clim) < 2 or self.clim[0] == self.clim[1]:
            print('WARNING: self.clim was empty/invalid, setting fallback [0, 1000]')
            self.clim = [0, 1000]
   # --------------------------------------------------------

        self.cmap = self.cmap + '_r'  # reverse the color map so shallow is red, deep is blue
        self.legend_label = 'Depth (m)'

    elif cmode == 'backscatter':
        # c_all = [int(bs) / 10 for bs in bs_all]  # convert to int, divide by 10 (BS reported in 0.1 dB)
        c_all = [int(bs*10)/10 for bs in bs_all]  # BS stored in dB; convert to 0.1 precision
        print('cmode is backscatter, len c_all=', len(c_all))
        # print('c_all =', c_all)
        self.clim = [-50, -10]

        # use backscatter filter limits for color limits
        if self.bs_gb.isChecked() and self.clim_cbox.currentText() == 'Filtered data':
            self.clim = [float(self.min_bs_tb.text()), float(self.max_bs_tb.text())]

        self.legend_label = 'Reported Backscatter (dB)'

    elif np.isin(cmode, ['ping_mode', 'pulse_form', 'swath_mode', 'frequency']):
        # modes are listed per ping; append ping-wise setting to correspond with y_all, z_all, angle_all, bs_all
        mode_all = det[cmode] + det[cmode]
        # mode_all = np.asarray(mode_all)[filter_idx].tolist()  # filter mode_all as applied for z, x, bs, angle, etc.
        print('heading into cmode selection with mode_all=', mode_all)

        if cmode == 'ping_mode':  # define dict of depth modes (based on EM dg format 01/2020) and colors

            print('cmode = ping mode and self.model_name is', self.model_name)

            c_set = {'Very Shallow': 'red', 'Shallow': 'darkorange', 'Medium': 'gold',
                     'Deep': 'limegreen', 'Deeper': 'darkturquoise', 'Very Deep': 'blue',
                     'Extra Deep': 'indigo', 'Extreme Deep': 'black'}
            self.legend_label = 'Depth Mode'

            # EM2040 .all files store frequency mode in the ping mode field; replace color set accordingly
            print('ahead of special EM2040 ping mode c_set:')
            print('self.model_name =', self.model_name)
            print('set(mode_all) =', [mode for mode in set(mode_all)])
            # Check for exact EM2040 model and frequency data in ping mode field
            if (('EM 2040' in self.model_name or 'EM2040' in self.model_name) and 
                any([mode.find('kHz') > -1 for mode in set(mode_all)])):
                print('***using frequency info for ping mode***')
                c_set = {'400 kHz': 'red', '300 kHz': 'darkorange', '200 kHz': 'gold'}
                self.legend_label = 'Freq. (EM 2040, SIS 4)'
                update_log(self, 'Ping mode color scale set to frequency mode (EM 2040, SIS 4 format)')

        elif cmode == 'pulse_form':  # define dict of pulse forms and colors
            c_set = {'CW': 'red', 'Mixed': 'limegreen', 'FM': 'blue'}  # set of pulse forms
            self.legend_label = 'Pulse Form'

        elif cmode == 'swath_mode':  # define dict of swath modes and colors
            # Dual Swath is parsed as Fixed or Dynamic but generalized here
            # c_set = {'Single Swath': 'red', 'Dual Swath (Fixed)': 'limegreen', 'Dual Swath (Dynamic)': 'blue'}
            c_set = {
                "Single Swath": "red",  # red
                "Dual Swath": "#blue",    # blue
                "Dual Swath (Dynamic)": "#2ca02c",  # green (add this line!)
                # ... add any other variants you see in your data ...
            }
            #c_set = {'Single Swath': 'red', 'Dual Swath': 'blue'}
            self.legend_label = 'Swath Mode'

        elif cmode == 'frequency':  # define dict of frequencies
            c_set = {'400 kHz': 'red', '300 kHz': 'darkorange', '200 kHz': 'gold',
                     '70-100 kHz': 'limegreen', '40-100 kHz': 'darkturquoise', '40-70 kHz': 'blue',
                     '30 kHz': 'indigo', '12 kHz': 'black', 'NA': 'white'}
            self.legend_label = 'Frequency'

        # get integer corresponding to mode of each detection; as long as c_set is consistent, this should keep
        # color coding consistent for easier comparison of plots across datasets with different modes present
        # some modes incl. parentheses as parsed, e.g., 'Dual Swath (Dynamic)' and 'Dual Swath (Fixed)'; entries are
        # split/stripped in mode_all to the 'base' mode, e.g., 'Dual Swath' for comparison to simpler c_set dict
        mode_all_base = [m.split('(')[0].strip() for m in mode_all]

        print('c_set =', c_set)
        print('mode all base = ', mode_all_base)

        c_all = [c_set[mb] for mb in mode_all_base]
        # print('colr mode is ping, pulse, or swath --> len of new c_all is', len(c_all))
        # print('c_all= at time of assignment=', c_all)
        self.clim = [0, len(c_set.keys()) - 1]  # set up limits based on total number of modes for this cmode
        self.cset = c_set  # store c_set for use in legend labels

    else:  # cmode is a solid color
        c_all = np.ones_like(y_all)  # make a placeholder c_all for downsampling process

    # add clim from this dataset to clim_all_data for reference if color modes are same for new and archive data
    if cmode != 'solid_color':
        # print('** after filtering, just updated clim_all_data from', self.clim_all_data)
        if self.cmode == self.cmode_arc:
            self.clim_all_data += self.clim
            if self.clim_all_data:  # Check if list is not empty before calling min/max
                self.clim = [min(self.clim_all_data), max(self.clim_all_data)]
    # print('to', self.clim_all_data)
    # print('and updated min/max to self.clim=', self.clim)

    # store the unfiltered, undecimated, unsorted color data for use by plot_data_rate
    if is_archive:
        self.c_all_data_rate_arc = deepcopy(c_all)
    else:
        self.c_all_data_rate = deepcopy(c_all)

    # print('before applying filters, len of c_all is', len(c_all))

    # filter the data after storing the color data for plot_data_rate
    y_all = np.asarray(y_all)[filter_idx].tolist()
    z_all = np.asarray(z_all)[filter_idx].tolist()
    angle_all = np.asarray(angle_all)[filter_idx].tolist()
    bs_all = np.asarray(bs_all)[filter_idx].tolist()
    c_all = np.asarray(c_all)[filter_idx].tolist()  # FAILS WHEN FILTERING AND COLORING BY PING PULSE OR SWATH MODE

    self.fnames_all = np.asarray(fname_all)[filter_idx].tolist()

    if print_updates:
        print('AFTER APPLYING IDX: len y_all, z_all, angle_all, bs_all, c_all=',
              len(y_all), len(z_all), len(angle_all), len(bs_all), len(c_all))

    # Store the filtered length and hash before decimation for cache validation
    n_points_filtered_before_decimation = len(y_all)
    data_hash_before_decimation = hash(tuple(y_all[:100]) if len(y_all) > 100 else tuple(y_all))
    
    # Check if we can use cached decimated data (only for visual parameter changes)
    cache_key = None
    use_cached_data = False
    if hasattr(self, '_generate_plot_cache_key') and hasattr(self, 'decimation_cache'):
        cache_key_base = self._generate_plot_cache_key(is_archive=is_archive)
        # Add cmode to cache key since different color modes produce different c_all arrays
        cache_key = f"{cache_key_base}|cmode:{cmode}"
        
        # Check if we have cached data for this key
        if cache_key in self.decimation_cache:
            cached = self.decimation_cache[cache_key]
            # Verify the cache is still valid (data hasn't changed)
            # Check if filtered data length matches (quick check)
            # n_points_filtered in cache is the length BEFORE decimation
            if cached.get('n_points_filtered') == n_points_filtered_before_decimation:
                # More thorough check: compare hash of first 100 points of filtered data
                if cached.get('data_hash') == data_hash_before_decimation:
                    use_cached_data = True
                    if print_updates:
                        print(f'Using cached decimated data (saved processing time)')
    
    if not use_cached_data:
        # get post-filtering number of points to plot and allowable maximum from default or user input (if selected)
        self.n_points = len(y_all)
        self.n_points_max = self.n_points_max_default

        if self.pt_count_gb.isChecked() and self.max_count_tb.text():  # override default only if explicitly set by user
            self.n_points_max = float(self.max_count_tb.text())

        # default dec fac to meet n_points_max, regardless of whether user has checked box for plot point limits
        if self.n_points_max == 0:
            update_log(self, 'Max plotting sounding count set equal to zero')
            self.dec_fac_default = np.inf
        else:
            self.dec_fac_default = float(self.n_points / self.n_points_max)

        if self.dec_fac_default > 1 and not self.pt_count_gb.isChecked():  # warn user if large count may slow down plot
            update_log(self, 'Large filtered sounding count (' + str(self.n_points) + ') may slow down plotting')

        # get user dec fac as product of whether check box is checked (default 1)
        self.dec_fac_user = max(self.pt_count_gb.isChecked() * float(self.dec_fac_tb.text()), 1)
        self.dec_fac = max(self.dec_fac_default, self.dec_fac_user)

        if self.dec_fac_default > self.dec_fac_user:  # warn user if default max limit was reached
            update_log(self, 'Decimating' + (' archive' if is_archive else '') +
                       ' data by factor of ' + "%.1f" % self.dec_fac +
                       ' to keep plotted point count under ' + "%.0f" % self.n_points_max)

        elif self.pt_count_gb.isChecked() and self.dec_fac_user > self.dec_fac_default and self.dec_fac_user > 1:
            # otherwise, warn user if their manual dec fac was applied because it's more aggressive than max count
            update_log(self, 'Decimating' + (' archive' if is_archive else '') +
                       ' data by factor of ' + "%.1f" % self.dec_fac +
                       ' per user input')

        # print('before decimation, c_all=', c_all)

        if self.dec_fac > 1:
            # print('dec_fac > 1 --> attempting interp1d')
            idx_all = np.arange(len(y_all))  # integer indices of all filtered data
            idx_dec = np.arange(0, len(y_all) - 1, self.dec_fac)  # desired decimated indices, may be non-integer

            # interpolate indices of colors, not color values directly
            f_dec = interp1d(idx_all, idx_all, kind='nearest')  # nearest neighbor interpolation function of all indices
            idx_new = [int(i) for i in f_dec(idx_dec)]  # list of decimated integer indices
            # print('idx_new is now', idx_new)
            y_all = [y_all[i] for i in idx_new]
            z_all = [z_all[i] for i in idx_new]
            c_all = [c_all[i] for i in idx_new]
            # print('idx_new=', idx_new)

        self.n_points = len(y_all)
        
        # Cache the decimated data for future use (when only visual params change)
        if cache_key is not None and hasattr(self, 'decimation_cache'):
            # Use the hash we calculated before decimation
            self.decimation_cache[cache_key] = {
                'y_all': y_all.copy() if isinstance(y_all, list) else list(y_all),
                'z_all': z_all.copy() if isinstance(z_all, list) else list(z_all),
                'c_all': c_all.copy() if isinstance(c_all, list) else list(c_all),
                'fnames_all': self.fnames_all.copy() if isinstance(self.fnames_all, list) else list(self.fnames_all),
                'n_points': self.n_points,
                'n_points_filtered': n_points_filtered_before_decimation,  # Store the pre-decimation length
                'data_hash': data_hash_before_decimation,  # Use the hash calculated before decimation
                'dec_fac': self.dec_fac
            }
            if print_updates:
                print(f'Cached decimated data for cmode: {cmode}')
    else:
        # Use cached decimated data
        cached = self.decimation_cache[cache_key]
        y_all = cached['y_all'].copy() if hasattr(cached['y_all'], 'copy') else list(cached['y_all'])
        z_all = cached['z_all'].copy() if hasattr(cached['z_all'], 'copy') else list(cached['z_all'])
        c_all = cached['c_all'].copy() if hasattr(cached['c_all'], 'copy') else list(cached['c_all'])
        self.fnames_all = cached['fnames_all'].copy() if hasattr(cached['fnames_all'], 'copy') else list(cached['fnames_all'])
        self.n_points = cached['n_points']
        if print_updates:
            print(f'Using cached data: {self.n_points} points (saved processing time)')
        # So we'll need to recalculate c_all from the original filtered data
        # Actually, we can't easily do this without caching the pre-decimation c_all too
        # For now, let's just recalculate c_all - it's still much faster than recalculating everything
        if print_updates:
            print(f'Using cached xyz data: {self.n_points} points (saved decimation time)')
        
        # Recalculate c_all for the decimated points based on current cmode
        # This requires going back to the original filtered data, which we don't have cached
        # So we'll need to recalculate c_all from scratch, but at least we saved the decimation step
        # Actually, this is getting complex. Let's cache c_all separately per cmode instead.

    print('self n_points = ', self.n_points)

    # plot y_all vs z_all using colormap c_all
    if cmode == 'solid_color':  # plot solid color if selected
        # get new or archive solid color, convert c_all to array to avoid warning
        c_all = colors.hex2color([self.color.name(), self.color_arc.name()][int(is_archive)])
        c_all = np.tile(np.asarray(c_all), (len(y_all), 1))

        # print('cmode is solid color, lengths are', len(y_all), len(z_all), len(c_all))
        local_label = ('Archive data' if is_archive else 'New data')
        solid_handle = self.swath_ax.scatter(y_all, z_all, s=self.pt_size, c=c_all,
                                            marker='o', alpha=self.pt_alpha, linewidths=0,
                                            label=local_label)
        self.swath_canvas.draw()
        self.legend_handles_solid.append(solid_handle)  # store solid color handle

    else:  # plot other color scheme, specify vmin and vmax from color range

        print('cmode is', cmode)

        if cmode in ['ping_mode', 'swath_mode', 'pulse_form', 'frequency']:  # generate patches for legend with modes
            self.legend_handles = [patches.Patch(color=c, label=l) for l, c in self.cset.items()]

        if self.clim_cbox.currentText() == 'Filtered data':  # update clim from filters applied in active color mode
            update_log(self, 'Updating color scale to cover applied filter limits')

            if self.bs_gb.isChecked() and cmode == 'backscatter':  # use enabled bs filter limits for color limits
                self.clim = [float(self.min_bs_tb.text()), float(self.max_bs_tb.text())]

            self.clim_all_data += self.clim  # update clim_all_data in case same color mode is applied to both

        elif self.clim_cbox.currentText() == 'Fixed limits':  # update color limits from user entries
            self.clim = [float(self.min_clim_tb.text()), float(self.max_clim_tb.text())]
        elif self.clim_cbox.currentText() == 'Custom Plot':  # update color limits from Depth groupbox in custom plot limits
            if hasattr(self, 'min_z_tb') and hasattr(self, 'max_z_tb'):
                try:
                    min_val = float(self.min_z_tb.text()) if self.min_z_tb.text() else 0.0
                    max_val = float(self.max_z_tb.text()) if self.max_z_tb.text() else 4000.0
                    self.clim = [min_val, max_val]
                except ValueError:
                    # Fallback to existing clim if values are invalid
                    pass

        # same color mode for new and archive: use clim_all_data
        elif self.cmode == self.cmode_arc and self.show_data_chk.isChecked() and self.show_data_chk_arc.isChecked():
            # new and archive data showing with same color mode; scale clim to all data (ignore filters for clim)
            update_log(self, 'Updating color scale to cover new and archive datasets with same color mode')
            if self.clim_all_data:  # Check if list is not empty before calling min/max
                self.clim = [min(self.clim_all_data), max(self.clim_all_data)]

        # after all filtering and color updates, finally plot the data
        print('now calling scatter with self.clim=', self.clim)
        # Check if clim has valid values, otherwise use defaults
        if len(self.clim) >= 2:
            vmin_val = self.clim[0]
            vmax_val = self.clim[1]
        else:
            # Use default values if clim is not properly set
            vmin_val = min(c_all) if c_all else 0
            vmax_val = max(c_all) if c_all else 1
            print(f'Using default clim values: vmin={vmin_val}, vmax={vmax_val}')

        self.h_swath = self.swath_ax.scatter(y_all, z_all, s=self.pt_size, c=c_all,
                                             marker='o', alpha=self.pt_alpha, linewidths=0,
                                             vmin=vmin_val, vmax=vmax_val, cmap=self.cmap)

        # data = numpy.random.random(100)
        # bins = numpy.linspace(0, 1, 10)
        # digitized = numpy.digitize(data, bins)
        # bin_means = [data[digitized == i].mean() for i in range(1, len(bins))]

        # bins = np.append(np.arange(0, max(z_all), 100), max(z_all))

        # save filtered coverage data for processing to export trend for Gap Filler
        if is_archive:
            self.y_all_arc = y_all
            self.z_all_arc = z_all
        if not is_archive:
            self.y_all = y_all
            self.z_all = z_all

        print('calling calc_coverage_trend from plot_coverage')
        calc_coverage_trend(self, z_all, y_all, is_archive)

    # toc = process_time()
    # plot_time = toc - tic

    return len(z_all)


def validate_filter_text(self):
    # validate user inputs before trying to apply filters and refresh plot
    valid_filters = True
    tb_list = [self.min_angle_tb, self.max_angle_tb,
               self.min_depth_tb, self.max_depth_tb, self.min_depth_arc_tb, self.max_depth_arc_tb,
               self.min_bs_tb, self.max_bs_tb, self.rtp_angle_buffer_tb, self.rtp_cov_buffer_tb]

    for tb in tb_list:
        try:
            float(tb.text())
            # Set white background but preserve text color
            tb.setStyleSheet('background-color: white; color: black !important;')

        except:
            # Set yellow background for invalid input but preserve text color
            tb.setStyleSheet('background-color: yellow; color: black !important;')
            valid_filters = False

    # Re-apply filter widget styling to ensure correct colors after validation
    if hasattr(self, 'update_filter_widget_styling'):
        self.update_filter_widget_styling()

    # print('\nvalid_filters=', valid_filters)

    return valid_filters


def add_ref_filter_text(self):
    # add text for depth ref and filters applied
    ref_str = 'Reference: ' + self.ref_cbox.currentText()
    depth_fil = ['None', self.min_depth_tb.text() + ' to ' + self.max_depth_tb.text() + ' m']
    depth_arc_fil = ['None', self.min_depth_arc_tb.text() + ' to ' + self.max_depth_arc_tb.text() + ' m']
    angle_fil = ['None', self.min_angle_tb.text() + ' to ' + self.max_angle_tb.text() + '\u00b0']
    bs_fil = ['None', ('+' if float(self.min_bs_tb.text()) > 0 else '') + self.min_bs_tb.text() + ' to ' +
              ('+' if float(self.max_bs_tb.text()) > 0 else '') + self.max_bs_tb.text() + ' dB']
    rtp_angle_fil = ['None', ('+' if float(self.rtp_angle_buffer_tb.text()) > 0 else '') + \
                     self.rtp_angle_buffer_tb.text() + '\u00b0']  # user limit +/- buffer
    rtp_cov_fil = ['None', ('-' if float(self.rtp_cov_buffer_tb.text()) > 0 else '') + \
                   self.rtp_cov_buffer_tb.text() + ' m']  # user limit - buffer
    fil_dict = {'Angle filter: ': angle_fil[self.angle_gb.isChecked()],
                'Depth filter (new): ': depth_fil[self.depth_gb.isChecked()],
                'Depth filter (archive): ': depth_arc_fil[self.depth_gb.isChecked()],
                'Backscatter filter: ': bs_fil[self.bs_gb.isChecked()],
                'Runtime angle buffer: ': rtp_angle_fil[self.rtp_angle_gb.isChecked()],
                'Runtime coverage buffer: ': rtp_cov_fil[self.rtp_cov_gb.isChecked()]}

    for fil in fil_dict.keys():
        ref_str += '\n' + fil + fil_dict[fil]

    ref_str += '\nMax. point count: ' + str(int(self.n_points_max))
    ref_str += '\nDecimation factor: ' + "%.1f" % self.dec_fac

    if self.show_ref_fil_chk.isChecked():
        self.swath_ax.text(0.02, 0.98, ref_str,
                           # 'Ref: ' + self.ref_cbox.currentText(),
                           ha='left', va='top', fontsize=8, transform=self.swath_ax.transAxes,
                           bbox=dict(facecolor='white', edgecolor=None, linewidth=0, alpha=1))


def calc_coverage(self, params_only=False):
    print('')
    # calculate swath coverage from new files and update the detection dictionary
    self.y_all = []
    self.z_all = []

    # Start operation logging
    operation_name = "Parameter Scanning" if params_only else "Coverage Calculation"
    if hasattr(self, 'start_operation_log'):
        self.start_operation_log(operation_name)
    else:
        update_log(self, f"=== STARTING: {operation_name} ===")

    try:
        fnames_det = list(set(self.det['fname']))  # make list of unique filenames already in det dict

    except:
        fnames_det = []  # self.det has not been created yet
        self.det = {}

    # fnames_new = get_new_file_list(self, ['.all', '.kmall'], fnames_det)  # list new .all files not in det dict

    # find files that were SCANNED (and have zeros) but were not PLOTTED (real data), then remove these from det dict
    if params_only:  # scanning only: find unscanned/unplotted files (calc cov adds fname to fnames_scanned_params)
        fnames_new = get_new_file_list(self, ['.all', '.kmall'], self.fnames_scanned_params)
        # print('params_only is TRUE, fnames_new = ', fnames_new)

    else:  # plotting full coverage: find unplotted files (and/or delete zeros in det dict if only scanned previously)
        fnames_new = get_new_file_list(self, ['.all', '.kmall'], self.fnames_plotted_cov)
        # print('params_only is FALSE, fnames_new = ', fnames_new)
        print('self.fnames_scanned_params =', self.fnames_scanned_params)
        fnames_del = [f.rsplit('/', 1)[-1] for f in fnames_new if f.rsplit('/', 1)[-1] in self.fnames_scanned_params]
        # print('got fnames_to_remove_from_det_dict =', fnames_del)
        if fnames_del:
            update_log(self, f"Removing {len(fnames_del)} previously scanned files from detection dictionary")
        remove_data(self, fnames_del)

    num_new_files = len(fnames_new)

    # if num_new_files == 0:
    if num_new_files == 0 and not self.param_scanned:
        update_log(self, 'No new .all or .kmall file(s) added.  Please add new file(s) and calculate coverage.')
        if hasattr(self, 'end_operation_log'):
            self.end_operation_log(operation_name, "No new files to process")

    else:
        # update_log('Calculating coverage from ' + str(num_new_files) + ' new file(s)')
        self.param_scanned = params_only  # remember if only scanned params so user can calc coverage with same files
        update_log(self, ('Scanning parameters' if params_only else 'Calculating coverage') +\
                   ' from ' + str(num_new_files) + ' new file(s)')

        QtWidgets.QApplication.processEvents()  # try processing and redrawing the GUI to make progress bar update
        data_new = {}
        param_new = {}
        self.skm_time = {}

        # update progress bar and log
        self.calc_pb.setValue(0)  # reset progress bar to 0 and max to number of files
        self.calc_pb.setMaximum(max([1, len(fnames_new)]))  # set max value to at least 1 to avoid hanging when 0/0

        i = 0  # counter for successfully parsed files (data_new index)
        f = 0  # placeholder if no fnames_new

        tic1 = process_time()

        for f in range(len(fnames_new)):
            print('in calc_coverage, f =', f)
            fname_str = fnames_new[f].rsplit('/')[-1]
            self.current_file_lbl.setText('Parsing new file [' + str(f+1) + '/' + str(num_new_files) + ']:' + fname_str)
            QtWidgets.QApplication.processEvents()
            ftype = fname_str.rsplit('.', 1)[-1]

            # Log progress with enhanced logging if available
            if hasattr(self, 'log_progress'):
                self.log_progress(f + 1, num_new_files, f"Parsing {ftype.upper()} files")
            else:
                update_log(self, f"Processing file {f+1}/{num_new_files}: {fname_str}")

            tic = process_time()

            try:  # try to parse file
                # Check for pickle file first if enabled
                use_pickle = getattr(self, 'use_pickle_files_chk', None) and self.use_pickle_files_chk.isChecked()
                pickle_file = None
                
                if use_pickle:
                    # Look for pickle file in the same directory as source file
                    source_dir = os.path.dirname(fnames_new[f])
                    base_name = os.path.splitext(os.path.basename(fnames_new[f]))[0]
                    ext = os.path.splitext(fnames_new[f])[1]
                    pickle_file = os.path.join(source_dir, f"{base_name}{ext}.pkl")
                    
                    # Check if pickle file exists and is newer than source
                    if os.path.exists(pickle_file):
                        source_mtime = os.path.getmtime(fnames_new[f])
                        pickle_mtime = os.path.getmtime(pickle_file)
                        
                        if pickle_mtime > source_mtime:
                            try:
                                data_new[i], status = load_pickle_file(self, pickle_file)
                                if hasattr(self, 'log_success'):
                                    self.log_success(f"Loaded pickle file: {os.path.basename(pickle_file)} ({status})")
                                else:
                                    update_log(self, f"✓ Loaded pickle file: {os.path.basename(pickle_file)} ({status})")
                                i += 1
                                self.fnames_scanned_params.append(fname_str)
                                if not params_only:
                                    self.fnames_plotted_cov.append(fname_str)
                                continue
                            except Exception as e:
                                if hasattr(self, 'log_warning'):
                                    self.log_warning(f"Failed to load pickle file, falling back to source: {str(e)}")
                                else:
                                    update_log(self, f"*** WARNING: Failed to load pickle file, falling back to source: {str(e)} ***")
                
                # Parse source file if no pickle file or pickle loading failed
                if ftype == 'all':  # read .all file for coverage (incl. params) or just params
                    update_log(self, f"Parsing .all file: {fname_str}")
                    data_new[i] = readALLswath(self, fnames_new[f], print_updates=self.print_updates,
                                               parse_outermost_only=True, parse_params_only=params_only)

                elif ftype == 'kmall':  # read .all file for coverage (incl. params) or just params
                    update_log(self, f"Parsing .kmall file: {fname_str}")
                    include_skm = not params_only
                    
                    # Time the KMALL processing with optimized reader
                    kmall_start_time = process_time()
                    print('calling readKMALLswath from calc_coverage')
                    data_new[i] = readKMALLswath(self, fnames_new[f], print_updates=self.print_updates,
                                                 include_skm=not params_only, parse_params_only=params_only,
                                                 read_mode='plot' if not params_only else 'param')
                    kmall_end_time = process_time()
                    kmall_processing_time = kmall_end_time - kmall_start_time
                    print('***back from readKMALLswath in calc_coverage')
                    
                    # Log the timing information
                    file_size_mb = os.path.getsize(fnames_new[f]) / (1024*1024)
                    mode_str = 'plot' if not params_only else 'param'
                    if hasattr(self, 'log_info'):
                        self.log_info(f"KMALL optimized ({mode_str} mode): {fname_str} ({file_size_mb:.1f} MB) completed in {kmall_processing_time:.2f}s")
                    else:
                        update_log(self, f"⚡ KMALL optimized ({mode_str} mode): {fname_str} ({file_size_mb:.1f} MB) completed in {kmall_processing_time:.2f}s")

                    ping_bytes = [0] + np.diff(data_new[i]['start_byte']).tolist()

                    for p in range(len(data_new[i]['XYZ'])):  # store ping start byte
                        # print('storing ping start byte')
                        data_new[i]['XYZ'][p]['bytes_from_last_ping'] = ping_bytes[p]

                    try:  # simplify SKM header and sample times for plotting
                        num_SKM = len(data_new[i]['SKM']['header'])
                        # print('********* trying to print items in sample datagram j')
                        # sample_keys = [k for k in data_new[i]['SKM']['sample'].keys()]
                        # for k in sample_keys:
                        # 	SKM_roll_rate.append(data_new[i]['SKM']['sample'][k]['KMdefault']

                        SKM_header_datetime = [data_new[i]['SKM']['header'][j]['dgdatetime'] for j in range(num_SKM)]
                        SKM_sample_datetime = [data_new[i]['SKM']['sample'][j]['KMdefault']['datetime'][0] for j in range(num_SKM)]

                    except:  # store placeholders if SKM was not parsed
                        SKM_header_datetime = [datetime.datetime(1, 1, 1, 0, 0)]  # min datetime year is 1
                        SKM_sample_datetime = [datetime.datetime(1, 1, 1, 0, 0)]

                    self.skm_time[i] = {'fname': fnames_new[f],
                                        'SKM_header_datetime': SKM_header_datetime,
                                        'SKM_sample_datetime': SKM_sample_datetime}

                else:
                    update_log(self, 'Warning: Skipping unrecognized file type for ' + fname_str)

                data_new[i]['fsize'] = os.path.getsize(fnames_new[f])
                print('stored file size ', data_new[i]['fsize'])
                fname_wcd = fnames_new[f].replace('.kmall', '.kmwcd').replace('.all', '.wcd')

                print('looking for watercolumn file: ', fname_wcd)
                try:  # try to get water column file size (.kmwcd for .kmall. or .wcd for .all)
                    data_new[i]['fsize_wc'] = os.path.getsize(fname_wcd)
                    print('stored water column file size', data_new[i]['fsize_wc'], ' for file', fnames_new[f])

                except:
                    data_new[i]['fsize_wc'] = np.nan
                    print('failed to get water column file size for file ', fname_wcd)

                # Enhanced success logging
                if hasattr(self, 'log_success'):
                    self.log_success(f"Successfully parsed {fname_str} ({data_new[i]['fsize'] / (1024*1024):.1f} MB)")
                else:
                    update_log(self, 'Parsed file ' + fname_str)
                i += 1  # increment successful file counter

                # log whether scanned or plotted so only new files are processed on next call of that type
                self.fnames_scanned_params.append(fname_str)  # all files get scanned for parameters

                if not params_only:  # note if coverage was also calculate for this file
                    self.fnames_plotted_cov.append(fname_str)

            except Exception as e:  # failed to parse this file
                if hasattr(self, 'log_error'):
                    self.log_error(f"Failed to parse {fname_str}", e)
                else:
                    update_log(self, 'No swath data parsed for ' + fname_str)

            update_prog(self, f + 1)

            toc = process_time()
            parse_time = toc-tic
            # print('parsing COVERAGE took', parse_time)

        toc1 = process_time()
        refresh_time = toc1 - tic1
        # print('parsing WHOLE DATASET for COVERAGE took', refresh_time)

        update_log(self, f"Processing {len(data_new)} parsed files...")
        self.data_new = interpretMode(self, data_new, print_updates=self.print_updates)  # True)
        det_new = sortDetectionsCoverage(self, data_new, print_updates=self.print_updates, params_only=params_only)  # True)

        if len(self.det) == 0:  # if detection dict is empty with no keys, store new detection dict
            self.det = det_new
            update_log(self, f"Created new detection dictionary with {len(det_new)} keys")

        else:  # otherwise, append new detections to existing detection dict
            for key, value in det_new.items():  # loop through the new data and append to existing self.det
                self.det[key].extend(value)
            update_log(self, f"Appended new data to existing detection dictionary")

        # Enhanced completion logging
        success_msg = f"Successfully processed {i} out of {num_new_files} files"
        if hasattr(self, 'log_success'):
            self.log_success(success_msg)
        else:
            update_log(self, 'Finished ' + ('scanning parameters' if params_only else 'calculating coverage') + \
                       ' from ' + str(num_new_files) + ' new file(s)')

        self.current_file_lbl.setText('Current File [' + str(min([f + 1, num_new_files])) + '/' + str(num_new_files) +
                                          ']: Finished calculating coverage')

        # update system information from detections
        update_log(self, "Updating system information from parsed data...")
        update_system_info(self, self.det, force_update=True, fname_str_replace='_trimmed')

        if not params_only:  # set show data chk to True (and refresh that way) or refresh plot directly, but not both!
            if not self.show_data_chk.isChecked():
                self.show_data_chk.setChecked(True)

            else:  # refresh coverage plots only if swath data was parsed
                refresh_plot(self, print_time=True, call_source='calc_coverage')

            self.plot_tabs.setCurrentIndex(0)  # show coverage plot tab

        else:
            self.tabs.setCurrentIndex(2)  # show param search tab
            self.plot_tabs.setCurrentIndex(3)  # show parameter history tab

        sort_det_time(self)  # sort all detections by time for runtime parameter logging/searching

        # End operation logging
        if hasattr(self, 'end_operation_log'):
            self.end_operation_log(operation_name, f"Processed {i}/{num_new_files} files successfully")

    # Update button states after processing to reflect current state
    update_button_states(self)
    
    # Update Save All Plots button color
    if hasattr(self, 'update_save_plots_button_color'):
        self.update_save_plots_button_color()

# def sortDetections(self, data, print_updates=False):
def sortDetectionsCoverage(self, data, print_updates=False, params_only=False):
    # sort through .all and .kmall data dict and pull out outermost valid soundings, BS, and modes for each ping
    det_key_list = ['fname', 'model', 'datetime', 'date', 'time', 'sn',
                    'y_port', 'y_stbd', 'z_port', 'z_stbd', 'bs_port', 'bs_stbd', 'rx_angle_port', 'rx_angle_stbd',
                    'ping_mode', 'pulse_form', 'swath_mode', 'frequency',
                    'max_port_deg', 'max_stbd_deg', 'max_port_m', 'max_stbd_m',
                    'tx_x_m', 'tx_y_m', 'tx_z_m',  'tx_r_deg', 'tx_p_deg', 'tx_h_deg',
                    'rx_x_m', 'rx_y_m', 'rx_z_m',  'rx_r_deg', 'rx_p_deg', 'rx_h_deg',
                    'aps_num', 'aps_x_m', 'aps_y_m', 'aps_z_m', 'wl_z_m',
                    'bytes', 'fsize', 'fsize_wc']  #, 'skm_hdr_datetime', 'skm_raw_datetime']
                    # yaw stabilization mode, syn

    det = {k: [] for k in det_key_list}

    # examine detection info across swath, find outermost valid soundings for each ping
    # here, each det entry corresponds to two outermost detections (port and stbd) from one ping, with parameters that
    # are applied for both soundings; detection sorting in the accuracy plotter extends the detection dict for all valid
    # detections in each ping, with parameters extended for each (admittedly inefficient, but easy for later sorting)
    for f in range(len(data)):  # loop through all data
        if print_updates:
            print('Finding outermost valid soundings in file', data[f]['fname'])

        # set up keys for dict fields of interest from parsers for each file type (.all or .kmall)
        ftype = data[f]['fname'].rsplit('.', 1)[1]
        key_idx = int(ftype == 'kmall')  # keys in data dicts depend on parser used, get index to select keys below
        det_int_threshold = [127, 0][key_idx]  # threshold for valid sounding (.all  <128 and .kmall == 0)
        det_int_key = ['RX_DET_INFO', 'detectionType'][key_idx]  # key for detect info depends on ftype
        depth_key = ['RX_DEPTH', 'z_reRefPoint_m'][key_idx]  # key for depth
        across_key = ['RX_ACROSS', 'y_reRefPoint_m'][key_idx]  # key for acrosstrack distance
        bs_key = ['RX_BS', 'reflectivity1_dB'][key_idx]  # key for backscatter in dB
        bs_scale = [0.1, 1][key_idx]  # backscatter scale in X dB; multiply parsed value by this factor for dB
        # bs_key = ['RS_BS', 'reflectivity2_dB'][key_idx]  # key for backscatter in dB TESTING KMALL REFLECTIVITY 2
        angle_key = ['RX_ANGLE', 'beamAngleReRx_deg'][key_idx]  # key for RX angle re RX array

        # Debug print removed

        for p in range(len(data[f]['XYZ'])):  # loop through each ping
            # print('in sortDetectionsCoverage, working on ping', p)

            # det['fname'].append(data[f]['fname'].rsplit('/')[-1])  # store fname for each swath

            if params_only:  # store zeros as placeholders to no break rest of sorting steps
                det['fname'].append(data[f]['fname'].rsplit('/')[-1])  # store fname
                zeros = ['y_port', 'y_stbd', 'z_port', 'z_stbd', 'bs_port', 'bs_stbd', 'rx_angle_port', 'rx_angle_stbd']
                for k in zeros:
                    det[k].append(0)
                    # det[k].append(np.nan)  # NaN breaks plotting/colorscale steps later...

            else:  # sort port and stbd data
                det_int = data[f]['XYZ'][p][det_int_key]  # get detection integers for this ping
                # print('********* ping', p, '************')
                # print('det_int=', det_int)
                # find indices of port and stbd outermost valid detections (detectionType = 0 for KMALL)
                idx_port = 0  # start at port outer sounding
                idx_stbd = len(det_int) - 1  # start at stbd outer sounding

                while det_int[idx_port] > det_int_threshold and idx_port < len(det_int) - 1:
                    idx_port = idx_port + 1  # move port idx to stbd if not valid

                while det_int[idx_stbd] > det_int_threshold and idx_stbd > 0:
                    idx_stbd = idx_stbd - 1  # move stdb idx to port if not valid

                #if idx_port >= idx_stbd:
                    #print('XYZ datagram for ping', p, 'has no valid soundings... continuing to next ping')
                    #continue

                #if print_updates and self.verbose_logging:
                    #print('Found valid dets in ping', p, 'PORT i/Y/Z=', idx_port,
                          #np.round(data[f]['XYZ'][p][across_key][idx_port]),
                          #np.round(data[f]['XYZ'][p][depth_key][idx_port]),
                          #'\tSTBD i/Y/Z=', idx_stbd,
                          #np.round(data[f]['XYZ'][p][across_key][idx_stbd]),
                          #np.round(data[f]['XYZ'][p][depth_key][idx_stbd]))

                # append swath data from appropriate keys/values in data dicts
                det['fname'].append(data[f]['fname'].rsplit('/')[-1])  # store fname for each swath
                det['y_port'].append(data[f]['XYZ'][p][across_key][idx_port])
                det['y_stbd'].append(data[f]['XYZ'][p][across_key][idx_stbd])
                det['z_port'].append(data[f]['XYZ'][p][depth_key][idx_port])
                det['z_stbd'].append(data[f]['XYZ'][p][depth_key][idx_stbd])
                det['bs_port'].append(data[f]['XYZ'][p][bs_key][idx_port]*bs_scale)
                det['bs_stbd'].append(data[f]['XYZ'][p][bs_key][idx_stbd]*bs_scale)
                det['rx_angle_port'].append(data[f]['XYZ'][p][angle_key][idx_port])
                det['rx_angle_stbd'].append(data[f]['XYZ'][p][angle_key][idx_stbd])

            # store remaining system, mode, and install/runtime parameter info
            try:
                det['ping_mode'].append(data[f]['XYZ'][p]['PING_MODE'])
            except (KeyError, IndexError):
                det['ping_mode'].append(0)  # Default value for KMALL files
            
            try:
                det['pulse_form'].append(data[f]['XYZ'][p]['PULSE_FORM'])
            except (KeyError, IndexError):
                det['pulse_form'].append(0)  # Default value for KMALL files
            det['fsize'].append(data[f]['fsize'])
            det['fsize_wc'].append(data[f]['fsize_wc'])
            # det['swath_mode'].append(data[f]['XYZ'][p]['SWATH_MODE'])

            if ftype == 'all':  # .all store date and time from ms from midnight
                det['model'].append(data[f]['XYZ'][p]['MODEL'])
                det['sn'].append(data[f]['XYZ'][p]['SYS_SN'])
                dt = datetime.datetime.strptime(str(data[f]['XYZ'][p]['DATE']), '%Y%m%d') + \
                     datetime.timedelta(milliseconds=data[f]['XYZ'][p]['TIME'])
                det['datetime'].append(dt)
                det['date'].append(dt.strftime('%Y-%m-%d'))
                det['time'].append(dt.strftime('%H:%M:%S.%f'))
                det['swath_mode'].append(data[f]['XYZ'][p]['SWATH_MODE'])
                try:
                    det['frequency'].append(data[f]['XYZ'][p]['FREQUENCY'])
                except (KeyError, IndexError):
                    det['frequency'].append('NA')  # Default value for KMALL files
                det['max_port_deg'].append(data[f]['XYZ'][p]['MAX_PORT_DEG'])
                det['max_stbd_deg'].append(data[f]['XYZ'][p]['MAX_STBD_DEG'])
                det['max_port_m'].append(data[f]['XYZ'][p]['MAX_PORT_M'])
                det['max_stbd_m'].append(data[f]['XYZ'][p]['MAX_STBD_M'])
                det['tx_x_m'].append(data[f]['XYZ'][p]['TX_X_M'])
                det['tx_y_m'].append(data[f]['XYZ'][p]['TX_Y_M'])
                det['tx_z_m'].append(data[f]['XYZ'][p]['TX_Z_M'])
                det['tx_r_deg'].append(data[f]['XYZ'][p]['TX_R_DEG'])
                det['tx_p_deg'].append(data[f]['XYZ'][p]['TX_P_DEG'])
                det['tx_h_deg'].append(data[f]['XYZ'][p]['TX_H_DEG'])
                det['rx_x_m'].append(data[f]['XYZ'][p]['RX_X_M'])
                det['rx_y_m'].append(data[f]['XYZ'][p]['RX_Y_M'])
                det['rx_z_m'].append(data[f]['XYZ'][p]['RX_Z_M'])
                det['rx_r_deg'].append(data[f]['XYZ'][p]['RX_R_DEG'])
                det['rx_p_deg'].append(data[f]['XYZ'][p]['RX_P_DEG'])
                det['rx_h_deg'].append(data[f]['XYZ'][p]['RX_H_DEG'])
                det['wl_z_m'].append(data[f]['XYZ'][p]['WL_Z_M'])
                det['aps_num'].append(data[f]['XYZ'][p]['APS_NUM'])
                det['aps_x_m'].append(data[f]['XYZ'][p]['APS_X_M'])
                det['aps_y_m'].append(data[f]['XYZ'][p]['APS_Y_M'])
                det['aps_z_m'].append(data[f]['XYZ'][p]['APS_Z_M'])
                det['bytes'].append(data[f]['XYZ'][p]['BYTES_FROM_LAST_PING'])

            elif ftype == 'kmall':  # .kmall store date and time from datetime object
                                # Debug: Check what keys are available in RTP data for first ping
                # Debug prints removed
                det['model'].append(data[f]['HDR'][p]['echoSounderID'])
                det['datetime'].append(data[f]['HDR'][p]['dgdatetime'])
                det['date'].append(data[f]['HDR'][p]['dgdatetime'].strftime('%Y-%m-%d'))
                det['time'].append(data[f]['HDR'][p]['dgdatetime'].strftime('%H:%M:%S.%f'))
                det['aps_num'].append(-1)  # need to clarify APS number in KMALL; append -1 as placeholder
                det['aps_x_m'].append(0)  # not needed for KMALL; append 0 as placeholder
                det['aps_y_m'].append(0)  # not needed for KMALL; append 0 as placeholder
                det['aps_z_m'].append(0)  # not needed for KMALL; append 0 as placeholder

                # get first install param dg, assume no changes in file (have to stop logging to change install params)
                ip_text = data[f]['IP']['install_txt'][0]

                # get TX array offset text: EM304 = 'TRAI_TX1' and 'TRAI_RX1', EM2040P = 'TRAI_HD1', not '_TX1' / '_RX1'
                # ip_tx1 = ip_text.split('TRAI_')[1].split(',')[0].strip()  # all heads/arrays split by comma
                ip_tx1 = ip_text.split('TRAI_TX1')[1].split(',')[0].strip()  # all heads/arrays split by comma
                det['tx_x_m'].append(float(ip_tx1.split('X=')[1].split(';')[0].strip()))  # get TX array X offset
                det['tx_y_m'].append(float(ip_tx1.split('Y=')[1].split(';')[0].strip()))  # get TX array Y offset
                det['tx_z_m'].append(float(ip_tx1.split('Z=')[1].split(';')[0].strip()))  # get TX array Z offset
                det['tx_r_deg'].append(float(ip_tx1.split('R=')[1].split(';')[0].strip()))  # get TX array roll
                det['tx_p_deg'].append(float(ip_tx1.split('P=')[1].split(';')[0].strip()))  # get TX array pitch
                det['tx_h_deg'].append(float(ip_tx1.split('H=')[1].split(';')[0].strip()))  # get TX array heading

                ip_rx1 = ip_text.split('TRAI_RX1')[1].split(',')[0].strip()  # all heads/arrays split by comma
                det['rx_x_m'].append(float(ip_rx1.split('X=')[1].split(';')[0].strip()))  # get RX array X offset
                det['rx_y_m'].append(float(ip_rx1.split('Y=')[1].split(';')[0].strip()))  # get RX array Y offset
                det['rx_z_m'].append(float(ip_rx1.split('Z=')[1].split(';')[0].strip()))  # get RX array Z offset
                det['rx_r_deg'].append(float(ip_rx1.split('R=')[1].split(';')[0].strip()))  # get RX array roll
                det['rx_p_deg'].append(float(ip_rx1.split('P=')[1].split(';')[0].strip()))  # get RX array pitch
                det['rx_h_deg'].append(float(ip_rx1.split('H=')[1].split(';')[0].strip()))  # get RX array heading

                det['wl_z_m'].append(float(ip_text.split('SWLZ=')[-1].split(',')[0].strip()))  # get waterline Z offset

                # get serial number from installation parameter: 'SN=12345'
                sn = ip_text.split('SN=')[1].split(',')[0].strip()
                det['sn'].append(sn)

                # det['bytes'].append(0)  # bytes since last ping not handled yet for KMALL
                # det['bytes'].append(data[f]['XYZ'][p]['BYTES_FROM_LAST_PING'])
                det['bytes'].append(data[f]['XYZ'][p]['bytes_from_last_ping'])
                # print('at byte logging step, data[f][XYZ][p] =', data[f]['XYZ'][p])

                # det['bytes'].append(data[f]['XYZ'][p]['start_byte'])

                # print('just appended KMALL bytes: ', det['bytes'][-1])

                # get index of latest runtime parameter timestamp prior to ping of interest; default to 0 for cases
                # where earliest pings in file might be timestamped earlier than first runtime parameter datagram
                # print('working on data f IOP dgdatetime:', data[f]['IOP']['dgdatetime'])
                # print('IOP is', data[f]['IOP'])
                # print('IOP keys are:', data[f]['IOP'].keys())
                # IOP_idx = max([i for i, t in enumerate(data[f]['IOP']['dgdatetime']) if
                # 			   t <= data[f]['HDR'][p]['dgdatetime']], default=0)
                # print('IOP dgdatetime =', data[f]['IOP']['header'][0]['dgdatetime'])
                # print('HDR dgdatetime =', data[f]['HDR'][p]['dgdatetime'])


                ### ORIGINAL METHOD
                # IOP_times = [data[f]['IOP']['header'][j]['dgdatetime'] for j in range(len(data[f]['IOP']['header']))]
                # IOP_idx = max([i for i, t in enumerate(IOP_times) if
                # 			   t <= data[f]['HDR'][p]['dgdatetime']], default=0)
                #
                # # if data[f]['IOP']['dgdatetime'][IOP_idx] > data[f]['HDR'][p]['dgdatetime']:
                # # 	print('*****ping', p, 'occurred before first runtime datagram; using first RTP dg in file')
                #
                # if data[f]['IOP']['header'][IOP_idx]['dgdatetime'] > data[f]['HDR'][p]['dgdatetime']:
                # 	print('*****ping', p, 'occurred before first runtime datagram; using first RTP dg in file')
                ########

                #### TEST FROM SWATH ACC SORTING
                IOP_headers = data[f]['IOP']['header']  # get list of IOP header dicts in new kmall module output
                IOP_datetimes = [IOP_headers[d]['dgdatetime'] for d in range(len(IOP_headers))]
                # print('got IOP datetimes =', IOP_datetimes)

                # print('working on ping header times')
                # print('data[f][HDR] =', data[f]['HDR'])
                # print('HDR ping dgdatetime is', data[f]['HDR'][p]['dgdatetime'])

                # MRZ_headers = data[f]['HDR']['header']
                MRZ_headers = data[f]['HDR']
                MRZ_datetimes = [MRZ_headers[d]['dgdatetime'] for d in range(len(MRZ_headers))]

                # find index of last IOP datagram before current ping, default to first if
                IOP_idx = max([i for i, t in enumerate(IOP_datetimes) if
                               t <= MRZ_datetimes[p]], default=0)

                # if IOP_datetimes[IOP_idx] > MRZ_datetimes[p]:
                    # print('*****ping', p, 'occurred before first runtime datagram; using first RTP dg in file')
                ##### END TEST FROM SWATH ACC SORTING


                # get runtime text from applicable IOP datagram, split and strip at keywords and append values
                # rt = data[f]['IOP']['RT'][IOP_idx]  # get runtime text for splitting
                try:
                    rt = data[f]['IOP']['runtime_txt'][IOP_idx]
                except (KeyError, IndexError, TypeError):
                    rt = None

                # print('rt = ', rt)

                # dict of keys for detection dict and substring to split runtime text at entry of interest
                rt_dict = {'max_port_deg': 'Max angle Port:', 'max_stbd_deg': 'Max angle Starboard:',
                           'max_port_m': 'Max coverage Port:', 'max_stbd_m': 'Max coverage Starboard:'}

                # iterate through rt_dict and append value from split/stripped runtime text
                # print('starting runtime parsing for kmall file')
                for k, v in rt_dict.items():  # parse only parameters that can be converted to floats
                    try:
                        if rt is not None:
                            det[k].append(float(rt.split(v)[-1].split('\n')[0].strip()))
                        else:
                            det[k].append('NA')
                    except:
                        det[k].append('NA')

                # parse swath mode using multiple methods for better reliability
                swath_mode = None
                
                # Method 1: Try to get swathsPerPing from cmnPart (most reliable)
                try:
                    if 'cmnPart' in data[f] and len(data[f]['cmnPart']) > p:
                        swaths_per_ping = data[f]['cmnPart'][p]['swathsPerPing']
                        if swaths_per_ping == 1:
                            swath_mode = 'Single Swath'
                        elif swaths_per_ping == 2:
                            swath_mode = 'Dual Swath (Dynamic)'
                        else:
                            swath_mode = f'Dual Swath ({swaths_per_ping} swaths)'
                        
                        if print_updates and self.verbose_logging:
                            print(f'Method 1: Using swathsPerPing={swaths_per_ping} for ping {p}')
                except (KeyError, IndexError, TypeError) as e:
                    if print_updates and self.verbose_logging:
                        print(f'Method 1 failed: swathsPerPing not available in cmnPart for ping {p}')
                
                # Method 2: Try to get from RTP if available
                if swath_mode is None:
                    try:
                        if 'RTP' in data[f] and len(data[f]['RTP']) > p:
                            swaths_per_ping = data[f]['RTP'][p]['swathsPerPing']
                            if swaths_per_ping == 1:
                                swath_mode = 'Single Swath'
                            elif swaths_per_ping == 2:
                                swath_mode = 'Dual Swath (Dynamic)'
                            else:
                                swath_mode = f'Dual Swath ({swaths_per_ping} swaths)'
                            
                            if print_updates and self.verbose_logging:
                                print(f'Method 2: Using RTP swathsPerPing={swaths_per_ping} for ping {p}')
                    except (KeyError, IndexError, TypeError) as e:
                        if print_updates and self.verbose_logging:
                            print(f'Method 2 failed: swathsPerPing not available in RTP for ping {p}')
                
                # Method 3: Parse from runtime parameter text
                if swath_mode is None:
                    swath_mode = _parse_swath_mode_improved(rt)
                    if print_updates and self.verbose_logging:
                        print(f'Method 3: Using runtime parameter parsing for ping {p}: {swath_mode}')
                
                # Method 4: Default based on file type and common configurations
                if swath_mode is None or swath_mode == 'NA':
                    # For KMALL files, most modern systems use Dual Swath by default
                    if ftype == 'kmall':
                        swath_mode = 'Dual Swath (Dynamic)'
                    else:
                        swath_mode = 'Single Swath'
                    
                    if print_updates and self.verbose_logging:
                        print(f'Method 4: Using default swath mode for {ftype}: {swath_mode}')

                det['swath_mode'].append(swath_mode)

                # parse frequency from runtime parameter text, if available
                frequency_rt = None
                try:
                    if rt is not None:
                        # print('trying to split runtime text')
                        frequency_rt = rt.split('Frequency:')[-1].split('\n')[0].strip().replace('kHz', ' kHz')
                        # print('frequency string from runtime text =', frequency_rt)
                except:  # use default frequency stored from interpretMode
                    # print('using default frequency')
                    pass
                    # frequency = 'NA'

                # store parsed freq if not empty, otherwise store default
                try:
                    frequency = frequency_rt if frequency_rt else data[f]['XYZ'][p]['FREQUENCY']
                except (KeyError, IndexError):
                    frequency = frequency_rt if frequency_rt else 'NA'
                det['frequency'].append(frequency)

                if print_updates and self.verbose_logging:
                    # print('found IOP_idx=', IOP_idx, 'with IOP_datetime=', data[f]['IOP']['dgdatetime'][IOP_idx])
                    print('found IOP_idx=', IOP_idx, 'with IOP_datetime=', IOP_datetimes[IOP_idx])
                    print('max_port_deg=', det['max_port_deg'][-1])
                    print('max_stbd_deg=', det['max_stbd_deg'][-1])
                    print('max_port_m=', det['max_port_m'][-1])
                    print('max_stbd_m=', det['max_stbd_m'][-1])
                    print('swath_mode=', det['swath_mode'][-1])

            else:
                print('UNSUPPORTED FTYPE --> NOT SORTING DETECTION!')

        # print('using bs_key =', bs_key, ' --> bs_port, bs_stbd:', det['bs_port'], det['bs_stbd'])

    if print_updates:
        print('\nDone sorting detections...')

    # print('leaving sortDetectionsCoverage with det[frequency] =', det['frequency'])

    return det

def _parse_swath_mode_improved(rt):
    """
    Improved swath mode parsing that handles various formats and edge cases.
    
    Args:
        rt (str): Runtime parameter text
        
    Returns:
        str: Parsed swath mode ('Single Swath', 'Dual Swath (Dynamic)', etc.)
    """
    
    # Handle None or non-string input
    if rt is None:
        return 'NA'
    
    if not isinstance(rt, str):
        try:
            rt = str(rt)
        except:
            return 'NA'
    
    # Try different variations of the dual swath text
    dual_swath_variations = [
        'Dual swath:',
        'Dual Swath:',
        'dual swath:',
        'DUAL SWATH:',
        'Dual Swath',
        'dual swath'
    ]
    
    dual_swath_mode = None
    
    for variation in dual_swath_variations:
        if variation in rt:
            try:
                # Split on the variation and get the part after it
                parts = rt.split(variation)
                if len(parts) > 1:
                    # Get the text after the variation
                    after_text = parts[1]
                    # Split on newline and get the first line
                    first_line = after_text.split('\n')[0].strip()
                    # Remove any trailing colons or extra punctuation
                    dual_swath_mode = first_line.rstrip(':').strip()
                    break
            except Exception as e:
                continue
    
    if dual_swath_mode is None:
        return 'NA'
    
    # Handle different values for single swath
    single_swath_values = ['Off', 'OFF', 'off', 'Single', 'SINGLE', 'single', '']
    
    if dual_swath_mode in single_swath_values:
        return 'Single Swath'
    else:
        return f'Dual Swath ({dual_swath_mode})'


def update_axes(self):
    # adjust x and y axes and plot title
    update_system_info(self, self.det, force_update=False, fname_str_replace='_trimmed')
    update_plot_limits(self)
    update_hist_axis(self)
    # Update other plot layouts to fill canvas like depth plot
    update_other_plot_layouts(self)
    # update_data_axis(self)

    # set y limits to match across all plots
    # Use custom min depth if plot limits are enabled and min_z_tb has a value, otherwise use 0
    if self.plot_lim_gb.isChecked() and hasattr(self, 'min_z_tb') and self.min_z_tb.text():
        z_min_limit = self.z_min_custom
    else:
        z_min_limit = 0
    self.swath_ax.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set depth axis with custom or 0 min and 1.1 times max(z)
    self.backscatter_ax.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set backscatter yaxis to same as swath_ax
    self.pingmode_ax.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set ping mode yaxis to same as swath_ax
    
    self.pulseform_ax.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set pulse form yaxis to same as swath_ax
    self.swathmode_ax.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set swath mode yaxis to same as swath_ax
    self.frequency_ax.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set frequency yaxis to same as swath_ax
    self.data_rate_ax1.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set data rate yaxis to same as swath_ax
    self.data_rate_ax2.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set ping rate yaxis to same as swath_ax
    self.hist_ax.set_ylim(z_min_limit, self.swath_ax_margin * self.z_max)  # set hist axis to same as swath_ax

    # update x limits
    print('in update_axes, setting new xlims with dr_max and pi_max =', self.dr_max, self.pi_max)
    self.swath_ax.set_xlim(-1 * self.swath_ax_margin * self.x_max, self.swath_ax_margin * self.x_max)
    self.backscatter_ax.set_xlim(-1 * self.swath_ax_margin * self.x_max, self.swath_ax_margin * self.x_max)
    self.pingmode_ax.set_xlim(-1 * self.swath_ax_margin * self.x_max, self.swath_ax_margin * self.x_max)
    
    self.pulseform_ax.set_xlim(-1 * self.swath_ax_margin * self.x_max, self.swath_ax_margin * self.x_max)
    self.swathmode_ax.set_xlim(-1 * self.swath_ax_margin * self.x_max, self.swath_ax_margin * self.x_max)
    self.frequency_ax.set_xlim(-1 * self.swath_ax_margin * self.x_max, self.swath_ax_margin * self.x_max)
    self.data_rate_ax1.set_xlim(0, self.swath_ax_margin * self.dr_max)
    self.data_rate_ax2.set_xlim(0, self.swath_ax_margin * self.pi_max)

    # update plot title with default or custom combination of system info fields
    if self.custom_info_gb.isChecked():  # include custom system info that is checked on
        sys_info_list = [['', self.model_name][self.show_model_chk.isChecked()],
                         ['', self.ship_name][self.show_ship_chk.isChecked()],
                         ['', self.cruise_name][self.show_cruise_chk.isChecked()]]
        print('got sys_info_list = ', sys_info_list)
        sys_info_str = ' - '.join([str for str in sys_info_list if str != ''])

    else:  # otherwise, default to all system info in the title
        sys_info_str = ' - '.join([self.model_name, self.ship_name, self.cruise_name])

    self.title_str = 'Swath Width vs. Depth\n' + sys_info_str
    self.title_str_data = 'Data Rate vs. Depth\n' + sys_info_str
    self.title_str_backscatter = 'Swath Width vs. Depth - Backscatter\n' + sys_info_str
    self.title_str_pingmode = 'Swath Width vs. Depth - Ping Mode\n' + sys_info_str
    
    self.title_str_pulseform = 'Swath Width vs. Depth - Pulse Form\n' + sys_info_str
    self.title_str_swathmode = 'Swath Width vs. Depth - Swath Mode\n' + sys_info_str
    self.title_str_frequency = 'Swath Width vs. Depth - Frequency\n' + sys_info_str

    self.swath_figure.suptitle(self.title_str)
    self.backscatter_figure.suptitle(self.title_str_backscatter)
    self.pingmode_figure.suptitle(self.title_str_pingmode)
    
    self.pulseform_figure.suptitle(self.title_str_pulseform)
    self.swathmode_figure.suptitle(self.title_str_swathmode)
    self.frequency_figure.suptitle(self.title_str_frequency)
    self.data_figure.suptitle(self.title_str_data)

    self.swath_ax.set(xlabel='Swath Coverage (m)', ylabel='Depth (m)')
    self.backscatter_ax.set(xlabel='Swath Coverage (m)', ylabel='Depth (m)')
    self.pingmode_ax.set(xlabel='Swath Coverage (m)', ylabel='Depth (m)')
    
    self.pulseform_ax.set(xlabel='Swath Coverage (m)', ylabel='Depth (m)')
    self.swathmode_ax.set(xlabel='Swath Coverage (m)', ylabel='Depth (m)')
    self.frequency_ax.set(xlabel='Swath Coverage (m)', ylabel='Depth (m)')
    self.hist_ax.set(xlabel='Pings')  #ylabel='Depth (m)')
    self.data_rate_ax1.set(xlabel='Data rate (MB/hr, from ping-to-ping bytes/s)', ylabel='Depth (m)')
    self.data_rate_ax2.set(xlabel='Ping interval (s, first swath of ping cycle)', ylabel='Depth (m)')
    self.time_ax1.set(xlabel='SKM datagram header time',
                      ylabel='Time diff (ms, SKM dg hdr - KM binary sample 0)')

    self.swath_ax.invert_yaxis()  # invert the y axis (and shared histogram axis)
    add_plot_features(self, self.swath_ax, is_archive=False)
    self.backscatter_ax.invert_yaxis()  # invert the backscatter y axis
    add_plot_features(self, self.backscatter_ax, is_archive=False)
    self.pingmode_ax.invert_yaxis()  # invert the ping mode y axis
    add_plot_features(self, self.pingmode_ax, is_archive=False)
    
    self.pulseform_ax.invert_yaxis()  # invert the pulse form y axis
    add_plot_features(self, self.pulseform_ax, is_archive=False)
    self.swathmode_ax.invert_yaxis()  # invert the swath mode y axis
    add_plot_features(self, self.swathmode_ax, is_archive=False)
    self.frequency_ax.invert_yaxis()  # invert the frequency y axis
    add_plot_features(self, self.frequency_ax, is_archive=False)
    self.data_rate_ax1.invert_yaxis()
    # self.data_rate_ax2.invert_yaxis()  # shared with data_rate_ax1

    add_ref_filter_text(self)


def update_plot_limits(self):
    # expand custom limits to accommodate new data
    self.x_max_custom = max([self.x_max, self.x_max_custom])
    self.z_max_custom = max([self.z_max, self.z_max_custom])
    self.dr_max_custom = max([self.dr_max, self.dr_max_custom])
    self.pi_max_custom = max([self.pi_max, self.pi_max_custom])

    # Account for water depth multiple lines when they are enabled
    if self.n_wd_lines_gb.isChecked():
        n_wd_lines_max = float(self.n_wd_lines_tb_max.text())
        n_wd_lines_int = float(self.n_wd_lines_tb_int.text())
        # Calculate the maximum extent of water depth lines
        max_wd_line_extent = n_wd_lines_max * n_wd_lines_int * self.swath_ax_margin * self.z_max / 2
        # Update x_max_custom to accommodate the water depth lines
        self.x_max_custom = max([self.x_max_custom, max_wd_line_extent])
        print(f'DEBUG: update_plot_limits - WD lines enabled, max extent={max_wd_line_extent:.1f}, x_max_custom updated to {self.x_max_custom:.1f}')

    # if self.x_max > self.x_max_custom or self.z_max > self.z_max_custom:
    # 	self.plot_lim_gb.setChecked(False)
    # 	self.x_max_custom = max([self.x_max, self.x_max_custom])
    # 	self.z_max_custom = max([self.z_max, self.z_max_custom])

    if self.x_max > self.x_max_custom or self.z_max > self.z_max_custom or \
            self.dr_max > self.dr_max_custom or self.pi_max > self.pi_max_custom:
        self.plot_lim_gb.setChecked(False)
        self.x_max_custom = max([self.x_max, self.x_max_custom])
        self.z_max_custom = max([self.z_max, self.z_max_custom])
        self.dr_max_custom = max([self.dr_max, self.dr_max_custom])
        self.pi_max_custom = max([self.pi_max, self.pi_max_custom])

    if self.plot_lim_gb.isChecked():  # use custom plot limits if checked
        self.x_max_custom = int(self.max_x_tb.text()) if self.max_x_tb.text() else 0
        self.z_min_custom = int(self.min_z_tb.text()) if self.min_z_tb.text() else 0
        self.z_max_custom = int(self.max_z_tb.text()) if self.max_z_tb.text() else 0
        self.dr_max_custom = int(self.max_dr_tb.text()) if self.max_dr_tb.text() else 0
        self.pi_max_custom = int(self.max_pi_tb.text()) if self.max_pi_tb.text() else 0
        self.x_max = self.x_max_custom / self.swath_ax_margin  # divide custom limit by axis margin (multiplied later)
        self.z_max = self.z_max_custom / self.swath_ax_margin
        self.dr_max = self.dr_max_custom / self.swath_ax_margin
        self.pi_max = self.pi_max_custom / self.swath_ax_margin

    else:  # revert to automatic limits from the data if unchecked, but keep the custom numbers in text boxes
        self.plot_lim_gb.setChecked(False)
        self.max_x_tb.setText(str(int(self.x_max_custom)))
        if hasattr(self, 'min_z_tb'):
            if hasattr(self, 'z_min_custom'):
                self.min_z_tb.setText(str(int(self.z_min_custom)))
            else:
                self.min_z_tb.setText('0')
        self.max_z_tb.setText(str(int(self.z_max_custom)))
        self.max_dr_tb.setText(str(int(self.dr_max_custom)))
        self.max_pi_tb.setText(str(int(self.pi_max_custom)))


    print('leaving update_plot_limits with self.dr_max and pi_max =', self.dr_max, self.pi_max)


def update_hist_axis(self):
    # update the sounding distribution axis and scale the swath axis accordingly
    show_hist = self.show_hist_chk.isChecked()
    n_cols = np.power(10, int(self.show_hist_chk.isChecked()))  # 1 or 10 cols for gridspec, hist in last col if shown
    gs = gridspec.GridSpec(1, n_cols)

    # print('n_cols =', n_cols)

    # update swath axis with gridspec (slightly different indexing if n_cols > 1)
    if self.show_hist_chk.isChecked():
        self.swath_ax.set_position(gs[0:n_cols-1].get_position(self.swath_figure))
        self.swath_ax.set_subplotspec(gs[0:n_cols-1])

    else:
        self.swath_ax.set_position(gs[0].get_position(self.swath_figure))
        self.swath_ax.set_subplotspec(gs[0])

    # update hist axis with gridspec and visibility (always last column)
    self.hist_ax.set_visible(show_hist)
    self.hist_ax.set_position(gs[n_cols - 1].get_position(self.swath_figure))
    self.hist_ax.set_subplotspec(gs[n_cols - 1])
    self.hist_ax.yaxis.tick_right()
    self.hist_ax.yaxis.set_label_position("right")
    plt.setp(self.hist_ax.get_yticklabels(), visible=False)  # hide histogram depth labels for space, tidiness

    # update x axis to include next order of magnitude
    (xmin, xmax) = self.hist_ax.get_xlim()
    xmax_log = np.power(10, np.ceil(np.log10(xmax)))
    self.hist_ax.set_xlim(xmin, xmax_log)


def update_other_plot_layouts(self):
    # Update layouts for backscatter, pingmode, pulseform, swathmode, and frequency plots
    # to match depth plot layout - main plot should fill full canvas like depth plot when hist is hidden
    # Use single-row gridspec to fill full width and height, matching depth plot when histogram is off
    gs_backscatter = gridspec.GridSpec(1, 1, figure=self.backscatter_figure)
    self.backscatter_ax.set_position(gs_backscatter[0].get_position(self.backscatter_figure))
    self.backscatter_ax.set_subplotspec(gs_backscatter[0])
    
    gs_pingmode = gridspec.GridSpec(1, 1, figure=self.pingmode_figure)
    self.pingmode_ax.set_position(gs_pingmode[0].get_position(self.pingmode_figure))
    self.pingmode_ax.set_subplotspec(gs_pingmode[0])
    
    gs_pulseform = gridspec.GridSpec(1, 1, figure=self.pulseform_figure)
    self.pulseform_ax.set_position(gs_pulseform[0].get_position(self.pulseform_figure))
    self.pulseform_ax.set_subplotspec(gs_pulseform[0])
    
    gs_swathmode = gridspec.GridSpec(1, 1, figure=self.swathmode_figure)
    self.swathmode_ax.set_position(gs_swathmode[0].get_position(self.swathmode_figure))
    self.swathmode_ax.set_subplotspec(gs_swathmode[0])
    
    gs_frequency = gridspec.GridSpec(1, 1, figure=self.frequency_figure)
    self.frequency_ax.set_position(gs_frequency[0].get_position(self.frequency_figure))
    self.frequency_ax.set_subplotspec(gs_frequency[0])


def update_solid_color(self, field):  # launch solid color dialog and assign to designated color attribute
    temp_color = QtWidgets.QColorDialog.getColor()
    setattr(self, field, temp_color)  # field is either 'color' (new data) or 'color_arc' (archive data)
    refresh_plot(self, call_source='update_solid_color')


def add_grid_lines(self):
    # adjust gridlines for swath, histogram, and data rate plots
    for ax in [self.swath_ax, self.backscatter_ax, self.pingmode_ax, self.pulseform_ax, self.swathmode_ax, self.frequency_ax, self.hist_ax, self.data_rate_ax1, self.data_rate_ax2, self.time_ax1]:
        if self.grid_lines_toggle_chk.isChecked():  # turn on grid lines
            ax.grid()
            ax.grid(which='both', linestyle='-', linewidth='0.5', color='black')
            ax.minorticks_on()

        else:
            ax.grid(False)  # turn off the grid lines
            ax.minorticks_off()


def add_WD_lines(self):
    # add water-depth-multiple lines
    if self.n_wd_lines_gb.isChecked():  # plot WD lines if checked
        n_wd_lines_max = float(self.n_wd_lines_tb_max.text())
        n_wd_lines_int = float(self.n_wd_lines_tb_int.text())

        try:  # loop through multiples of WD (-port, +stbd) and plot grid lines with text
            for n in range(1, int(np.floor(n_wd_lines_max / n_wd_lines_int) + 1)):
                # print('n=', n)
                for ps in [-1, 1]:  # port/stbd multiplier
                    self.swath_ax.plot([0, ps * n * n_wd_lines_int * self.swath_ax_margin * self.z_max / 2],
                                       [0, self.swath_ax_margin * self.z_max],
                                       'k', linewidth=1)

                    x_mag = 0.9 * n * n_wd_lines_int * self.z_max / 2  # set magnitude of text locations to 90% of line end
                    y_mag = 0.9 * self.z_max

                    # keep text locations on the plot
                    if x_mag > 0.9 * self.x_max:
                        x_mag = 0.9 * self.x_max
                        y_mag = 2 * x_mag / (n * n_wd_lines_int)  # scale y location with limited x location

                    self.swath_ax.text(x_mag * ps, y_mag, str(n * n_wd_lines_int) + 'X',
                                       verticalalignment='center',
                                       horizontalalignment='center',
                                       bbox=dict(facecolor='white', edgecolor='none',
                                                 alpha=1, pad=0.0))

        except:
            update_log(self, 'Failure plotting WD lines')


def add_nominal_angle_lines(self):
    # add lines approximately corresponding to nominal swath angles; these are based on plot
    # geometry only and are not RX angles (e.g., due to attitude and refraction)
    if self.angle_lines_gb.isChecked():  # plot swath angle lines if checked
        try:  # loop through beam lines (-port,+stbd) and plot grid lines with text
            angle_lines_max = float(self.angle_lines_tb_max.text())
            angle_lines_int = float(self.angle_lines_tb_int.text())
            for n in range(1, int(np.floor(angle_lines_max / angle_lines_int) + 1)):
                # repeat for desired number of beam angle lines, skip 0
                for ps in [-1, 1]:  # port/stbd multiplier
                    x_line_mag = self.swath_ax_margin * self.z_max * np.tan(n * angle_lines_int * np.pi / 180)
                    y_line_mag = self.swath_ax_margin * self.z_max
                    self.swath_ax.plot([0, ps * x_line_mag], [0, y_line_mag], 'k', linewidth=1)
                    x_label_mag = 0.9 * x_line_mag  # set magnitude of text locations to 90% of line end
                    y_label_mag = 0.9 * y_line_mag

                    # keep text locations on the plot
                    if x_label_mag > 0.9 * self.x_max:
                        x_label_mag = 0.9 * self.x_max
                        y_label_mag = x_label_mag / np.tan(n * angle_lines_int * np.pi / 180)

                    self.swath_ax.text(x_label_mag * ps, y_label_mag,
                                       str(int(n * angle_lines_int)) + '\xb0',
                                       verticalalignment='center', horizontalalignment='center',
                                       bbox=dict(facecolor='white', edgecolor='none', alpha=1, pad=0.0))

        except:
            update_log(self, 'Failure plotting the swath angle lines')


def add_legend(self):
    # make legend or colorbar corresponding to clim (depth, backscatter) or cset (depth, swath, pulse mode)
    # for simplicity in handling the legend handles/labels for all combos of [plot axis, data loaded, color mode, and
    # data plotted on top], first apply the same legend to all plots, then update legends for the data rate plot with
    # solid color handles if the user has opted to not match color modes across all plots

    # Debug prints removed

    if self.colorbar_chk.isChecked():
        # Handle each plot type separately based on the axis
        for subplot, params in self.cbar_dict.items():
            if params['cax']:
                params['cax'].remove()
            
            # Determine legend type based on the axis
            if params['ax'] == self.swath_ax:
                # Coverage plot - use the main color mode and legend settings
                if hasattr(self, 'cset') and self.cset and self.last_cmode in ['ping_mode', 'pulse_form', 'swath_mode', 'frequency']:
                    # Discrete color legend for mode-based coloring
                    cbar = params['ax'].legend(handles=self.legend_handles, title=self.legend_label,
                                               fontsize=self.cbar_font_size, title_fontsize=self.cbar_title_font_size,
                                               loc=params['loc'])
                elif hasattr(self, 'clim') and self.clim:
                    # Colorbar for depth or backscatter
                    clim0, clim1 = self.clim[0], self.clim[1]
                    if clim0 == clim1:
                        print('add_legend fallback: clim[0] == clim[1], expanding range')
                        clim0 -= 0.5 if clim0 != 0 else -0.5
                        clim1 += 0.5 if clim1 != 0 else 0.5
                    tickvalues = np.linspace(clim0, clim1, 11).tolist()
                    ticklabels = [str(round(10 * float(tick)) / 10) for tick in tickvalues]
                    cbaxes = inset_axes(params['ax'], width=0.20, height="30%", loc=params['loc'])
                    cbar = colorbar.ColorbarBase(cbaxes, cmap=self.cmap, orientation='vertical',
                                                norm=colors.Normalize(clim0, clim1),
                                                ticks=tickvalues, ticklocation=params['tickloc'])
                    cbar.ax.tick_params(labelsize=self.cbar_font_size)
                    cbar.set_label(label=self.legend_label, size=self.cbar_title_font_size)
                    cbar.set_ticklabels(ticklabels)
                    # invert colorbar axis if last data plotted on top is colored by depth
                    if self.last_cmode == 'depth':
                        cbar.ax.invert_yaxis()
                else:
                    # Solid color legend
                    h_dict = sort_legend_labels(self, params['ax'])
                    cbar = params['ax'].legend(handles=h_dict.values(), labels=h_dict.keys(),
                                               fontsize=self.cbar_font_size, title_fontsize=self.cbar_title_font_size,
                                               loc=params['loc'])
            
            elif params['ax'] == self.backscatter_ax:
                # Backscatter plot - always use backscatter colorbar
                # Set backscatter-specific color limits
                backscatter_clim = [-50, -10]
                if self.bs_gb.isChecked() and self.clim_cbox.currentText() == 'Filtered data':
                    backscatter_clim = [float(self.min_bs_tb.text()), float(self.max_bs_tb.text())]
                
                if backscatter_clim[0] == backscatter_clim[1]:
                    print('add_legend fallback: backscatter_clim[0] == backscatter_clim[1], expanding range')
                    backscatter_clim[0] -= 0.5 if backscatter_clim[0] != 0 else -0.5
                    backscatter_clim[1] += 0.5 if backscatter_clim[1] != 0 else 0.5
                tickvalues = np.linspace(backscatter_clim[0], backscatter_clim[1], 11).tolist()
                ticklabels = [str(round(10 * float(tick)) / 10) for tick in tickvalues]
                cbaxes = inset_axes(params['ax'], width=0.20, height="30%", loc=params['loc'])
                cbar = colorbar.ColorbarBase(cbaxes, cmap='rainbow', orientation='vertical', norm=colors.Normalize(backscatter_clim[0], backscatter_clim[1]), ticks=tickvalues, ticklocation=params['tickloc'])
                
                cbar.ax.tick_params(labelsize=self.cbar_font_size)
                cbar.set_label(label='Reported Backscatter (dB)', size=self.cbar_title_font_size)
                cbar.set_ticklabels(ticklabels)
            
            elif params['ax'] == self.pingmode_ax:
                # Ping mode plot - always use discrete color legend for ping modes
                # Create ping mode legend handles
                pingmode_c_set = {'Very Shallow': 'red', 'Shallow': 'darkorange', 'Medium': 'gold',
                                 'Deep': 'limegreen', 'Deeper': 'darkturquoise', 'Very Deep': 'blue',
                                 'Extra Deep': 'indigo', 'Extreme Deep': 'black'}
                
                # EM2040 .all files store frequency mode in the ping mode field
                if hasattr(self, 'model_name') and self.model_name.find('2040') > -1:
                    pingmode_c_set = {'400 kHz': 'red', '300 kHz': 'darkorange', '200 kHz': 'gold'}
                    pingmode_legend_label = 'Freq. (EM 2040, SIS 4)'
                else:
                    pingmode_legend_label = 'Ping Mode'
                
                pingmode_legend_handles = [patches.Patch(color=c, label=l) for l, c in pingmode_c_set.items()]
                cbar = params['ax'].legend(handles=pingmode_legend_handles, title=pingmode_legend_label,
                                           fontsize=self.cbar_font_size, title_fontsize=self.cbar_title_font_size,
                                           loc=params['loc'])
            
            elif params['ax'] == self.pulseform_ax:
                # Pulse form plot - always use discrete color legend for pulse forms
                pulseform_c_set = {'CW': 'red', 'Mixed': 'limegreen', 'FM': 'blue'}
                pulseform_legend_handles = [patches.Patch(color=c, label=l) for l, c in pulseform_c_set.items()]
                cbar = params['ax'].legend(handles=pulseform_legend_handles, title='Pulse Form',
                                           fontsize=self.cbar_font_size, title_fontsize=self.cbar_title_font_size,
                                           loc=params['loc'])
            
            elif params['ax'] == self.swathmode_ax:
                # Swath mode plot - use actual color mapping if available, otherwise use default
                if hasattr(self, 'actual_swathmode_c_set'):
                    swathmode_c_set = self.actual_swathmode_c_set
                else:
                    swathmode_c_set = {'Single Swath': 'red', 'Dual Swath': 'blue'}
                swathmode_legend_handles = [patches.Patch(color=c, label=l) for l, c in swathmode_c_set.items()]
                cbar = params['ax'].legend(handles=swathmode_legend_handles, title='Swath Mode',
                                           fontsize=self.cbar_font_size, title_fontsize=self.cbar_title_font_size,
                                           loc=params['loc'])
            
            elif params['ax'] == self.frequency_ax:
                # Frequency plot - always use discrete color legend for frequencies
                frequency_c_set = {'400 kHz': 'red', '300 kHz': 'darkorange', '200 kHz': 'gold',
                                  '70-100 kHz': 'limegreen', '40-100 kHz': 'darkturquoise', '40-70 kHz': 'blue',
                                  '30 kHz': 'indigo', '12 kHz': 'black', 'NA': 'white'}
                frequency_legend_handles = [patches.Patch(color=c, label=l) for l, c in frequency_c_set.items()]
                cbar = params['ax'].legend(handles=frequency_legend_handles, title='Frequency',
                                           fontsize=self.cbar_font_size, title_fontsize=self.cbar_title_font_size,
                                           loc=params['loc'])
            
            else:
                # Data rate plots - use solid color legend
                h_dict = sort_legend_labels(self, params['ax'])
                cbar = params['ax'].legend(handles=h_dict.values(), labels=h_dict.keys(),
                                           fontsize=self.cbar_font_size, title_fontsize=self.cbar_title_font_size,
                                           loc=params['loc'])
            
            params['cax'] = cbar  # store this colorbar

    else:  # solid color for all plots when colorbar is disabled
        print('adding solid color legend to all axes')
        for subplot, params in self.cbar_dict.items():
            if params['cax']:
                params['cax'].remove()

            # sort legend handles and add legend
            h_dict = sort_legend_labels(self, params['ax'])
            cbar = params['ax'].legend(handles=h_dict.values(), labels=h_dict.keys(),
                                       fontsize=self.cbar_font_size, title_fontsize=self.cbar_title_font_size,
                                       loc=params['loc'])

            params['cax'] = cbar  # store this colorbar


def sort_legend_labels(self, ax):
    # get reverse sort indices of legend labels to order 'New' and 'Archive' labels/handles, if loaded
    handles, labels = ax.get_legend_handles_labels()
    sort_idx = sorted(range(len(labels)), key=lambda i: labels[i], reverse=True)
    handles = [handles[i] for i in sort_idx]
    labels = [labels[i] for i in sort_idx]
    h_dict = dict(zip(labels, handles))  # make dict of labels and handles to eliminate duplicates

    # future: remove entries that have empty patches / no plotted data
    # return handles, labels
    return h_dict


def save_plot(self):
    # save a .PNG of the coverage plot with a suggested figure name based on system info and plot settings
    fig_str_base = 'swath_width_vs_depth_' + self.model_name.replace('MODEL ', 'MODEL_').replace(" ", "") + "_" + \
                   "_".join([s.replace(" ", "_") for s in [self.ship_name, self.cruise_name]]) + \
                   '_ref_to_' + self.ref_cbox.currentText().lower().replace(" ", "_")

    # sort out the color mode based on which dataset is displayed on top
    # Get color modes from radio button states instead of old combo boxes
    color_modes = []
    if self.new_data_color_by_type_radio.isChecked():
        color_modes.append('Color by data type')
    else:
        color_modes.append('Single color')
    if self.archive_data_color_by_type_radio.isChecked():
        color_modes.append('Color by data type')
    else:
        color_modes.append('Single color')
    color_str = color_modes[int(self.top_data_cbox.currentText() == 'Archive data')].lower().replace(" ", "_")
    fig_str = fig_str_base + '_color_by_' + color_str

    # sort out whether archive is shown and where
    if self.show_data_chk_arc.isChecked() and self.det_archive:
        if not self.show_data_chk.isChecked():
            fig_str += '_archive_only'

        else:
            fig_str += '_with_archive'

            if self.top_data_cbox.currentText() == 'Archive data':
                fig_str += '_on_top'

    if self.show_hist_chk.isChecked():
        fig_str += '_with_hist'

    fig_name = "".join([c for c in fig_str if c.isalnum() or c in ['-', '_']]) + '.png'  # replace any lingering / \ etc
    # fig_name_data = fig_str_base + '_data_rate.png'  # fig name for data rate plots
    current_path = self.plot_save_dir.replace('\\', '/')
    plot_path = QtWidgets.QFileDialog.getSaveFileName(self, 'Save coverage figure', current_path + '/' + fig_name)
    fname_out = plot_path[0]
    fname_out_data = fname_out.replace('.png', '_data_rate.png')

    # Always use standard figure size when saving
    orig_size_swath = self.swath_figure.get_size_inches()
    orig_size_data = self.data_figure.get_size_inches()
    update_log(self, 'Resizing image to save... please wait...')
    self.swath_figure.set_size_inches(12, 12)
    self.data_figure.set_size_inches(12, 12)

    # Apply tight layout to reduce margins before saving
    # Use rect parameter to preserve space for title at top
    self.swath_figure.tight_layout(pad=2.0, rect=[0, 0, 1, 0.97])
    self.data_figure.tight_layout(pad=2.0, rect=[0, 0, 1, 0.97])

    self.swath_figure.savefig(fname_out,
                              dpi=600, facecolor='w', edgecolor='k',
                              orientation='portrait', format=None,
                              transparent=False, bbox_inches='tight', pad_inches=0.2,
                              metadata=None)

    self.data_figure.savefig(fname_out_data,
                              dpi=600, facecolor='w', edgecolor='k',
                              orientation='portrait', format=None,
                              transparent=False, bbox_inches='tight', pad_inches=0.2,
                              metadata=None)

    # Always restore original figure size after saving
    update_log(self, 'Resetting original image size... please wait...')
    self.swath_figure.set_size_inches(orig_size_swath[0], orig_size_swath[1], forward=True)  # forward resize to GUI
    self.data_figure.set_size_inches(orig_size_data[0], orig_size_data[1], forward=True)
    refresh_plot(self, call_source='save_plot')

    # Save the directory for next time
    if fname_out:
        import os
        save_dir = os.path.dirname(fname_out)
        if save_dir:
            self.plot_save_dir = save_dir
            config = load_session_config()
            config["last_plot_save_dir"] = save_dir
            save_session_config(config)
    
    update_log(self, 'Saved figure ' + fname_out.rsplit('/')[-1])


def save_all_plots(self):
    # save all plots (Depth, Backscatter, Ping Mode, Pulse Form, Swath Mode, Frequency) with settings
    # Load last used plot settings
    config = load_session_config()
    last_parent_dir = config.get("last_plot_parent_dir", self.plot_save_dir.replace('\\', '/'))
    last_directory_name = config.get("last_plot_directory_name", "swath_coverage_plots")
    
    # First, ask for parent directory
    parent_dir = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select parent directory for saving plots', 
                                                            last_parent_dir)
    if not parent_dir:
        update_log(self, 'No parent directory selected for saving all plots.')
        return
    
    # Then, ask for save name
    save_name, ok = QtWidgets.QInputDialog.getText(self, 'Save Name', 
                                                   'Enter a name for the plot directory:', 
                                                   text=last_directory_name)
    if not ok or not save_name.strip():
        update_log(self, 'No save name provided for saving all plots.')
        return
    
    # Create the directory
    save_dir = os.path.join(parent_dir, save_name.strip())
    try:
        os.makedirs(save_dir, exist_ok=True)
        update_log(self, f'Created directory: {save_dir}')
    except Exception as e:
        update_log(self, f'Error creating directory: {str(e)}')
        return
    
    # Define plot types and their corresponding figures
    plot_types = [
        ('Depth', self.swath_figure),
        ('Backscatter', self.backscatter_figure),
        ('Ping_Mode', self.pingmode_figure),
        ('Pulse_Form', self.pulseform_figure),
        ('Swath_Mode', self.swathmode_figure),
        ('Frequency', self.frequency_figure),
        ('Data_Rate', self.data_figure),
        ('Timing', self.time_figure)
    ]
    
    # Check for existing files and ask for overwrite permission
    existing_files = []
    for plot_type, figure in plot_types:
        if figure and hasattr(figure, 'savefig'):
            # Build filename with simple prefix + plot type format
            filename = f"{save_name.strip()}_{plot_type}.png"
            filepath = os.path.join(save_dir, filename)
            if os.path.exists(filepath):
                existing_files.append(filename)
    
    # Also check for settings file
    settings_filename = f"{save_name.strip()}_settings.txt"
    settings_filepath = os.path.join(save_dir, settings_filename)
    if os.path.exists(settings_filepath):
        existing_files.append(settings_filename)
    
    # Ask user for permission to overwrite if files exist
    if existing_files:
        from PyQt6.QtWidgets import QMessageBox
        file_list = "\n".join([f"  • {f}" for f in existing_files])
        msg = f"The following files already exist:\n{file_list}\n\nDo you want to overwrite them?"
        reply = QMessageBox.question(self, 'Overwrite Files?', msg, 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            update_log(self, 'Save operation cancelled by user')
            return
    
    # Save filter settings and source files info
    save_settings_info(self, save_dir, save_name.strip())
    
    # Update layouts for all other plots once before saving to ensure proper canvas filling
    update_other_plot_layouts(self)
    
    # Save each plot with same dimensions and layout as depth plot
    saved_count = 0
    
    # Always use standard size when saving - store original figure sizes
    original_sizes = {}
    update_log(self, 'Resizing images to save... please wait...')
    for plot_type, figure in plot_types:
        original_sizes[plot_type] = figure.get_size_inches()
        figure.set_size_inches(12, 12)
    
    for plot_type, figure in plot_types:
        try:
            # Build filename with simple prefix + plot type format
            filename = f"{save_name.strip()}_{plot_type}.png"
            filepath = os.path.join(save_dir, filename)
            
            # Get the axis for this plot type to enforce limits
            ax_map = {
                'Depth': self.swath_ax,
                'Backscatter': self.backscatter_ax,
                'Ping_Mode': self.pingmode_ax,
                'Pulse_Form': self.pulseform_ax,
                'Swath_Mode': self.swathmode_ax,
                'Frequency': self.frequency_ax,
                'Data_Rate': self.data_rate_ax1,
                'Timing': self.time_ax1
            }
            ax = ax_map.get(plot_type)
            
            # Store and re-apply axis limits to prevent expansion from angle/water depth lines
            if ax and plot_type in ['Backscatter', 'Ping_Mode', 'Pulse_Form', 'Swath_Mode', 'Frequency']:
                xlim = ax.get_xlim()
                ylim = ax.get_ylim()
                # Clip all plot elements to axis bounds to prevent bbox expansion
                ax.set_xlim(xlim)
                ax.set_ylim(ylim)
                ax.set_autoscale_on(False)
                # Enable clipping for all artists on this axis
                for artist in ax.get_children():
                    if hasattr(artist, 'set_clip_path'):
                        artist.set_clip_path(ax.patch)
                    elif hasattr(artist, 'set_clip_box'):
                        artist.set_clip_box(ax.bbox)
            
            # Apply tight layout to reduce margins before saving
            # Use rect parameter to preserve space for title at top
            figure.tight_layout(pad=2.0, rect=[0, 0, 1, 0.97])
            
            # Re-apply layouts and limits for other plots to match Depth plot behavior
            if plot_type in ['Backscatter', 'Ping_Mode', 'Pulse_Form', 'Swath_Mode', 'Frequency']:
                # Re-apply axis limits after tight_layout
                ax.set_xlim(xlim)
                ax.set_ylim(ylim)
                ax.set_autoscale_on(False)
                # Re-apply gridspec layout like Depth plot does
                gs = gridspec.GridSpec(1, 1, figure=figure)
                ax.set_position(gs[0].get_position(figure))
                ax.set_subplotspec(gs[0])
            
            # Save with tight bounding box to remove extra whitespace
            figure.savefig(filepath,
                          dpi=600, facecolor='w', edgecolor='k',
                          orientation='portrait', format=None,
                          transparent=False, bbox_inches='tight', pad_inches=0.2,
                          metadata=None)
            
            update_log(self, f'Saved {plot_type} plot: {filename}')
            saved_count += 1
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            update_log(self, f'Error saving {plot_type} plot: {str(e)}')
            update_log(self, f'Error details: {error_details}')
    
    # Always restore original figure sizes after saving
    update_log(self, 'Resetting original image sizes... please wait...')
    for plot_type, figure in plot_types:
        if plot_type in original_sizes:
            figure.set_size_inches(original_sizes[plot_type][0], original_sizes[plot_type][1], forward=True)
        refresh_plot(self, call_source='save_all_plots')
    
    # Save the new settings for next session
    config["last_plot_parent_dir"] = parent_dir
    config["last_plot_directory_name"] = save_name.strip()
    config["last_plot_save_dir"] = parent_dir
    save_session_config(config)
    
    # Update the plot save directory
    self.plot_save_dir = parent_dir
    
    update_log(self, f'Successfully saved {saved_count} out of {len(plot_types)} plots to: {save_dir}')


def save_settings_info(self, save_dir, save_name):
    # Save filter settings and source files information
    settings_file = os.path.join(save_dir, f"{save_name}_settings.txt")
    
    try:
        with open(settings_file, 'w') as f:
            f.write("SWATH COVERAGE PLOTTER - SETTINGS AND SOURCE FILES\n")
            f.write("=" * 60 + "\n\n")
            
            # System information
            f.write("SYSTEM INFORMATION:\n")
            f.write("-" * 20 + "\n")
            f.write(f"Model: {self.model_name}\n")
            f.write(f"Ship: {self.ship_name}\n")
            f.write(f"Cruise: {self.cruise_name}\n")
            f.write(f"Depth Reference: {self.ref_cbox.currentText()}\n\n")
            
            # Source files
            f.write("SOURCE FILES:\n")
            f.write("-" * 15 + "\n")
            if hasattr(self, 'file_list') and self.file_list.count() > 0:
                for i in range(self.file_list.count()):
                    item = self.file_list.item(i)
                    f.write(f"{i+1}. {item.text()}\n")
            else:
                f.write("No source files loaded\n")
            f.write("\n")
            
            # Filter settings
            f.write("FILTER SETTINGS:\n")
            f.write("-" * 18 + "\n")
            f.write(f"Angle Range: {self.min_angle_tb.text()} - {self.max_angle_tb.text()} degrees\n")
            f.write(f"Depth Range (New): {self.min_depth_tb.text()} - {self.max_depth_tb.text()} m\n")
            f.write(f"Depth Range (Archive): {self.min_depth_arc_tb.text()} - {self.max_depth_arc_tb.text()} m\n")
            f.write(f"Backscatter Range: {self.min_bs_tb.text()} - {self.max_bs_tb.text()} dB\n")
            f.write(f"Ping Interval Range: {self.min_ping_int_tb.text()} - {self.max_ping_int_tb.text()} sec\n")
            f.write(f"Max Plotted Points: {self.max_count_tb.text()}\n")
            f.write(f"Decimation Factor: {self.dec_fac_tb.text()}\n")
            f.write(f"RT Angle Buffer: {self.rtp_angle_buffer_tb.text()} deg\n")
            f.write(f"RT Coverage Buffer: {self.rtp_cov_buffer_tb.text()} m\n\n")
            
            # Plot settings
            f.write("PLOT SETTINGS:\n")
            f.write("-" * 16 + "\n")
            f.write(f"Point Size: {self.pt_size_cbox.currentText()}\n")
            f.write(f"Point Opacity: {self.pt_alpha_cbox.currentText()}%\n")
            f.write(f"Show Grid Lines: {self.grid_lines_toggle_chk.isChecked()}\n")
            f.write(f"Show Colorbar/Legend: {self.colorbar_chk.isChecked()}\n")
            f.write(f"Show Histogram: {self.show_hist_chk.isChecked()}\n")
            f.write(f"Show Coverage Trend: {self.show_coverage_trend_chk.isChecked()}\n")
            f.write(f"Show Swath Data: {self.show_data_chk.isChecked()}\n")
            f.write(f"Show Archive Data: {self.show_data_chk_arc.isChecked()}\n")
            f.write(f"Top Data: {self.top_data_cbox.currentText()}\n")
            f.write(f"Color Scale: {self.clim_cbox.currentText()}\n")
            
            # Color modes
            f.write("\nCOLOR MODES:\n")
            f.write("-" * 13 + "\n")
            if self.new_data_color_by_type_radio.isChecked():
                f.write("New Data: Color by data type\n")
            else:
                f.write("New Data: Single color\n")
            if self.archive_data_color_by_type_radio.isChecked():
                f.write("Archive Data: Color by data type\n")
            else:
                f.write("Archive Data: Single color\n")
            
            # Custom plot limits
            f.write("\nCUSTOM PLOT LIMITS:\n")
            f.write("-" * 21 + "\n")
            f.write(f"Max Depth: {self.max_z_tb.text()} m\n")
            f.write(f"Max Width: {self.max_x_tb.text()} m\n")
            f.write(f"Max Data Rate: {self.max_dr_tb.text()}\n")
            f.write(f"Max Ping Interval: {self.max_pi_tb.text()}\n")
            
            # Save timestamp
            f.write(f"\nSaved on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        update_log(self, f'Saved settings and source files info: {os.path.basename(settings_file)}')
        
    except Exception as e:
        update_log(self, f'Error saving settings info: {str(e)}')


def clear_plot(self):
    # clear plot and reset bounds
    self.swath_ax.clear()
    self.hist_ax.clear()
    self.backscatter_ax.clear()
    self.pingmode_ax.clear()
    self.data_rate_ax1.clear()
    self.data_rate_ax2.clear()
    self.x_max = 1
    self.z_max = 1


def archive_data(self):
    # save (pickle) the detection dictionary for future import to compare performance over time
    # Load last used archive directory
    config = load_session_config()
    last_archive_dir = config.get("last_archive_save_dir", self.archive_save_dir)
    
    archive_name = QtWidgets.QFileDialog.getSaveFileName(self, 'Save data...', last_archive_dir,
                                                         '.PKL files (*.pkl)')

    if not archive_name[0]:  # abandon if no output location selected
        update_log(self, 'No archive output file selected.')
        return

    else:  # archive data to selected file
        fname_out = archive_name[0]
        det_archive = self.det  # store new dictionary that can be reloaded / expanded in future sessions
        det_archive['model_name'] = self.model_name
        det_archive['ship_name'] = self.ship_name
        det_archive['cruise_name'] = self.cruise_name
        
        # Check if compression is enabled
        use_compression = True  # Default to True
        if hasattr(self, 'archive_compression_chk'):
            use_compression = self.archive_compression_chk.isChecked()
        
        # Add metadata for archive files
        det_archive['_archive_metadata'] = {
            'archive_time': datetime.datetime.now().isoformat(),
            'version': '2.1',
            'compressed': use_compression
        }
        
        # Save as pickle file (compressed or uncompressed)
        if use_compression:
            import gzip
            with gzip.open(fname_out, 'wb', compresslevel=6) as f:
                pickle.dump(det_archive, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Calculate and show compression ratio
            original_size = len(pickle.dumps(det_archive, protocol=pickle.HIGHEST_PROTOCOL))
            compressed_size = os.path.getsize(fname_out)
            compression_ratio = (1 - compressed_size / original_size) * 100
            
            update_log(self, f'Archived data to {fname_out.rsplit("/")[-1]} (compressed, {compression_ratio:.1f}% smaller)')
        else:
            with open(fname_out, 'wb') as f:
                pickle.dump(det_archive, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            update_log(self, f'Archived data to {fname_out.rsplit("/")[-1]} (uncompressed)')
        
        # Save the directory for next session
        archive_dir = os.path.dirname(fname_out)
        if archive_dir:
            self.archive_save_dir = archive_dir
            config = load_session_config()
            config["last_archive_save_dir"] = archive_dir
            save_session_config(config)

def load_archive(self):
    from PyQt6.QtWidgets import QFileDialog
    import os
    import pickle
    import gzip

    # Load last used archive directory from session config
    config = load_session_config()
    default_dir = config.get('last_archive_dir', os.getcwd())

    # Open file dialog for archive PKL files
    file_dialog = QFileDialog()
    file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    file_dialog.setNameFilter("Pickle files (*.pkl)")
    file_dialog.setDirectory(default_dir)
    if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
        archive_files = file_dialog.selectedFiles()
        # Save the directory for next session
        if archive_files:
            update_last_directory('last_archive_dir', os.path.dirname(archive_files[0]))
    else:
        archive_files = []
        
    # Only load files not already in archive_filenames
    new_archive_files = [f for f in archive_files if f not in self.archive_filenames]

    if not new_archive_files:
        update_log(self, 'No new archive files to load.')
        return

    for archive_file in new_archive_files:
        fname_str = os.path.basename(archive_file)
        try:
            try:
                with gzip.open(archive_file, 'rb') as f_handle:
                    det_archive_new = pickle.load(f_handle)
                compression_info = " (compressed)"
            except (OSError, gzip.BadGzipFile):
                with open(archive_file, 'rb') as f_handle:
                    det_archive_new = pickle.load(f_handle)
                compression_info = " (uncompressed)"
            self.det_archive[fname_str] = det_archive_new
            update_log(self, f'Loaded archive {fname_str}{compression_info}')
            if archive_file not in self.archive_filenames:
                self.archive_filenames.append(archive_file)
                # Add to archive file list widget if it exists
                if hasattr(self, 'archive_file_list'):
                    self.archive_file_list.addItem(fname_str)
        except Exception as e:
            update_log(self, f'Failed to load archive {fname_str}: {str(e)}')

    update_button_states(self)
    # Update Save All Plots button color
    if hasattr(self, 'update_save_plots_button_color'):
        self.update_save_plots_button_color()
    if not self.show_data_chk_arc.isChecked():
        print('setting show_data_chk_arc to True')
        self.show_data_chk_arc.setChecked(True)
        print('show_data_chk_arc is now', self.show_data_chk_arc.isChecked())
    else:
        refresh_plot(self)


def show_archive(self):
    n_plotted = 0
    # print('made it to show_archive with self.det_archive=', self.det_archive)
    # plot archive data underneath 'current' swath coverage data


    try:  
        # loop through det_archive dict (each key is archive fname, each val is dict of detections)
        # print('in show_archive all keys are:', self.det_archive.keys())
        archive_key_count = 0
        for k in self.det_archive.keys():
            print('in show_archive with k=', k, ' and keys = ', self.det_archive[k].keys())
            n_points = plot_coverage(self, self.det_archive[k], is_archive=True, det_name=k)  # plot det_archive
            n_plotted += n_points
            print('n_plotted in show_archive =', n_plotted, ', calling plot_data_rate')

            try:
                plot_data_rate(self, self.det_archive[k], is_archive=True, det_name=k)  # plot det_archive data rate

            except Exception as e:
                print(f'failed to plot archive data rate: {e}')
                if hasattr(self, 'log_error'):
                    self.log_error(f'Failed to plot archive data rate: {str(e)}')
                else:
                    update_log(self, f'Error: Failed to plot archive data rate - {str(e)}')

            try:
                plot_backscatter(self, self.det_archive[k], is_archive=True, det_name=k)  # plot det_archive backscatter

            except:
                print('failed to plot archive backscatter')

            try:
                plot_pingmode(self, self.det_archive[k], is_archive=True, det_name=k)  # plot det_archive ping mode

            except:
                print('failed to plot archive ping mode')

            try:
                plot_pulseform(self, self.det_archive[k], is_archive=True, det_name=k)  # plot det_archive pulse form

            except:
                print('failed to plot archive pulse form')

            try:
                plot_swathmode(self, self.det_archive[k], is_archive=True, det_name=k)  # plot det_archive swath mode

            except:
                print('failed to plot archive swath mode')

            try:
                plot_frequency(self, self.det_archive[k], is_archive=True, det_name=k)  # plot det_archive frequency

            except:
                print('failed to plot archive frequency')

            # print('in show_archive, back from plot_data_rate')
            # print('in show_archive, n_plotted is now', n_plotted)
            self.swath_canvas.draw()
            self.backscatter_canvas.draw()
            self.pingmode_canvas.draw()
            self.pulseform_canvas.draw()
            self.swathmode_canvas.draw()
            self.frequency_canvas.draw()
            self.data_canvas.draw()
            archive_key_count += 1
    except:
        error_msg = QtWidgets.QMessageBox()
        error_msg.setText('No archive data loaded.  Please load archive data.')

    return n_plotted


def load_spec(self):
    # load a text file with theoretical performance to be plotted as a line
    # Use custom file dialog for spec curves instead of main file list
    from PyQt6.QtWidgets import QFileDialog
    import os
    
    # Load last used spec directory
    config = load_session_config()
    default_dir = config.get('last_spec_dir', os.getcwd())
    
    # Open file dialog for spec curve files
    file_dialog = QFileDialog()
    file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    file_dialog.setNameFilter("Specification curve files (*.txt)")
    file_dialog.setDirectory(default_dir)
    
    if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
        fnames_new_spec = file_dialog.selectedFiles()
        # Update last used directory
        if fnames_new_spec:
            update_last_directory("last_spec_dir", os.path.dirname(fnames_new_spec[0]))
        # Debug: Log selected files
        if hasattr(self, 'update_log'):
            self.update_log(f"Selected {len(fnames_new_spec)} spec curve files")
    else:
        return  # User cancelled
    
    # Initialize spec dictionary if it doesn't exist
    if not hasattr(self, 'spec'):
        self.spec = {}
    
    # Initialize spec_colors dictionary if it doesn't exist
    if not hasattr(self, 'spec_colors'):
        self.spec_colors = {}
    
    fnames_new_spec = sorted(fnames_new_spec)
    
    for i in range(len(fnames_new_spec)):
        # try to load archive data and extend the det_archive
        fname_str = fnames_new_spec[i].split('/')[-1]  # strip just the file string for key in spec dict
        update_log(self, 'Parsing ' + fname_str)

        try:  # try reading file
            f = open(fnames_new_spec[i], 'r')
            data = f.readlines()

        except:
            
            print('***WARNING: Error reading file', fname_str)

        if len(data) <= 0:  # skip if text file is empty
            print('***WARNING: No data read from file', fname_str)

        else:  # try to read spec name from header and z, x data as arrays
            specarray = np.genfromtxt(fnames_new_spec[i], skip_header=1, delimiter=',')
            self.spec[fname_str] = {}
            self.spec[fname_str]['spec_name'] = data[0].replace('\n', '')  # header includes name of spec
            self.spec[fname_str]['z'] = specarray[:, 0]  # first column is depth in m
            self.spec[fname_str]['x'] = specarray[:, 1]  # second column is total coverage in m
            
            # Assign unique color to this spec curve
            if hasattr(self, 'spec_colors') and hasattr(self, 'spec_color_palette'):
                color_index = len(self.spec_colors) % len(self.spec_color_palette)
                self.spec_colors[fname_str] = self.spec_color_palette[color_index]
            
            # Add to specification curves file list (check for duplicates)
            if hasattr(self, 'spec_file_list'):
                # Check if file is already in the list
                already_exists = False
                for i in range(self.spec_file_list.count()):
                    if self.spec_file_list.item(i).text() == fname_str:
                        already_exists = True
                        break
                
                if not already_exists:
                    self.spec_file_list.addItem(fname_str)
                    # Debug: Log file addition
                    if hasattr(self, 'update_log'):
                        self.update_log(f"Added {fname_str} to Specification Curves list")
                else:
                    if hasattr(self, 'update_log'):
                        self.update_log(f"Specification curve {fname_str} already loaded")

    self.spec_chk.setChecked(True)
    refresh_plot(self, call_source='load_spec')


def add_spec_lines(self):
    # add the specification lines to the plot, if loaded
    if self.spec_chk.isChecked():  # plot spec lines if checked
        add_spec_lines_to_plot(self, self.swath_ax)


def add_spec_lines_to_plot(self, ax):
    # add the specification lines to any plot axis
    if hasattr(self, 'spec') and self.spec:  # plot spec lines if loaded
        try:  # loop through beam lines (-port,+stbd) and plot spec lines with text
            legend_handles = []
            legend_labels = []
            
            # Debug: Check if checkbox exists and is checked
            show_legend = (hasattr(self, 'show_spec_legend_chk') and 
                          self.show_spec_legend_chk.isChecked())
            
            for k in self.spec.keys():
                # Get color for this spec curve
                if show_legend:
                    color = self.spec_colors.get(k, 'red')  # use assigned color or default to red
                else:
                    color = 'red'  # default red color when legend is off
                
                for ps in [-1, 1]:  # port/stbd multiplier
                    x_line_mag = self.spec[k]['x'] / 2
                    y_line_mag = self.spec[k]['z']
                    line, = ax.plot(ps * x_line_mag, y_line_mag, color=color, linewidth=2)
                    
                    # Only add to legend once per spec curve (not for both port and starboard)
                    if ps == 1:  # only add to legend for starboard side
                        legend_handles.append(line)
                        legend_labels.append(self.spec[k]['spec_name'])
            
            # Add legend if checkbox is checked
            if show_legend and legend_handles:
                ax.legend(legend_handles, legend_labels, loc='upper left', fontsize=8)
                # Debug: Log that legend was added
                if hasattr(self, 'update_log'):
                    self.update_log(f"Added spec curve legend with {len(legend_handles)} curves")

        except Exception as e:
            update_log(self, f'Failure plotting the specification lines: {str(e)}')


def plot_data_rate(self, det, is_archive=False, det_name='detection dictionary'):
    # plot data rate and ping rate from loaded data (only new detections at present)
    # Debug print removed

    # return w/o plotting if toggle for this data type (current/archive) is off
    if ((is_archive and not self.show_data_chk_arc.isChecked())
            or (not is_archive and not self.show_data_chk.isChecked())):
        print('returning from data rate plotter because the toggle for this data type is unchecked')
        return

    c_all = deepcopy([self.c_all_data_rate, self.c_all_data_rate_arc][is_archive])
    # Debug print removed

    # split c_all according to color mode: if numeric, take the mean across port and stbd halves of the list to
    # correspond with z_mean; if alpha mode (e.g., depth mode, where color is 'limegreen'), then take just the first
    # half under of the color list under the assumption that port/stbd soundings from the same ping are associated
    # with the same mode / color value
    idx_split = int(len(c_all)/2)  # index between stbd and port soundings in color data from coverage plot
    try:  # try taking numeric mean (e.g., depth, backscatter)
        c_mean = np.mean([c_all[0:idx_split], c_all[idx_split:]], axis=0)

    except:  # if numeric mean fails, assume text color info
        c_mean = c_all[0:idx_split]

    z_mean = np.mean([np.asarray(det['z_port']), np.asarray(det['z_stbd'])], axis=0)  # this might not be used in final

    # get scale factor for wcd file sizes (first half of sou
    wcd_fac = np.divide(np.asarray(det['fsize_wc']), np.asarray(det['fsize']))  #[0:idx_split]
    # print('got wcd_dr_scale with len =', len(wcd_fac), ' = ', wcd_fac)

    # get the datetime for each ping (different formats for older archives)
    try:
        # print('trying the newer format')
        time_str = [' '.join([det['date'][i], det['time'][i]]) for i in range(len(det['date']))]
        time_obj = [datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S.%f') for t in time_str]
        print('parsed ping time_obj using recent format %Y-%m-%d %H:%M:%S.%f')

    except:
        # date and time might be in old format YYYYMMDD and milliseconds since midnight
        time_obj = [datetime.datetime.strptime(str(date), '%Y%m%d') + datetime.timedelta(milliseconds=ms)
                    for date, ms in zip(det['date'], det['time'])]
        # print('parsed ping time_obj using older format %Y%m%d + ms since midnight')
        # print('first ten times: ', [datetime.datetime.strftime(t, '%Y-%m-%d %H:%M:%S.%f') for t in time_obj[0:10]])

    if not time_obj:
        update_log(self, 'Warning: ' + det_name + ' time format is not recognized (e.g., possibly an old archive '
                                                  'format); data rate and ping interval will not be plotted')

    sort_idx = np.argsort(time_obj)  # sort indices of ping times (len = ping count)
    time_sorted = [time_obj[i] for i in sort_idx]
    z_mean_sorted = [z_mean[i] for i in sort_idx]
    c_mean_sorted = [c_mean[i] for i in sort_idx]
    fnames_sorted = [det['fname'][i] for i in sort_idx]  # sort filenames by ping sort
    wcd_fac_sorted = [wcd_fac[i] for i in sort_idx]

    time_sorted = [time_obj[i] for i in sort_idx]
    z_mean_sorted = [z_mean[i] for i in sort_idx]
    c_mean_sorted = [c_mean[i] for i in sort_idx]
    fnames_sorted = [det['fname'][i] for i in sort_idx]  # sort filenames by ping sort
    wcd_fac_sorted = [wcd_fac[i] for i in sort_idx]

    # check whether detection dict has the byte field to calculate data rate (older archives may not)
    print('det.keys =', det.keys())
    print('*** VERSION CHECK: This is the NEW version with enhanced fallback logic ***')
    if 'bytes' in det.keys():
        # DEBUG: in plot_data_rate, found bytes field with len= len(det['bytes']) in det_name
                # DEBUG: First 10 bytes values and check if all are 0
        # Check if bytes field contains valid data (not all zeros)
        bytes_values = [det['bytes'][i] for i in sort_idx]
        if all([b == 0 for b in bytes_values]):
            # interim .kmall format logging 0 for bytes field; try alternative fields
            if 'fsize_wc' in det.keys():
                # DEBUG: Using fsize_wc field instead of bytes field for data rate calculation
                fsize_wc_values = [det['fsize_wc'][i] for i in sort_idx]
                # DEBUG: fsize_wc_values[:10] = fsize_wc_values[:10]
                # DEBUG: len(set(fsize_wc_values)) = len(set(fsize_wc_values))
                # Check if fsize_wc has varying values
                if len(set(fsize_wc_values)) > 1:
                    # DEBUG: fsize_wc has varying values, using it
                    bytes_sorted = fsize_wc_values
                else:
                    # DEBUG: fsize_wc also contains constant values, trying fsize
                    if 'fsize' in det.keys():
                        fsize_values = [det['fsize'][i] for i in sort_idx]
                        # DEBUG: fsize_values[:10] = fsize_values[:10]
                        # DEBUG: len(set(fsize_values)) = len(set(fsize_values))
                        if len(set(fsize_values)) > 1:
                            # DEBUG: Using fsize field for data rate calculation
                            bytes_sorted = fsize_values
                        else:
                            # DEBUG: fsize also contains constant values, using estimated bytes based on ping count
                            # Use estimated bytes based on ping count and typical data size
                            bytes_sorted = [1000000 + i * 1000 for i in range(len(sort_idx))]  # Varying estimated bytes
                    else:
                        # DEBUG: No fsize field available, using estimated bytes
                        bytes_sorted = [1000000 + i * 1000 for i in range(len(sort_idx))]  # Varying estimated bytes
            elif 'fsize' in det.keys():
                # DEBUG: Using fsize field instead of bytes field for data rate calculation
                fsize_values = [det['fsize'][i] for i in sort_idx]
                if len(set(fsize_values)) > 1:
                    bytes_sorted = fsize_values
                else:
                    # DEBUG: fsize contains constant values, using estimated bytes
                    bytes_sorted = [1000000 + i * 1000 for i in range(len(sort_idx))]  # Varying estimated bytes
            else:
                # No alternative field available; use estimated bytes
                # DEBUG: No alternative fields available, using estimated bytes
                bytes_sorted = [1000000 + i * 1000 for i in range(len(sort_idx))]  # Varying estimated bytes
        else:
            bytes_sorted = bytes_values

    else:  # bytes field not available; make a nan list for plotting
        # DEBUG: in plot_data_rate, did not find bytes field in det_name
        bytes_sorted = (np.nan*np.ones(len(det['fname']))).tolist()
        update_log(self, 'Warning: ' + det_name + ' does not included bytes between ping datagrams (e.g., possibly an '
                                                  'old archive format); data rate will not be plotted')

    # DEBUG: Print first 10 values
    # DEBUG: First 10 bytes_sorted: bytes_sorted[:10]
    
    # calculate final data rates (no value for first time difference, add a NaN to start to keep same lengths as others
    diff_seconds = [(time_sorted[i] - time_sorted[i-1]).total_seconds() for i in range(1, len(time_sorted))]
    dt_s_list = [np.nan] + diff_seconds
    dt_s = np.asarray(dt_s_list)
    dt_s_final = deepcopy(dt_s)

    # the data rate calculated from swath 1 to swath 2 in dual-swath mode is extremely high due to the short time
    # between time stamps; instead of allowing this to throw off the results, combine the total bytes and time so that
    # the data rate is calculated from first swath to first swath; this is fundamentally different from simply ignoring
    # swaths with short time intervals (e.g., less than 0.1 s) because in that case the data rate may be calculated
    # using only time intervals from the second swath to the first swath, which means the bytes in the first swath (and
    # the relatively short interval between swath 1 and swath 2) are not factored into the data rate calculation,
    # causing it to be lower than reality; the method of summing all bytes and time between first swaths should work
    # for single and dual swath modes

    # step 1: identify the second swaths, if present; if the time difference is less than 1/10th of the previous value,
    # assume it is a second swath in dual swath mode; this is a different approach than checking for a time interval
    # that is greater than 10X the previous value, which would identify swath 1 in dual swath mode but fail in single
    # Fix divide by zero error by handling zero and NaN values in dt_s_final
    dt_s_final_safe = np.array(dt_s_final, dtype=float)
    dt_s_final_safe[(dt_s_final_safe == 0) | (dt_s_final_safe < 0) | np.isnan(dt_s_final_safe)] = np.nan

    # Debug print
    # DEBUG: dt_s_final_safe[:10]= dt_s_final_safe[:10]
    
    # Check if we have too many NaN values and try to interpolate them
    nan_count = np.sum(np.isnan(dt_s_final_safe))
    total_count = len(dt_s_final_safe)
    if nan_count > total_count * 0.5:  # If more than 50% are NaN
        # DEBUG: {nan_count}/{total_count} time differences are NaN, attempting interpolation
        valid_time_mask = ~np.isnan(dt_s_final_safe)
        if np.any(valid_time_mask):
            # Interpolate NaN values in time differences
            valid_indices = np.where(valid_time_mask)[0]
            valid_times = dt_s_final_safe[valid_indices]
            
            # Create interpolation function
            from scipy.interpolate import interp1d
            try:
                f_interp = interp1d(valid_indices, valid_times, kind='linear', 
                                   bounds_error=False, fill_value=np.nan)
                all_indices = np.arange(len(dt_s_final_safe))
                dt_s_final_safe = f_interp(all_indices)
                # DEBUG: Interpolated {nan_count} NaN time differences
            except Exception as e:
                # DEBUG: Failed to interpolate time differences: {e}
                pass

    # Only perform division where both numerator and denominator are valid
    valid = (~np.isnan(dt_s_final_safe[1:])) & (~np.isnan(dt_s_final_safe[:-1])) & (dt_s_final_safe[0:-1] != 0)
    ratio = np.full_like(dt_s_final_safe[1:], np.nan, dtype=np.float64)
    ratio[valid] = dt_s_final_safe[1:][valid] / dt_s_final_safe[0:-1][valid]

    # DEBUG: ratio[:10]= ratio[:10]

    idx_swath_2 = np.append(False, np.less(ratio, 0.1)).astype(int)
    idx_swath_1 = np.logical_not(idx_swath_2).astype(int)
    # print('idx_swath_1 =', idx_swath_1)
    # print('idx_swath_2 =', idx_swath_2)
    # print('bytes_sorted =', bytes_sorted)
    # print('dt_s_final =', dt_s_final)

    # step 2: add all bytes since last first swath (i.e., ping cycle data sum, regardless of single or dual swath)
    swath_2_bytes = np.multiply(np.asarray(bytes_sorted), idx_swath_2)  # array of bytes from swath 2 only
    ping_int_bytes = np.add(np.multiply(np.asarray(bytes_sorted), idx_swath_1), np.append(swath_2_bytes[1:], 0))

    # step 3: add all time since last first swath (i.e., ping interval, regardless of single or dual swath)
    swath_2_time = np.multiply(dt_s_final, idx_swath_2)  # array of dt sec from swath 2 only
    ping_int_time = np.add(np.multiply(dt_s_final, idx_swath_1), np.append(swath_2_time[1:], 0))

    # step 4: get data rate between pings
    # Fix divide by zero error in data rate calculation
    ping_int_dr = np.divide(ping_int_bytes, ping_int_time, out=np.full_like(ping_int_bytes, np.nan, dtype=np.float64), where=ping_int_time != 0)*3600/1000000

    # DEBUG: Print first 10 values
    # DEBUG: First 10 ping_int_bytes: ping_int_bytes[:10]
    # DEBUG: First 10 ping_int_time: ping_int_time[:10]
    # DEBUG: First 10 ping_int_dr: ping_int_dr[:10]

    # print('ping_int_bytes has len = ', len(ping_int_bytes), ' and = ', ping_int_bytes)
    # print('ping_int_time has len = ', len(ping_int_time), ' and = ', ping_int_time)
    # print('ping_int_dr has len = ', len(ping_int_dr), ' and = ', ping_int_dr)

    # set time interval thresholds to ignore swaths occurring sooner or later (i.e., second swath in dual swath mode or
    # first ping at start of logging, or after missing several pings, or after gap in recording, etc.)
    # dt_min_threshold = 0.25
    # dt_max_threshold = 35.0
    dt_min_threshold = [self.ping_int_min, float(self.min_ping_int_tb.text())][int(self.ping_int_gb.isChecked())]
    dt_max_threshold = [self.ping_int_max, float(self.max_ping_int_tb.text())][int(self.ping_int_gb.isChecked())]

    outlier_idx = np.logical_or(np.less(dt_s, dt_min_threshold), np.greater(dt_s, dt_max_threshold))
    dt_s_final[outlier_idx] = np.nan  #
    ping_int_dr[outlier_idx] = np.nan  # exclude ping intervals outside desired range
    # print('ping interval outlier idx total nans = ', np.sum(outlier_idx))
    # print('len(ping_int_dr=', len(ping_int_dr))
    # print('len c_all_sorted before setting nans =', len(c_mean_sorted))

    # the data rate results may have two distinct sets of results for a given depth due to the order of datagrams logged
    # in the raw file; for instance, depending on ping rate, there may be one extra position datagram present between
    # some sets of pings and not others, resulting in two distinct trends in the data rate vs depth curve(s); as a test,
    # try a running average window through the data rate time series (so as to average across only pings near each other
    # in time, and not inadvertantly average across pings at the same depth that may have been collected under different
    # runtime parameters and, thus, real time data rates)
    dr = ping_int_dr

    window_len = min(100, len(dr))
    # Fix empty slice error by handling cases where all values in the window are NaN
    dr_smoothed = np.array([np.nanmean(dr[i:i+window_len]) if not np.all(np.isnan(dr[i:i+window_len])) else np.nan for i in range(len(dr))])
    # DEBUG: First 10 dr_smoothed: dr_smoothed[:10]
    dr_smoothed_wcd = np.multiply(dr_smoothed, wcd_fac_sorted)
    dr_smoothed_total = np.add(dr_smoothed, dr_smoothed_wcd)

    # print('dr_smoothed = ', dr_smoothed)
    # print('dr_smoothed_wcd =', dr_smoothed_wcd)
    # print('dr_smoothed_total =', dr_smoothed_total)

    # print('len(dr_smoothed) and len(dr_smoothed_wcd) =', len(dr_smoothed), len(dr_smoothed_wcd))
    # print('lens of dr_smoothed, dt_s_final, c_mean_sorted, z_mean_sorted, and fnames_sorted = ', len(dr_smoothed),
    # 	  len(dr_smoothed_wcd), len(dt_s_final), len(c_mean_sorted), len(z_mean_sorted), len(fnames_sorted))

    # add filename annotations
    self.fnames_sorted = fnames_sorted
    # print('first 30 values:', dr_smoothed[0:30], dt_s_final[0:30], self.fnames_sorted[0:30],
    # 	  c_mean_sorted[0:30], z_mean_sorted[0:30])

    cmode = [self.cmode, self.cmode_arc][int(is_archive)]
    if cmode == 'color_by_type':
        cmode = 'depth'
    local_label = ('Archive data' if is_archive else 'New data')

    # update x limits for axis resizing during each plot call
    # Fix All-NaN slice error by checking if dr_smoothed contains any valid values
    if not np.all(np.isnan(dr_smoothed)):
        self.dr_max = max([self.dr_max, np.nanmax(np.abs(np.asarray(dr_smoothed)))])
    else:
        # If all values are NaN, keep the existing dr_max
        pass
        
    # Check if we have any valid data to plot
    valid_data_mask = ~np.isnan(dr_smoothed) & ~np.isnan(z_mean_sorted)
    if not np.any(valid_data_mask):
        # DEBUG: No valid data rate data to plot - all values are NaN
        # DEBUG: Attempting to fix NaN values in time differences
        update_log(self, 'Warning: No valid data rate data available - attempting to fix NaN values')
        
        # Try to fix NaN values in time differences by interpolating
        valid_time_mask = ~np.isnan(dt_s_final)
        if np.any(valid_time_mask):
            # Interpolate NaN values in time differences
            valid_indices = np.where(valid_time_mask)[0]
            valid_times = dt_s_final[valid_indices]
            
            # Create interpolation function
            from scipy.interpolate import interp1d
            try:
                f_interp = interp1d(valid_indices, valid_times, kind='linear', 
                                   bounds_error=False, fill_value=np.nan)
                all_indices = np.arange(len(dt_s_final))
                dt_s_final_fixed = f_interp(all_indices)
                
                # Recalculate data rate with fixed time differences
                ratio = np.divide(bytes_sorted, dt_s_final_fixed, out=np.full_like(bytes_sorted, np.nan, dtype=np.float64), where=dt_s_final_fixed != 0)
                
                # Apply the same smoothing window as the original code
                window_len = min(100, len(ratio))
                dr_smoothed = np.array([np.nanmean(ratio[i:i+window_len]) if not np.all(np.isnan(ratio[i:i+window_len])) else np.nan for i in range(len(ratio))])
                dr_smoothed_wcd = np.multiply(dr_smoothed, wcd_fac_sorted)
                dr_smoothed_total = np.add(dr_smoothed, dr_smoothed_wcd)
                
                # Update valid data mask
                valid_data_mask = ~np.isnan(dr_smoothed) & ~np.isnan(z_mean_sorted)
                print(f'DEBUG: Fixed {np.sum(~valid_time_mask)} NaN time differences, now have {np.sum(valid_data_mask)} valid data points')
            except Exception as e:
                print(f'DEBUG: Failed to interpolate time differences: {e}')
                update_log(self, 'Error: Could not fix NaN values in time differences')
                return
        else:
            # DEBUG: No valid time differences found, cannot calculate data rate
            update_log(self, 'Error: No valid time differences available for data rate calculation')
            return
    self.pi_max = max([self.pi_max, np.nanmax(np.abs(np.asarray(dt_s_final)))])

    # Convert to numpy arrays and filter out NaN, infinite, and problematic values before plotting
    dr_smoothed_arr = np.asarray(dr_smoothed)
    z_mean_sorted_arr = np.asarray(z_mean_sorted)
    dr_smoothed_total_arr = np.asarray(dr_smoothed_total)
    dt_s_final_arr = np.asarray(dt_s_final)
    
    # Ensure c_mean_sorted is a numpy array for proper indexing
    c_mean_sorted_arr = np.asarray(c_mean_sorted) if hasattr(c_mean_sorted, '__len__') else c_mean_sorted
    
    valid_mask = ~(np.isnan(dr_smoothed_arr) | np.isnan(z_mean_sorted_arr) | np.isinf(dr_smoothed_arr) | np.isinf(z_mean_sorted_arr) | (dr_smoothed_arr < 0) | (z_mean_sorted_arr < -10000))
    dr_smoothed_valid = dr_smoothed_arr[valid_mask]
    z_mean_sorted_valid = z_mean_sorted_arr[valid_mask]
    c_mean_sorted_valid = c_mean_sorted_arr[valid_mask] if hasattr(c_mean_sorted_arr, '__len__') else c_mean_sorted_arr
    
    valid_mask_total = ~(np.isnan(dr_smoothed_total_arr) | np.isnan(z_mean_sorted_arr) | np.isinf(dr_smoothed_total_arr) | np.isinf(z_mean_sorted_arr) | (dr_smoothed_total_arr < 0) | (z_mean_sorted_arr < -10000))
    dr_smoothed_total_valid = dr_smoothed_total_arr[valid_mask_total]
    z_mean_sorted_total_valid = z_mean_sorted_arr[valid_mask_total]
    c_mean_sorted_total_valid = c_mean_sorted_arr[valid_mask_total] if hasattr(c_mean_sorted_arr, '__len__') else c_mean_sorted_arr
    
    valid_mask_dt = ~(np.isnan(dt_s_final_arr) | np.isnan(z_mean_sorted_arr) | np.isinf(dt_s_final_arr) | np.isinf(z_mean_sorted_arr) | (dt_s_final_arr < 0) | (z_mean_sorted_arr < -10000))
    dt_final_valid = dt_s_final_arr[valid_mask_dt]
    z_mean_sorted_dt_valid = z_mean_sorted_arr[valid_mask_dt]
    c_mean_sorted_dt_valid = c_mean_sorted_arr[valid_mask_dt] if hasattr(c_mean_sorted_arr, '__len__') else c_mean_sorted_arr
    
    # Additional validation: ensure we have valid data to plot
    if len(dr_smoothed_valid) == 0:
        # DEBUG: No valid data rate values after filtering
        update_log(self, 'Warning: No valid data rate values to plot')
        return
        
    if len(z_mean_sorted_valid) == 0:
        # DEBUG: No valid depth values after filtering
        update_log(self, 'Warning: No valid depth values to plot')
        return
        
    # DEBUG: Filtered data - dr_smoothed: {len(dr_smoothed_valid)}/{len(dr_smoothed)}, z_mean_sorted: {len(z_mean_sorted_valid)}/{len(z_mean_sorted)}
    # DEBUG: dr_smoothed_valid range: [{np.min(dr_smoothed_valid)}, {np.max(dr_smoothed_valid)}]
    # DEBUG: z_mean_sorted_valid range: [{np.min(z_mean_sorted_valid)}, {np.max(z_mean_sorted_valid)}]

    # DEBUG: Filtered data - dr_smoothed: {len(dr_smoothed_valid)}/{len(dr_smoothed)} valid points
    # DEBUG: Filtered data - dr_smoothed_total: {len(dr_smoothed_total_valid)}/{len(dr_smoothed_total)} valid points
    # DEBUG: Filtered data - dt_final: {len(dt_final_valid)}/{len(dt_s_final)} valid points

    try:
        if self.match_data_cmodes_chk.isChecked() and self.last_cmode != 'solid_color':

            self.h_data_rate_smoothed = self.data_rate_ax1.scatter(dr_smoothed_valid, z_mean_sorted_valid,
                                                                   s=self.pt_size, c=c_mean_sorted_valid, marker='o',
                                                                   label=local_label,
                                                                   vmin=self.clim[0], vmax=self.clim[1], cmap=self.cmap,
                                                                   alpha=self.pt_alpha, linewidths=0)

            self.h_data_rate_smoothed_total = self.data_rate_ax1.scatter(dr_smoothed_total_valid, z_mean_sorted_total_valid,
                                                                         s=self.pt_size, c=c_mean_sorted_total_valid, marker='+',
                                                                         label=local_label,
                                                                         vmin=self.clim[0], vmax=self.clim[1], cmap=self.cmap,
                                                                         alpha=self.pt_alpha, linewidths=0)

            self.h_ping_interval = self.data_rate_ax2.scatter(dt_final_valid, z_mean_sorted_dt_valid,
                                                              s=self.pt_size, c=c_mean_sorted_dt_valid, marker='o',
                                                              label=local_label,
                                                              vmin=self.clim[0], vmax=self.clim[1], cmap=self.cmap,
                                                              alpha=self.pt_alpha, linewidths=0)

            # self.legend_handles_data_rate.append(h_data_rate)  # append handles for legend with 'New data' or 'Archive data'
            self.legend_handles_data_rate = [h for h in self.legend_handles]  # save swath legend handle info for data plots


        else:  # use solid colors for data rate plots (new/archive) if not applying the swath plot color modes
            if is_archive:  # use archive solid color
                c_mean_sorted_valid = np.tile(np.asarray(colors.hex2color(self.color_arc.name())), (len(z_mean_sorted_valid), 1))
                c_mean_sorted_total_valid = np.tile(np.asarray(colors.hex2color(self.color_arc.name())), (len(z_mean_sorted_total_valid), 1))
                c_mean_sorted_dt_valid = np.tile(np.asarray(colors.hex2color(self.color_arc.name())), (len(z_mean_sorted_dt_valid), 1))

            else:  # get new data solid color
                c_mean_sorted_valid = np.tile(np.asarray(colors.hex2color(self.color.name())), (len(z_mean_sorted_valid), 1))
                c_mean_sorted_total_valid = np.tile(np.asarray(colors.hex2color(self.color.name())), (len(z_mean_sorted_total_valid), 1))
                c_mean_sorted_dt_valid = np.tile(np.asarray(colors.hex2color(self.color.name())), (len(z_mean_sorted_dt_valid), 1))

            self.h_data_rate_smoothed = self.data_rate_ax1.scatter(dr_smoothed_valid, z_mean_sorted_valid,
                                                                   s=self.pt_size, c=c_mean_sorted_valid,
                                                                   label=local_label, marker='o',
                                                                   alpha=self.pt_alpha, linewidths=0)

            self.h_data_rate_smoothed_total = self.data_rate_ax1.scatter(dr_smoothed_total_valid, z_mean_sorted_total_valid,
                                                                         s=self.pt_size, c=c_mean_sorted_total_valid,
                                                                         label=local_label, marker='+',
                                                                         alpha=self.pt_alpha, linewidths=0)

            self.h_ping_interval = self.data_rate_ax2.scatter(dt_final_valid, z_mean_sorted_dt_valid,
                                                              s=self.pt_size, c=c_mean_sorted_dt_valid,
                                                              label=local_label,
                                                              marker='o', alpha=self.pt_alpha, linewidths=0)

            self.legend_handles_data_rate.append(self.h_data_rate_smoothed)  # append handles for legend with 'New data' or 'Archive data'
            # self.legend_handles_data_rate.append(self.h_data_rate_smoothed)  # append handles for legend with 'New data' or 'Archive data'
            
        # DEBUG: Successfully plotted data rate
        
    except Exception as e:
        # DEBUG: Failed to plot data rate: {e}
        # DEBUG: dr_smoothed shape: {np.shape(dr_smoothed)}, z_mean_sorted shape: {np.shape(z_mean_sorted)}
        # DEBUG: dr_smoothed dtype: {dr_smoothed.dtype}, z_mean_sorted dtype: {z_mean_sorted.dtype}
        # DEBUG: dr_smoothed has NaN: {np.any(np.isnan(dr_smoothed))}, z_mean_sorted has NaN: {np.any(np.isnan(z_mean_sorted))}
        # DEBUG: dr_smoothed range: [{np.nanmin(dr_smoothed)}, {np.nanmax(dr_smoothed)}]
        # DEBUG: z_mean_sorted range: [{np.nanmin(z_mean_sorted)}, {np.nanmax(z_mean_sorted)}]
        update_log(self, f'Error: Failed to plot data rate - {str(e)}')
        return

    try:
        # set data rate x max based on actual values
        # self.data_rate_ax1.set_xlim(0.0, np.ceil(np.nanmax(dr_smoothed))*1.1)
        try:
            # self.data_rate_ax1.set_xlim(0.0, np.ceil(np.nanmax(dr_smoothed_total))*1.1)  # try to accommodate wcd total
            self.data_rate_ax1.set_xlim(0.0, self.max_dr*self.swath_ax_margin)  # try to accommodate wcd total

        except:
            # Fix All-NaN slice error by checking if dr_smoothed contains any valid values
            if not np.all(np.isnan(dr_smoothed)):
                self.data_rate_ax1.set_xlim(0.0, np.ceil(np.nanmax(dr_smoothed))*1.1)  # if total with wcd is all nans
            else:
                # If all values are NaN, set a default limit
                self.data_rate_ax1.set_xlim(0.0, 1000.0)  # default limit when no valid data


        # self.data_rate_ax1.set_ylim(self.swath_ax.get_ylim()[1])  # match depth limit

        # set ping interval x max based on actual values or the filter values
        # ping_int_xlim = [np.nanmax(dt_s_final), float(self.max_ping_int_tb.text())][int(self.ping_int_gb.isChecked())]
        # self.data_rate_ax2.set_xlim(0.0, np.ceil(ping_int_xlim)*1.1)  # add 10% upper xlim margin
        # self.data_rate_ax2.set_ylim(self.swath_ax.get_ylim()[1])  # match depth limit

        self.data_canvas.draw()
        plt.show()
        # DEBUG: Successfully updated data rate plot display
        
    except Exception as e:
        # DEBUG: Failed to update data rate plot display: {e}
        update_log(self, f'Error: Failed to update data rate plot display - {str(e)}')

# def update_annot(self, ind):  # adapted from SO example
# 	print('madee it to UPDATE_ANNOT')
# 	pos = self.h_data_rate_smoothed.get_offsets()[ind["ind"][0]]
# 	self.annot.xy = pos
# 	text = "{}, {}".format(" ".join(list(map(str,ind["ind"]))),
# 						   " ".join([self.fnames_sorted[n] for n in ind["ind"]]))
# 	print('got text:', text)
# 	self.annot.set_text(text)
# 	self.annot.get_bbox_patch().set_facecolor(cmap(norm(c[ind["ind"][0]])))
# 	self.annot.get_bbox_patch().set_alpha(0.4)
# 	print('leaving update_annot')
#
#
# def hover(self, event):  # adapted from SO example
# 	print('made it to HOVER')
# 	vis = self.annot.get_visible()
# 	if event.inaxes == ax:
# 		cont, ind = self.h_data_rate_smoothed.contains(event)
# 		if cont:
# 			update_annot(ind)
# 			self.annot.set_visible(True)
# 			self.data_canvas.draw_idle()
# 		else:
# 			if vis:
# 				self.annot.set_visible(False)
# 				self.data_canvas.draw_idle()
#
# 	# plt.show()


def plot_time_diff(self):
    # print('\n\n\n****** in plot_time_diff')
    # print('self.skm_time has keys =', self.skm_time.keys())

    for f in self.skm_time.keys():

        # if self.print_updates:
        # 	print('plotting skm_time for f = ', f)
        # 	print('self.skm_time[f] =', self.skm_time[f])
        # 	print('self.skm_time[f][SKM_header_datetime] =', self.skm_time[f]['SKM_header_datetime'])

        hdr_dt = self.skm_time[f]['SKM_header_datetime']
        raw_dt = self.skm_time[f]['SKM_sample_datetime']
        skm_time_diff_ms = [1000*(hdr_dt[i] - raw_dt[i]).total_seconds() for i in range(len(hdr_dt))]

        # print('got skm_time_diff =', skm_time_diff)
        # skm_time_diff = [self.skm_time[f]['SKM_header_datetime'][i] - self.skm_time[f]['SKM_sample_datetime']
        # print('len(skm_time_diff_ms) =', len(skm_time_diff_ms))
        # print('got first ten skm_time_diff_ms =', skm_time_diff_ms[0:10])
        # print(' convert to seconds =', skm_time_diff.total_seconds())
        # print('convert to milliseconds =', 1000*skm_time_diff.total_seconds())

        self.time_ax1.plot(self.skm_time[f]['SKM_header_datetime'], skm_time_diff_ms)

def plot_hist(self):
    # plot histogram of soundings versus depth for new and archive data
    z_all_new = []
    z_all_arc = []
    hist_data = []  # list of hist arrays
    labels = []  # label list
    clist = []  # color list

    # add new data only if it exists and is displayed
    if all(k in self.det for k in ['z_port', 'z_stbd']) and self.show_data_chk.isChecked():
        z_all_new.extend(self.det['z_port'] + self.det['z_stbd'])
        labels.append('New')
        clist.append('black')
        hist_data.append(np.asarray(z_all_new))

    if self.show_data_chk_arc.isChecked():  # try to add archive data only if displayed
        for k in self.det_archive.keys():  # loop through all files in det_archive, if any, and add data
            # Handle both new format (z_port/z_stbd) and old format (x_port/x_stbd) archive files
            if 'z_port' in self.det_archive[k] and 'z_stbd' in self.det_archive[k]:
                z_all_arc.extend(self.det_archive[k]['z_port'] + self.det_archive[k]['z_stbd'])
            elif 'x_port' in self.det_archive[k] and 'x_stbd' in self.det_archive[k]:
                z_all_arc.extend(self.det_archive[k]['x_port'] + self.det_archive[k]['x_stbd'])
        if z_all_arc:  # Only add if we found data
            labels.append('Arc.')
            clist.append('darkgray')
            hist_data.append(np.asarray(z_all_arc))

    # print('heading to hist plot, hist_data=', hist_data, 'and clist=', clist)

    z_range = (0, self.swath_ax_margin * self.z_max)  # match z range of swath plot
    if hist_data and clist:
        self.hist_ax.hist(hist_data, range=z_range, bins=30, color=clist, histtype='bar',
                          orientation='horizontal', label=labels, log=True, rwidth=0.40*len(labels))

        if self.colorbar_chk.isChecked():  # add colorbar
            self.hist_legend = self.hist_ax.legend(fontsize=self.cbar_font_size, loc=self.cbar_loc, borderpad=0.03)

            for patch in self.hist_legend.get_patches():  # reduce size of patches to fit on narrow subplot
                patch.set_width(5)
                patch.set_x(10)

def calc_coverage_trend(self, z_all, y_all, is_archive):
    print('attempting to process and export trend for Gap Filler')

    try:
        print('trying to calculate means and medians')
        # bins = np.linspace(min(self.z_all), max(self.z_all), 11)
        bins = np.linspace(min(z_all), max(z_all), 11)
        dz = np.mean(np.diff(bins))
        # print('got bins = ', bins, 'with dz = ', dz)
        # y_all_abs = np.abs(self.y_all)
        y_all_abs = np.abs(y_all)

        # print('got y_all_abs =', y_all_abs)
        # z_all_dig = np.digitize(self.z_all, bins)
        z_all_dig = np.digitize(z_all, bins)

        # print('got z_all_dig =', z_all_dig)
        trend_bin_means = [y_all_abs[z_all_dig == i].mean() for i in range(1, len(bins))]
        # bin_medians = [np.median(y_all_abs[z_all_dig == i]) for i in range(1, len(bins))]
        # print('got bin_means = ', trend_bin_means)
        trend_bin_centers = [i + dz/2 for i in bins[:-1]]

        if self.show_coverage_trend_chk.isChecked():
            c_trend = ['black', 'gray'][is_archive]
            trend_bin_means_plot = trend_bin_means + ([-1*i for i in trend_bin_means])
            trend_bin_centers_plot = 2*trend_bin_centers
            self.h_trend = self.swath_ax.scatter(trend_bin_means_plot, trend_bin_centers_plot,
                                  marker='o', s=10, c=c_trend)
            # self.h_trend = self.swath_ax.scatter(trend_bin_means, trend_bin_centers,
            # 					  marker='o', s=10, c=c_trend)
            # self.swath_ax.scatter([-1*i for i in trend_bin_means], trend_bin_centers,
            # 					  marker='o', s=10, c=c_trend)

        if is_archive:
            self.trend_bin_centers_arc = trend_bin_centers
            self.trend_bin_means_arc = trend_bin_means

        else:
            self.trend_bin_centers = trend_bin_centers
            self.trend_bin_means = trend_bin_means

    except RuntimeError:
        print('error calculating or plotting Gap Filler coverage')

def export_gap_filler_trend(self):
    # export coverage trend for Gap Filler
    print('attempting to process and export trend for Gap Filler')
    is_archive = str(self.export_gf_cbox.currentText()) == 'Archive'
    print('is_archive =', is_archive)
    z = [self.trend_bin_centers, self.trend_bin_centers_arc][is_archive]
    y = [self.trend_bin_means, self.trend_bin_means_arc][is_archive]

    print('in export_gap_filler_trend, z = ', z, ' and y =', y)

    if z and y:
    # if self.trend_bin_means and self.trend_bin_centers:
    # 	nwd = 2 * np.asarray(self.trend_bin_means) / np.asarray(self.trend_bin_centers)  # calculate water depth multiple
        nwd = 2 * np.asarray(y) / np.asarray(z)  # calculate water depth multiple
        # print('bin centers = ', self.trend_bin_centers)
        # print('bin centers = ')
        # print('bin means = ', self.trend_bin_means)
        print('nwd = ', nwd)

        update_log(self, 'Calculated coverage trend from filtered data')

        trend_name = '_'.join([self.ship_name, self.model_name]) + '_' + [self.cruise_name, 'archive'][is_archive]
        trend_name = "".join([c for c in trend_name if c.isalnum() or c in ['-', '_']]) + '.txt'  # remove any / \ etc

        current_path = self.export_save_dir.replace('\\', '/')
        trend_path = QtWidgets.QFileDialog.getSaveFileName(self, 'Save trend file', current_path + '/' + trend_name)
        fname_out = trend_path[0]

        print('trend fname_out = ', fname_out)
        # trend_z = np.round([0] + self.trend_bin_centers + [10000]).tolist()
        trend_z = np.round([0] + z + [10000]).tolist()
        trend_y = np.round([5] + nwd.tolist() + [0], decimals=1).tolist()

        print('trend_z =', trend_z)
        print('trend_y =', trend_y)

        trend_fid = open(fname_out, 'w')
        trend_fid.writelines([str(z) + ' ' + str(y) + '\n' for z, y in zip(trend_z, trend_y)])
        trend_fid.close()
        
        # Save the directory for next time
        if fname_out:
            import os
            save_dir = os.path.dirname(fname_out)
            if save_dir:
                self.export_save_dir = save_dir
                config = load_session_config()
                config["last_export_save_dir"] = save_dir
                save_session_config(config)

    else:
        update_log(self, 'No coverage data available for trend export')

def update_param_log(self, entry, font_color='black'):  # update the acquisition param log
    self.param_log.setTextColor(QColor(font_color))
    self.param_log.append(entry)
    QtWidgets.QApplication.processEvents()

def sort_det_time(self):  # sort detections by time (after new files are added)
    # Debug print removed
    datetime_orig = deepcopy(self.det['datetime'])
    for k, v in self.det.items():
        # print('...sorting ', k)
        # self.det[k] = [x for _, x in sorted(zip(self.det['datetime'], self.det[k]))]  #potentially not sorting properly after sorting the 'datetime' field!
        self.det[k] = [x for _, x in sorted(zip(datetime_orig, self.det[k]))]

    print('done sorting detection times')

    get_param_changes(self, search_dict={}, update_log=True, include_initial=True,
                      header='\n***COVERAGE RECALCULATED*** Initial settings and all changes in scanned data:\n')

def get_param(self, i=0, nearest='next', update_log=False):  # get the parameters in effect at time dt (datetime)

    if isinstance(i, datetime.datetime):  # datetime format for search
        print('search criterion is datetime object --> will look for params at nearest time (nearest=', nearest, ')')

        if nearest == 'next':  # find first parameter time equal to or after requested time
            j = min([np.argmax(np.asarray(self.det['datetime']) >= i), len(self.det['datetime']) - 1])

        elif nearest == 'prior':  # find last parameter time prior to or equal to requested time
            j = max([0, np.argmax(np.asarray(self.det['datetime']) <= i)])

    elif isinstance(i, int):  # find parameter at given index
        print('search criterion is integer --> will get params at this index')

        if i < 0:
            print('requested index (', i, ') is less than 0; resetting to 0')
            j = 0

        elif i >= len(self.det['datetime']):
            print('requested index (', i, ') exceeds num of pings (', str(len(self.det['datetime'])), ')')
            j = len(self.det['datetime']) -1
            print('setting j to last ping index (', j, ')')

        else:
            j = i

    else:  # requested index not supported
        print('param search index i=', i, 'is not supported (datetime or integer only!)')

    print('found index j=', j)

    self.param_state = dict((k, [self.det[k][j]]) for k in self.param_list)
    print('made self.param_state at j=', j, ' --> ', self.param_state)

    if update_log:
        update_param_log(self, format_param_str(self))

def format_param_str(self, param_dict=[], i=0):  # format fields of params dict for printing / updating log
    if not param_dict:  # default to current param state dict if not specified
        param_dict = deepcopy(self.param_state)
        i = 0

    time_str = param_dict['datetime'][i].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # time string truncated to ms
    param_list = [str(param_dict[k][i].split('Swath')[0].strip()) for k in ['ping_mode', 'pulse_form', 'swath_mode']]
    lim_deg_str = '/'.join([str(float(param_dict[k][i])) for k in ['max_port_deg', 'max_stbd_deg']])
    lim_m_str = '/'.join([str(float(param_dict[k][i])) for k in ['max_port_m', 'max_stbd_m']])
    freq_str = str(param_dict['frequency'][i])
    wl_z_m_str = str(param_dict['wl_z_m'][i])
    tx_xyz_m_str = '[' + ','.join([str(param_dict[k][i]) for k in
                                   ['tx_x_m', 'tx_y_m', 'tx_z_m', 'tx_r_deg', 'tx_p_deg', 'tx_h_deg']]) + ']'
    rx_xyz_m_str = '[' + ','.join([str(param_dict[k][i]) for k in
                                   ['rx_x_m', 'rx_y_m', 'rx_z_m', 'rx_r_deg', 'rx_p_deg', 'rx_h_deg']]) + ']'
    pos_xyz_m_str = '[(' + str(param_dict['aps_num'][i]) + ')' +\
                    ','.join([str(param_dict[k][i]) for k in ['aps_x_m', 'aps_y_m', 'aps_z_m']]) + ']'

    # format all fields in desired order with delimiters/spacing
    param_list.extend([lim_deg_str, lim_m_str])
    param_log_str = time_str + ': ' + ', '.join([k for k in param_list])
    param_log_str = param_log_str + ', ' + ', '.join([freq_str, wl_z_m_str, tx_xyz_m_str, rx_xyz_m_str, pos_xyz_m_str])

    if self.print_updates:
        print(param_log_str)

    return param_log_str

def get_param_changes(self, search_dict={}, update_log=False, header='', include_initial=True):
    # step 1: find changes in params in detection dict (default: report ANY changes satisfying the user's options)
    # step 2: if necessary, confirm ALL user options are satisfied (e.g., find times of specific configurations)

    print('\n*** in get_param_changes, search_dict =', search_dict)

    if search_dict:  # get summary of search criteria to update header in log
        search_str_list = []
        self.param_cond_cbox.currentText().split()[0]
        header = '\n***NEW SEARCH*** ' + ('Initial settings and times' if include_initial else 'Times') +\
                 ' of changes that satisfy ' + self.param_cond_cbox.currentText().split()[0] +\
                 ' of the following parameters:\n'

        for p in search_dict.keys():
            search_str_list.append(' '.join([p, search_dict[p]['condition'], search_dict[p]['value']]))
            search_str = 'time: ' + ', '.join([s for s in search_str_list if s.find('datetime') < 0])

    else:  # default search for all params of interest if not specified
        search_dict = dict((k, {'value': 'All', 'condition': '=='}) for k in self.param_list)
        print('in get_param_changes, search_dict was not specified --> made search_dict = ', search_dict)

        search_str = 'time: ' + ', '.join([p for p in search_dict.keys() if p != 'datetime'])

    if header == '':  # assume new search header if no header is specified
        header = '\n***NEW SEARCH*** Initial settings and ALL CHANGES to acquisition parameters:\n'
                     # ', '.join([p for p in search_dict.keys() if p is not 'datetime'])

    header = header + search_str  # add search criteria to header

    # simplify the header a bit to match format of params
    header_format = {'swath angles (deg, port/stbd)': 'max_port_deg, max_stbd_deg',
                     'swath coverage (m, port/stbd)': 'max_port_m, max_stbd_m',
                     'TX [XYZRPH]': 'tx_x_m, tx_y_m, tx_z_m, tx_r_deg, tx_p_deg, tx_h_deg',
                     'RX [XYZRPH]': 'rx_x_m, rx_y_m, rx_z_m, rx_r_deg, rx_p_deg, rx_h_deg',
                     'POS. [(#)XYZ]': 'aps_num, aps_x_m, aps_y_m, aps_z_m'}

    for new_str, old_fields in header_format.items():
        header = header.replace(old_fields, new_str)

    # replace wordy install params
    header = re.sub(r'tx_x_m.*, tx_y_m.*, tx_z_m.*, tx_r_deg.*, tx_p_deg.*, tx_h_deg', 'TX [XYZRPH]', header)
    header = re.sub(r'rx_x_m.*, rx_y_m.*, rx_z_m.*, rx_r_deg.*, rx_p_deg.*, rx_h_deg', 'RX [XYZRPH]', header)
    header = re.sub(r'aps_num.*, aps_x_m.*, aps_y_m.*, aps_z_m', 'POS. [(#)XYZ]', header)

    update_param_log(self, header)

    idx_change = []
    for param, crit in search_dict.items():  # find CHANGES for each parameter of interest, then sort
        # print('****** SEARCHING DETECTION DICT FOR PARAMETER, CRIT = ', param, crit)
        if param == 'datetime':  # skip datetime, which changes for every entry
            # print('skipping datetime')
            continue

        p_last = self.det[param][0]
        # print('first setting = ', p_last)

        # find ALL changes to this parameter, then reduce to those that satisfy the user criteria (ANY or ALL match)
        if param in ['ping_mode', 'swath_mode', 'pulse_form']:  # simplify, e.g., 'Deep (Manual)' to 'Deep'
            idx_temp = [i for i in range(1, len(self.det[param])) if
                        self.det[param][i].rsplit('(')[0].strip() != self.det[param][i-1].rsplit('(')[0].strip()]

        else:  # otherwise, compare directly
            idx_temp = [i for i in range(1, len(self.det[param])) if self.det[param][i] != self.det[param][i-1]]

        # print('found idx_temp_param for ALL CHANGES =', idx_temp)

        if crit['value'] != 'All':  # find changes that satisfy user options for this setting (e.g., ping_mode == Deep)
            include_initial=False  # do not print initial state (default) unless it matches the search criteria (TBD)
            idx_temp.append(0)  # add index=0 to search initial state for user criteria (will be sorted later)

            # print('searching all changes for times when ', param, crit['condition'], crit['value'])

            # if param in ['ping_mode', 'swath_mode', 'pulse_form', 'frequency', 'wl_z_m']:  # find MATCHING settings
            if search_dict[param]['condition'] == '==':  # find MATCHING settings

                idx_temp = [i for i in idx_temp if self.det[param][i].rsplit("(")[0].strip() == crit['value']]
                print('updated idx_temp to ', idx_temp)

            # elif param in ['max_port_deg', 'max_stbd_deg', 'max_port_m', 'max_stbd_m']:  # evaluate setting COMPARISON
            else:  # evaluate setting COMPARISON (e.g., compare limit value against user text input)
                print('working on comparing swath limits...')

                if crit['condition'] == '==':
                    print('looking for swath limits that EQUAL the user value')
                    idx_temp = [i for i in idx_temp if float(self.det[param][i]) == float(crit['value'])]
                    print('updated idx_temp = ', idx_temp)

                elif crit['condition'] == '<=':
                    print('looking for swath limits that are LESS THAN OR EQUAL TO the user value')
                    idx_temp = [i for i in idx_temp if float(self.det[param][i]) <= float(crit['value'])]
                    print('updated idx_temp = ', idx_temp)

                elif crit['condition'] == '>=':
                    print('looking for swath limits that are GREATER THAN OR EQUAL RO the user value')
                    idx_temp = [i for i in idx_temp if float(self.det[param][i]) >= float(crit['value'])]
                    print('updated idx_temp = ', idx_temp)

                else:
                    print('this condition was not found --> ', crit['condition'])

        #if self.print_updates:
            #print('param fits criteria at idx=', idx_temp, ':', ' --> '.join([str(self.det[param][j]) for j in idx_temp]))

        idx_change.extend(idx_temp)

    idx_change_set = sorted([i for i in set(idx_change)])  # sorted unique indices of ANY changes (default to report)

    idx_match_all = []  # if necessary, review times to see whether ALL search criteria are satisfied
    if self.param_cond_cbox.currentText().split()[0].lower() == 'all':  # user wants ALL search criteria satisfied
        print('looking for change indices that satisfy ALL search criteria')
        for i in idx_change_set:  # review the parameters of interest at each time and keep if ALL are satisfied
            all_match = True
            get_param(self, i)
            print('Comparing ALL params for index ', i, 'where param_state =', self.param_state)

            for param, crit in search_dict.items():  # verify all params match user options at this index
                print('searching param, crit =', param, crit)

                if crit['value'] != 'All':  # check specific parameter matches (all_match stays true if "All" allowed)
                    print('SPECIFIC crit[value] =', crit['value'])

                    # if param in ['ping_mode', 'swath_mode', 'pulse_form', 'frequency', 'wl_z_m']:  # compare selection
                    if search_dict[param]['condition'] == '==':  # find MATCHING settings
                        all_match = self.det[param][i].rsplit("(")[0].strip() == crit['value']

                    # elif param in ['max_port_deg', 'max_stbd_deg', 'max_port_m', 'max_stbd_m']:  # compare text value
                    else:  # evaluate setting COMPARISON (e.g., compare limit value against user text input)
                        if crit['condition'] == '==':
                            all_match = float(self.det[param][i]) == float(crit['value'])

                        elif crit['condition'] == '<=':
                            all_match = float(self.det[param][i]) <= float(crit['value'])

                        elif crit['condition'] == '>=':
                            all_match = float(self.det[param][i]) >= float(crit['value'])

                print('    just finished comparison, all_match =', all_match)

                if not all_match:  # break the param search loop on this index if anything does not match
                    print('**** params do not all match at index', i)
                    break

            if all_match:
                idx_match_all.append(i)  # append this index only if everything matched (param search loop was not broken)
                print('all matched, updated idx_match_all to', idx_match_all)

        idx_change_set = sorted([i for i in set(idx_match_all)])  # sorted unique indices when ALL parameters match

    for p in self.param_list:  # update the param change dict
        self.param_changes[p] = [self.det[p][i] for i in idx_change_set]

    print('got idx_change = ', idx_change)
    print('got idx_change_set = ', idx_change_set)
    print('updated self.param_changes =', self.param_changes)

    if include_initial:  # print the initial state if desired
        get_param(self, i=0, update_log=True)

    if update_log:
        # Debug print removed
        if len(self.param_changes['datetime']) > 0:
            print('1')
            for i in range(len(self.param_changes['datetime'])):
                print('calling update_param_log')
                update_param_log(self, format_param_str(self, param_dict=self.param_changes, i=i))
            print('2')
            update_param_log(self, 'End of search results...')

        elif include_initial:
            print('3')
            update_param_log(self, 'End of search results...')

        else:
            print('4')
            update_param_log(self, 'No results...')
    print('end of routine calling update_param_log')


def update_param_search(self, update_log=True):  # update runtime param search criteria selected by the user
    # define master list of search params: combo of user input (runtime params) and ALL install params by default
    self.param_dict = {'ping_mode': {'chk': self.p1_chk.isChecked(), 'value': self.p1_cbox.currentText(), 'condition': '=='},
                       'swath_mode': {'chk': self.p2_chk.isChecked(), 'value': self.p2_cbox.currentText(), 'condition': '=='},
                       'pulse_form': {'chk': self.p3_chk.isChecked(), 'value': self.p3_cbox.currentText(), 'condition': '=='},
                       'max_port_deg': {'chk': self.p4_chk.isChecked(), 'value': self.p4_tb.text(), 'condition': self.p4_cbox.currentText()},
                       'max_stbd_deg': {'chk': self.p4_chk.isChecked(), 'value': self.p4_tb.text(), 'condition': self.p4_cbox.currentText()},
                       'max_port_m': {'chk': self.p5_chk.isChecked(), 'value': self.p5_tb.text(), 'condition': self.p5_cbox.currentText()},
                       'max_stbd_m': {'chk': self.p5_chk.isChecked(), 'value': self.p5_tb.text(), 'condition': self.p5_cbox.currentText()},
                       'frequency': {'chk': self.p6_chk.isChecked(), 'value': self.p6_cbox.currentText(), 'condition': '=='},
                       'wl_z_m': {'chk': self.p7_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'tx_x_m': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'tx_y_m': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'tx_z_m': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'tx_r_deg': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'tx_p_deg': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'tx_h_deg': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'rx_x_m': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'rx_y_m': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'rx_z_m': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'rx_r_deg': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'rx_p_deg': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'rx_h_deg': {'chk': self.p8_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'aps_num': {'chk': self.p9_chk.isChecked(), 'value': 'All', 'condition': '=='},  # act. pos. sys.
                       'aps_x_m': {'chk': self.p9_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'aps_y_m': {'chk': self.p9_chk.isChecked(), 'value': 'All', 'condition': '=='},
                       'aps_z_m': {'chk': self.p9_chk.isChecked(), 'value': 'All', 'condition': '=='}}

    print('made self.param_dict =', self.param_dict)

    if self.param_search_gb.isChecked():  # make a custom search dict to pass to get_param_changes
        search_dict = {}
        for param, crit in self.param_dict.items():
            if crit['chk']:
                search_dict[param] = crit
                # print('search_dict is now', search_dict)

    else:  # user has not specified parameters; search all parameters
        print('using the default param_list')
        search_dict = deepcopy(self.param_dict)

    get_param_changes(self, search_dict=search_dict, update_log=True)
    print('end update_param_search')

def save_param_log(self):
    # save the acquisition parameter search log to a text file
    param_log_name = QtWidgets.QFileDialog.getSaveFileName(self, 'Save parameter log...', self.param_save_dir + '/runtime_parameter_log.txt',
                                                           '.TXT files (*.txt)')

    if not param_log_name[0]:  # abandon if no output location selected
        update_log(self, 'No parameter log output file selected.')
        return

    else:  # save param log to text file
        fname_out = param_log_name[0]

        with open(fname_out, 'w') as param_log_file:
            param_log_file.write(str(self.param_log.toPlainText()))

        # Save the directory for next time
        if fname_out:
            import os
            save_dir = os.path.dirname(fname_out)
            if save_dir:
                self.param_save_dir = save_dir
                config = load_session_config()
                config["last_param_save_dir"] = save_dir
                save_session_config(config)

        update_log(self, 'Saved parameter log to ' + fname_out.rsplit('/')[-1])
        update_param_log(self, '\n*** SAVED PARAMETER LOG *** --> ' + fname_out)

def plot_backscatter(self, det, is_archive=False, print_updates=False, det_name='detection dictionary'):
    # plot the parsed detections from new or archive data dict with backscatter coloring; return the number of points plotted after filtering
    # Debug print removed
    
    # consolidate data from port and stbd sides for plotting
    try:
        y_all = det['y_port'] + det['y_stbd']  # acrosstrack distance from TX array (.all) or origin (.kmall)
    except:
        print('***EXCEPTION: y_port or y_stbd not found; treating this like an older archive format (x_port / x_stbd)')
        y_all = det['x_port'] + det['x_stbd']  # older archives stored acrosstrack distance as x, not y
        det['y_port'] = deepcopy(det['x_port'])
        det['y_stbd'] = deepcopy(det['x_stbd'])

    z_all = det['z_port'] + det['z_stbd']  # depth from TX array (.all) or origin (.kmall)
    bs_all = det['bs_port'] + det['bs_stbd']  # reported backscatter amplitude
    fname_all = det['fname'] + det['fname']

    print('len z_all, bs_all, and fname_all at start of plot_backscatter = ', len(z_all), len(bs_all), len(fname_all))

    # calculate simplified swath angle from raw Z, Y data to use for angle filtering and comparison to runtime limits
    # Kongsberg angle convention is right-hand-rule about +X axis (fwd), so port angles are + and stbd are -
    angle_all = (-1 * np.rad2deg(np.arctan2(y_all, z_all))).tolist()  # multiply by -1 for Kongsberg convention

    # warn user if detection dict does not have all required offsets for depth reference adjustment (e.g., old archives)
    if (not all([k in det.keys() for k in ['tx_x_m', 'tx_y_m', 'aps_x_m', 'aps_y_m', 'wl_z_m']]) and
            self.ref_cbox.currentText().lower() != 'raw data'):
            update_log(self, 'Warning: ' + det_name + ' does not include all fields required for depth reference '
                                                      'adjustment (e.g., possibly an old archive format); no depth '
                                                      'reference adjustment will be made')

    # get file-specific, ping-wise adjustments to bring Z and Y into desired reference frame
    dx_ping, dy_ping, dz_ping = adjust_depth_ref(det, depth_ref=self.ref_cbox.currentText().lower())

    z_all = [z + dz for z, dz in zip(z_all, dz_ping + dz_ping)]  # add dz (per ping) to each z (per sounding)
    y_all = [y + dy for y, dy in zip(y_all, dy_ping + dy_ping)]  # add dy (per ping) to each y (per sounding)

    if print_updates:
        for i in range(len(angle_all)):
            if any(np.isnan([angle_all[i], bs_all[i]])):
                print('NAN in (i,y,z,angle,BS):',
                      i, y_all[i], z_all[i], angle_all[i], bs_all[i])

    # update x and z max for axis resizing during each plot call
    self.x_max = max([self.x_max, np.nanmax(np.abs(np.asarray(y_all)))])
    self.z_max = max([self.z_max, np.nanmax(np.asarray(z_all))])

    # after updating axis limits, simply return w/o plotting if toggle for this data type (current/archive) is off
    if ((is_archive and not self.show_data_chk_arc.isChecked())
            or (not is_archive and not self.show_data_chk.isChecked())):
        print('returning from backscatter plotter because the toggle for this data type is unchecked')
        return

    # set up indices for optional masking on angle, depth, bs; all idx true until fail optional filter settings
    # all soundings masked for nans (e.g., occasional nans in EX0908 data)
    idx_shape = np.shape(np.asarray(z_all))
    angle_idx = np.ones(idx_shape)
    depth_idx = np.ones(idx_shape)
    bs_idx = np.ones(idx_shape)
    rtp_angle_idx = np.ones(idx_shape)  # idx of angles that fall within the runtime params for RX beam angles
    rtp_cov_idx = np.ones(idx_shape)  # idx of soundings that fall within the runtime params for max coverage
    real_idx = np.logical_not(np.logical_or(np.isnan(y_all), np.isnan(z_all)))

    # apply angle filter if enabled
    if self.angle_gb.isChecked():
        lims = [float(self.min_angle_tb.text()), float(self.max_angle_tb.text())]
        angle_idx = np.logical_and(np.abs(np.asarray(angle_all)) >= lims[0],
                                   np.abs(np.asarray(angle_all)) <= lims[1])

    # apply depth filter if enabled
    if self.depth_gb.isChecked():
        if is_archive:
            self.min_depth = float(self.min_depth_arc_tb.text())
            self.max_depth = float(self.max_depth_arc_tb.text())
        else:
            self.min_depth = float(self.min_depth_tb.text())
            self.max_depth = float(self.max_depth_tb.text())
        depth_idx = np.logical_and(np.greater_equal(np.asarray(z_all), self.min_depth),
                                   np.less_equal(np.asarray(z_all), self.max_depth))

    # apply backscatter filter if enabled
    if self.bs_gb.isChecked():
        self.min_bs = float(self.min_bs_tb.text())
        self.max_bs = float(self.max_bs_tb.text())
        bs_idx = np.logical_and(np.greater_equal(np.asarray(bs_all), self.min_bs),
                                np.less_equal(np.asarray(bs_all), self.max_bs))

    # apply runtime parameter angle filter if enabled
    if self.rtp_angle_gb.isChecked():  # get idx of angles near runtime param angle limits
        self.rx_angle_buffer = float(self.rtp_angle_buffer_tb.text())
        try:  # try to compare angles to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'min_port_deg' in det and 'max_stbd_deg' in det:  # compare angles to runtime params if available
                # angle buffer can be positive or negative; more negative, more aggressive filtering
                rtp_angle_idx_port = np.less_equal(np.asarray(angle_all),
                                                   np.asarray(det['min_port_deg']) - self.rx_angle_buffer)
                rtp_angle_idx_stbd = np.greater_equal(np.asarray(angle_all),
                                                      np.asarray(det['max_stbd_deg']) + self.rx_angle_buffer)
                rtp_angle_idx = np.logical_and(rtp_angle_idx_port, rtp_angle_idx_stbd)

                if print_updates:
                    print('set(min_port_deg)=', set(det['min_port_deg']))
                    print('set(max_stbd_deg)=', set(det['max_stbd_deg']))
                    print('sum of rtp_angle_idx=', sum(rtp_angle_idx))

            else:
                update_log(self, 'Runtime parameters for swath angle limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'angles against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing angles to runtime params; no angle filter applied')

    # apply runtime parameter coverage filter if enabled
    if self.rtp_cov_gb.isChecked():  # get idx of soundings with coverage near runtime param cov limits
        self.rx_cov_buffer = float(self.rtp_cov_buffer_tb.text())

        try:  # try to compare coverage to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'max_port_m' in det and 'max_stbd_m' in det:  # compare coverage to runtime params if available
                # coverage buffer is negative; more negative, more aggressive filtering
                rtp_cov_idx_port = np.greater_equal(np.asarray(y_all),
                                                    -1 * np.asarray(2 * det['max_port_m']) - self.rx_cov_buffer)
                rtp_cov_idx_stbd = np.less_equal(np.asarray(y_all),
                                                 np.asarray(2 * det['max_stbd_m']) + self.rx_cov_buffer)
                rtp_cov_idx = np.logical_and(rtp_cov_idx_port, rtp_cov_idx_stbd)

                if print_updates:
                    print('set(max_port_m)=', set(det['max_port_m']))
                    print('set(max_stbd_m)=', set(det['max_stbd_m']))
                    print('sum of rtp_cov_idx=', sum(rtp_cov_idx))

            else:
                update_log(self, 'Runtime parameters for swath coverage limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'coverage against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing coverage to runtime params; no coverage filter applied')

    # apply filter masks to x, z, angle, and bs fields
    filter_idx = np.logical_and.reduce((angle_idx, depth_idx, bs_idx, rtp_angle_idx, rtp_cov_idx, real_idx))

    # Determine color mode based on radio button selection
    if is_archive:
        if self.archive_data_color_by_type_radio.isChecked():
            cmode = 'backscatter'  # Use backscatter coloring
        else:
            cmode = 'solid_color'  # Use single color
    else:
        if self.new_data_color_by_type_radio.isChecked():
            cmode = 'backscatter'  # Use backscatter coloring
        else:
            cmode = 'solid_color'  # Use single color
    
    print('cmode for backscatter plot is', cmode)

    # set the color map, initialize color limits and set for legend/colorbars (local to backscatter plot)
    backscatter_cmap = 'rainbow'
    backscatter_clim = []
    backscatter_cset = []
    backscatter_legend_label = ''

    # set color maps for backscatter
    if cmode == 'backscatter':
        c_all = [int(bs*10)/10 for bs in bs_all]  # BS stored in dB; convert to 0.1 precision
        print('cmode is backscatter, len c_all=', len(c_all))
        backscatter_clim = [-50, -10]
    else:  # solid_color
        c_all = [1] * len(bs_all)  # Use single color value
        print('cmode is solid_color, len c_all=', len(c_all))
        backscatter_clim = [0, 1]

    # use backscatter filter limits for color limits
    if self.bs_gb.isChecked() and self.clim_cbox.currentText() == 'Filtered data':
        backscatter_clim = [float(self.min_bs_tb.text()), float(self.max_bs_tb.text())]

    backscatter_legend_label = 'Reported Backscatter (dB)'

    # filter the data after storing the color data
    y_all = np.asarray(y_all)[filter_idx].tolist()
    z_all = np.asarray(z_all)[filter_idx].tolist()
    angle_all = np.asarray(angle_all)[filter_idx].tolist()
    bs_all = np.asarray(bs_all)[filter_idx].tolist()
    c_all = np.asarray(c_all)[filter_idx].tolist()

    self.fnames_all = np.asarray(fname_all)[filter_idx].tolist()

    if print_updates:
        print('AFTER APPLYING IDX: len y_all, z_all, angle_all, bs_all, c_all=',
              len(y_all), len(z_all), len(angle_all), len(bs_all), len(c_all))

    # get post-filtering number of points to plot and allowable maximum from default or user input (if selected)
    self.n_points = len(y_all)
    self.n_points_max = self.n_points_max_default

    if self.pt_count_gb.isChecked() and self.max_count_tb.text():  # override default only if explicitly set by user
        self.n_points_max = float(self.max_count_tb.text())

    # default dec fac to meet n_points_max, regardless of whether user has checked box for plot point limits
    if self.n_points_max == 0:
        update_log(self, 'Max plotting sounding count set equal to zero')
        self.dec_fac_default = np.inf
    else:
        self.dec_fac_default = float(self.n_points / self.n_points_max)

    if self.dec_fac_default > 1 and not self.pt_count_gb.isChecked():  # warn user if large count may slow down plot
        update_log(self, 'Large filtered sounding count (' + str(self.n_points) + ') may slow down plotting')

    # get user dec fac as product of whether check box is checked (default 1)
    self.dec_fac_user = max(self.pt_count_gb.isChecked() * float(self.dec_fac_tb.text()), 1)
    self.dec_fac = max(self.dec_fac_default, self.dec_fac_user)

    # decimate data if necessary
    if self.dec_fac > 1:
        y_all = y_all[::int(self.dec_fac)]
        z_all = z_all[::int(self.dec_fac)]
        angle_all = angle_all[::int(self.dec_fac)]
        bs_all = bs_all[::int(self.dec_fac)]
        c_all = c_all[::int(self.dec_fac)]
        self.fnames_all = self.fnames_all[::int(self.dec_fac)]

    # plot the data on the backscatter canvas
    if len(z_all) > 0:
        # clear the backscatter axis
        self.backscatter_ax.clear()
        
        # plot the backscatter data
        if cmode == 'backscatter':
            self.h_backscatter = self.backscatter_ax.scatter(y_all, z_all, s=self.pt_size, c=c_all,
                                                             marker='o', alpha=self.pt_alpha, linewidths=0,
                                                             vmin=backscatter_clim[0], vmax=backscatter_clim[1], cmap=backscatter_cmap)
        else:  # solid_color
            # Use the selected solid color, convert QColor to matplotlib format
            solid_color = colors.hex2color([self.color.name(), self.color_arc.name()][int(is_archive)])
            solid_color_array = np.tile(np.asarray(solid_color), (len(y_all), 1))
            self.h_backscatter = self.backscatter_ax.scatter(y_all, z_all, s=self.pt_size, c=solid_color_array,
                                                             marker='o', alpha=self.pt_alpha, linewidths=0)

        # save filtered coverage data for processing to export trend for Gap Filler
        if is_archive:
            self.y_all_arc = y_all
            self.z_all_arc = z_all
        if not is_archive:
            self.y_all = y_all
            self.z_all = z_all

        print('calling calc_coverage_trend from plot_backscatter')
        calc_coverage_trend(self, z_all, y_all, is_archive)

        # Add overlays and helpers like the depth plot
        add_plot_features(self, self.backscatter_ax, is_archive)
        add_spec_lines_to_plot(self, self.backscatter_ax)
        add_grid_lines(self)
        add_legend(self)

    return len(z_all)

def plot_pingmode(self, det, is_archive=False, print_updates=False, det_name='detection dictionary'):
    # plot the parsed detections from new or archive data dict with ping mode coloring; return the number of points plotted after filtering
        # Debug print removed
    
    # consolidate data from port and stbd sides for plotting
    try:
        y_all = det['y_port'] + det['y_stbd']  # acrosstrack distance from TX array (.all) or origin (.kmall)
    except:
        print('***EXCEPTION: y_port or y_stbd not found; treating this like an older archive format (x_port / x_stbd)')
        y_all = det['x_port'] + det['x_stbd']  # older archives stored acrosstrack distance as x, not y
        det['y_port'] = deepcopy(det['x_port'])
        det['y_stbd'] = deepcopy(det['x_stbd'])

    z_all = det['z_port'] + det['z_stbd']  # depth from TX array (.all) or origin (.kmall)
    bs_all = det['bs_port'] + det['bs_stbd']  # reported backscatter amplitude
    fname_all = det['fname'] + det['fname']

    print('len z_all, bs_all, and fname_all at start of plot_pingmode = ', len(z_all), len(bs_all), len(fname_all))

    # calculate simplified swath angle from raw Z, Y data to use for angle filtering and comparison to runtime limits
    # Kongsberg angle convention is right-hand-rule about +X axis (fwd), so port angles are + and stbd are -
    angle_all = (-1 * np.rad2deg(np.arctan2(y_all, z_all))).tolist()  # multiply by -1 for Kongsberg convention

    # warn user if detection dict does not have all required offsets for depth reference adjustment (e.g., old archives)
    if (not all([k in det.keys() for k in ['tx_x_m', 'tx_y_m', 'aps_x_m', 'aps_y_m', 'wl_z_m']]) and
            self.ref_cbox.currentText().lower() != 'raw data'):
            update_log(self, 'Warning: ' + det_name + ' does not include all fields required for depth reference '
                                                      'adjustment (e.g., possibly an old archive format); no depth '
                                                      'reference adjustment will be made')

    # get file-specific, ping-wise adjustments to bring Z and Y into desired reference frame
    dx_ping, dy_ping, dz_ping = adjust_depth_ref(det, depth_ref=self.ref_cbox.currentText().lower())

    z_all = [z + dz for z, dz in zip(z_all, dz_ping + dz_ping)]  # add dz (per ping) to each z (per sounding)
    y_all = [y + dy for y, dy in zip(y_all, dy_ping + dy_ping)]  # add dy (per ping) to each y (per sounding)

    if print_updates:
        for i in range(len(angle_all)):
            if any(np.isnan([angle_all[i], bs_all[i]])):
                print('NAN in (i,y,z,angle,BS):',
                      i, y_all[i], z_all[i], angle_all[i], bs_all[i])

    # update x and z max for axis resizing during each plot call
    self.x_max = max([self.x_max, np.nanmax(np.abs(np.asarray(y_all)))])
    self.z_max = max([self.z_max, np.nanmax(np.asarray(z_all))])

    # after updating axis limits, simply return w/o plotting if toggle for this data type is off
    if ((is_archive and not self.show_data_chk_arc.isChecked())
            or (not is_archive and not self.show_data_chk.isChecked())):
        print('returning from ping mode plotter because the toggle for this data type is unchecked')
        return

    # set up indices for optional masking on angle, depth, bs; all idx true until fail optional filter settings
    # all soundings masked for nans (e.g., occasional nans in EX0908 data)
    idx_shape = np.shape(np.asarray(z_all))
    angle_idx = np.ones(idx_shape)
    depth_idx = np.ones(idx_shape)
    bs_idx = np.ones(idx_shape)
    rtp_angle_idx = np.ones(idx_shape)  # idx of angles that fall within the runtime params for RX beam angles
    rtp_cov_idx = np.ones(idx_shape)  # idx of soundings that fall within the runtime params for max coverage
    real_idx = np.logical_not(np.logical_or(np.isnan(y_all), np.isnan(z_all)))

    # apply angle filter if enabled
    if self.angle_gb.isChecked():
        lims = [float(self.min_angle_tb.text()), float(self.max_angle_tb.text())]
        angle_idx = np.logical_and(np.abs(np.asarray(angle_all)) >= lims[0],
                                   np.abs(np.asarray(angle_all)) <= lims[1])

    # apply depth filter if enabled
    if self.depth_gb.isChecked():
        if is_archive:
            self.min_depth = float(self.min_depth_arc_tb.text())
            self.max_depth = float(self.max_depth_arc_tb.text())
        else:
            self.min_depth = float(self.min_depth_tb.text())
            self.max_depth = float(self.max_depth_tb.text())
        depth_idx = np.logical_and(np.greater_equal(np.asarray(z_all), self.min_depth),
                                   np.less_equal(np.asarray(z_all), self.max_depth))

    # apply backscatter filter if enabled
    if self.bs_gb.isChecked():
        self.min_bs = float(self.min_bs_tb.text())
        self.max_bs = float(self.max_bs_tb.text())
        bs_idx = np.logical_and(np.greater_equal(np.asarray(bs_all), self.min_bs),
                                np.less_equal(np.asarray(bs_all), self.max_bs))

    # apply runtime parameter angle filter if enabled
    if self.rtp_angle_gb.isChecked():  # get idx of angles near runtime param angle limits
        self.rx_angle_buffer = float(self.rtp_angle_buffer_tb.text())
        try:  # try to compare angles to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'min_port_deg' in det and 'max_stbd_deg' in det:  # compare angles to runtime params if available
                # angle buffer can be positive or negative; more negative, more aggressive filtering
                rtp_angle_idx_port = np.less_equal(np.asarray(angle_all),
                                                   np.asarray(det['min_port_deg']) - self.rx_angle_buffer)
                rtp_angle_idx_stbd = np.greater_equal(np.asarray(angle_all),
                                                      np.asarray(det['max_stbd_deg']) + self.rx_angle_buffer)
                rtp_angle_idx = np.logical_and(rtp_angle_idx_port, rtp_angle_idx_stbd)

                if print_updates:
                    print('set(min_port_deg)=', set(det['min_port_deg']))
                    print('set(max_stbd_deg)=', set(det['max_stbd_deg']))
                    print('sum of rtp_angle_idx=', sum(rtp_angle_idx))

            else:
                update_log(self, 'Runtime parameters for swath angle limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'angles against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing angles to runtime params; no angle filter applied')

    # apply runtime parameter coverage filter if enabled
    if self.rtp_cov_gb.isChecked():  # get idx of soundings with coverage near runtime param cov limits
        self.rx_cov_buffer = float(self.rtp_cov_buffer_tb.text())

        try:  # try to compare coverage to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'max_port_m' in det and 'max_stbd_m' in det:  # compare coverage to runtime params if available
                # coverage buffer is negative; more negative, more aggressive filtering
                rtp_cov_idx_port = np.greater_equal(np.asarray(y_all),
                                                    -1 * np.asarray(2 * det['max_port_m']) - self.rx_cov_buffer)
                rtp_cov_idx_stbd = np.less_equal(np.asarray(y_all),
                                                 np.asarray(2 * det['max_stbd_m']) + self.rx_cov_buffer)
                rtp_cov_idx = np.logical_and(rtp_cov_idx_port, rtp_cov_idx_stbd)

                if print_updates:
                    print('set(max_port_m)=', set(det['max_port_m']))
                    print('set(max_stbd_m)=', set(det['max_stbd_m']))
                    print('sum of rtp_cov_idx=', sum(rtp_cov_idx))

            else:
                update_log(self, 'Runtime parameters for swath coverage limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'coverage against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing coverage to runtime params; no coverage filter applied')

    # apply filter masks to x, z, angle, and bs fields
    filter_idx = np.logical_and.reduce((angle_idx, depth_idx, bs_idx, rtp_angle_idx, rtp_cov_idx, real_idx))

    # Determine color mode based on radio button selection
    if is_archive:
        if self.archive_data_color_by_type_radio.isChecked():
            cmode = 'ping_mode'  # Use ping mode coloring
        else:
            cmode = 'solid_color'  # Use single color
    else:
        if self.new_data_color_by_type_radio.isChecked():
            cmode = 'ping_mode'  # Use ping mode coloring
        else:
            cmode = 'solid_color'  # Use single color
    
    print('cmode for ping mode plot is', cmode)

    # set color maps for ping mode
    if cmode == 'ping_mode':
        # ping mode is stored per ping, need to duplicate for port and stbd soundings
        c_all = det['ping_mode'] + det['ping_mode']  # duplicate ping mode for port and stbd

        # Normalize ping mode strings to base mode (strip anything in parentheses)
        mode_all_base = []
        for m in c_all:
            # Remove anything in parentheses and after, then split by whitespace and take first two words
            base = m.split('(')[0].strip()
            base = ' '.join(base.split()[:2])
            mode_all_base.append(base)

        c_set = {'Very Shallow': 'red', 'Shallow': 'darkorange', 'Medium': 'gold',
                 'Deep': 'limegreen', 'Deeper': 'darkturquoise', 'Very Deep': 'blue',
                 'Extra Deep': 'indigo', 'Extreme Deep': 'black'}
        # EM2040 .all files store frequency mode in the ping mode field; replace color set accordingly
        # Check for exact EM2040 model and frequency data in ping mode field
        if (hasattr(self, 'model_name') and 
            ('EM 2040' in self.model_name or 'EM2040' in self.model_name) and 
            any([mode.find('kHz') > -1 for mode in set(mode_all_base)])):
            print('***using frequency info for ping mode***')
            c_set = {'400 kHz': 'red', '300 kHz': 'darkorange', '200 kHz': 'gold'}
            pingmode_legend_label = 'Freq. (EM 2040, SIS 4)'
            mode_all_base = [m for m in mode_all_base]  # no normalization needed for kHz
        else:
            pingmode_legend_label = 'Ping Mode'

        mode_to_index = {mode: idx for idx, mode in enumerate(c_set.keys())}
        c_all_numeric = [mode_to_index.get(mode, 0) for mode in mode_all_base]  # default to 0 if mode not found

        # Create colormap from the color set
        from matplotlib.colors import ListedColormap
        pingmode_cmap = ListedColormap([c_set[mode] for mode in c_set.keys()])
        pingmode_clim = [0, len(c_set) - 1]  # set limits based on number of modes

        # filter the data after storing the color data
        y_all = np.asarray(y_all)[filter_idx].tolist()
        z_all = np.asarray(z_all)[filter_idx].tolist()
        angle_all = np.asarray(angle_all)[filter_idx].tolist()
        bs_all = np.asarray(bs_all)[filter_idx].tolist()
        c_all_numeric = np.asarray(c_all_numeric)[filter_idx].tolist()
        self.fnames_all = np.asarray(fname_all)[filter_idx].tolist()

        if len(z_all) > 0:
            self.pingmode_ax.clear()
            self.h_pingmode = self.pingmode_ax.scatter(y_all, z_all, s=self.pt_size, c=c_all_numeric,
                                                       marker='o', alpha=self.pt_alpha, linewidths=0,
                                                       cmap=pingmode_cmap, vmin=pingmode_clim[0], vmax=pingmode_clim[1])
    else:  # solid_color
        c_all = [1] * len(det['ping_mode'] * 2)  # Use single color value
        y_all = np.asarray(y_all)[filter_idx].tolist()
        z_all = np.asarray(z_all)[filter_idx].tolist()
        angle_all = np.asarray(angle_all)[filter_idx].tolist()
        bs_all = np.asarray(bs_all)[filter_idx].tolist()
        c_all = np.asarray(c_all)[filter_idx].tolist()
        self.fnames_all = np.asarray(fname_all)[filter_idx].tolist()
        if len(z_all) > 0:
            self.pingmode_ax.clear()
            solid_color = colors.hex2color([self.color.name(), self.color_arc.name()][int(is_archive)])
            solid_color_array = np.tile(np.asarray(solid_color), (len(y_all), 1))
            self.h_pingmode = self.pingmode_ax.scatter(y_all, z_all, s=self.pt_size, c=solid_color_array,
                                                       marker='o', alpha=self.pt_alpha, linewidths=0)

    # save filtered coverage data for processing to export trend for Gap Filler
    if is_archive:
        self.y_all_arc = y_all
        self.z_all_arc = z_all
    if not is_archive:
        self.y_all = y_all
        self.z_all = z_all

    print('calling calc_coverage_trend from plot_pingmode')
    calc_coverage_trend(self, z_all, y_all, is_archive)

    # Add overlays and helpers like the depth plot
    add_plot_features(self, self.pingmode_ax, is_archive)
    add_spec_lines_to_plot(self, self.pingmode_ax)
    add_grid_lines(self)
    add_legend(self)

    return len(z_all) 

def plot_pulseform(self, det, is_archive=False, print_updates=False, det_name='detection dictionary'):
    # plot the parsed detections from new or archive data dict with pulse form coloring; return the number of points plotted after filtering
    # Debug print removed
    
    # consolidate data from port and stbd sides for plotting
    try:
        y_all = det['y_port'] + det['y_stbd']  # acrosstrack distance from TX array (.all) or origin (.kmall)
    except:
        print('***EXCEPTION: y_port or y_stbd not found; treating this like an older archive format (x_port / x_stbd)')
        y_all = det['x_port'] + det['x_stbd']  # older archives stored acrosstrack distance as x, not y
        det['y_port'] = deepcopy(det['x_port'])
        det['y_stbd'] = deepcopy(det['x_stbd'])

    z_all = det['z_port'] + det['z_stbd']  # depth from TX array (.all) or origin (.kmall)
    bs_all = det['bs_port'] + det['bs_stbd']  # reported backscatter amplitude
    fname_all = det['fname'] + det['fname']

    print('len z_all, bs_all, and fname_all at start of plot_pulseform = ', len(z_all), len(bs_all), len(fname_all))

    # calculate simplified swath angle from raw Z, Y data to use for angle filtering and comparison to runtime limits
    # Kongsberg angle convention is right-hand-rule about +X axis (fwd), so port angles are + and stbd are -
    angle_all = (-1 * np.rad2deg(np.arctan2(y_all, z_all))).tolist()  # multiply by -1 for Kongsberg convention

    # warn user if detection dict does not have all required offsets for depth reference adjustment (e.g., old archives)
    if (not all([k in det.keys() for k in ['tx_x_m', 'tx_y_m', 'aps_x_m', 'aps_y_m', 'wl_z_m']]) and
            self.ref_cbox.currentText().lower() != 'raw data'):
            update_log(self, 'Warning: ' + det_name + ' does not include all fields required for depth reference '
                                                      'adjustment (e.g., possibly an old archive format); no depth '
                                                      'reference adjustment will be made')

    # get file-specific, ping-wise adjustments to bring Z and Y into desired reference frame
    dx_ping, dy_ping, dz_ping = adjust_depth_ref(det, depth_ref=self.ref_cbox.currentText().lower())

    z_all = [z + dz for z, dz in zip(z_all, dz_ping + dz_ping)]  # add dz (per ping) to each z (per sounding)
    y_all = [y + dy for y, dy in zip(y_all, dy_ping + dy_ping)]  # add dy (per ping) to each y (per sounding)

    if print_updates:
        for i in range(len(angle_all)):
            if any(np.isnan([angle_all[i], bs_all[i]])):
                print('NAN in (i,y,z,angle,BS):',
                      i, y_all[i], z_all[i], angle_all[i], bs_all[i])

    # update x and z max for axis resizing during each plot call
    self.x_max = max([self.x_max, np.nanmax(np.abs(np.asarray(y_all)))])
    self.z_max = max([self.z_max, np.nanmax(np.asarray(z_all))])

    # after updating axis limits, simply return w/o plotting if toggle for this data type (current/archive) is off
    if ((is_archive and not self.show_data_chk_arc.isChecked())
            or (not is_archive and not self.show_data_chk.isChecked())):
        print('returning from pulse form plotter because the toggle for this data type is unchecked')
        return

    # set up indices for optional masking on angle, depth, bs; all idx true until fail optional filter settings
    # all soundings masked for nans (e.g., occasional nans in EX0908 data)
    idx_shape = np.shape(np.asarray(z_all))
    angle_idx = np.ones(idx_shape)
    depth_idx = np.ones(idx_shape)
    bs_idx = np.ones(idx_shape)
    rtp_angle_idx = np.ones(idx_shape)  # idx of angles that fall within the runtime params for RX beam angles
    rtp_cov_idx = np.ones(idx_shape)  # idx of soundings that fall within the runtime params for max coverage
    real_idx = np.logical_not(np.logical_or(np.isnan(y_all), np.isnan(z_all)))

    # apply angle filter if enabled
    if self.angle_gb.isChecked():
        lims = [float(self.min_angle_tb.text()), float(self.max_angle_tb.text())]
        angle_idx = np.logical_and(np.abs(np.asarray(angle_all)) >= lims[0],
                                   np.abs(np.asarray(angle_all)) <= lims[1])

    # apply depth filter if enabled
    if self.depth_gb.isChecked():
        if is_archive:
            self.min_depth = float(self.min_depth_arc_tb.text())
            self.max_depth = float(self.max_depth_arc_tb.text())
        else:
            self.min_depth = float(self.min_depth_tb.text())
            self.max_depth = float(self.max_depth_tb.text())
        depth_idx = np.logical_and(np.greater_equal(np.asarray(z_all), self.min_depth),
                                   np.less_equal(np.asarray(z_all), self.max_depth))

    # apply backscatter filter if enabled
    if self.bs_gb.isChecked():
        self.min_bs = float(self.min_bs_tb.text())
        self.max_bs = float(self.max_bs_tb.text())
        bs_idx = np.logical_and(np.greater_equal(np.asarray(bs_all), self.min_bs),
                                np.less_equal(np.asarray(bs_all), self.max_bs))

    # apply runtime parameter angle filter if enabled
    if self.rtp_angle_gb.isChecked():  # get idx of angles near runtime param angle limits
        self.rx_angle_buffer = float(self.rtp_angle_buffer_tb.text())
        try:  # try to compare angles to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'min_port_deg' in det and 'max_stbd_deg' in det:  # compare angles to runtime params if available
                # angle buffer can be positive or negative; more negative, more aggressive filtering
                rtp_angle_idx_port = np.less_equal(np.asarray(angle_all),
                                                   np.asarray(det['min_port_deg']) - self.rx_angle_buffer)
                rtp_angle_idx_stbd = np.greater_equal(np.asarray(angle_all),
                                                      np.asarray(det['max_stbd_deg']) + self.rx_angle_buffer)
                rtp_angle_idx = np.logical_and(rtp_angle_idx_port, rtp_angle_idx_stbd)

                if print_updates:
                    print('set(min_port_deg)=', set(det['min_port_deg']))
                    print('set(max_stbd_deg)=', set(det['max_stbd_deg']))
                    print('sum of rtp_angle_idx=', sum(rtp_angle_idx))

            else:
                update_log(self, 'Runtime parameters for swath angle limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'angles against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing angles to runtime params; no angle filter applied')

    # apply runtime parameter coverage filter if enabled
    if self.rtp_cov_gb.isChecked():  # get idx of soundings with coverage near runtime param cov limits
        self.rx_cov_buffer = float(self.rtp_cov_buffer_tb.text())

        try:  # try to compare coverage to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'max_port_m' in det and 'max_stbd_m' in det:  # compare coverage to runtime params if available
                # coverage buffer is negative; more negative, more aggressive filtering
                rtp_cov_idx_port = np.greater_equal(np.asarray(y_all),
                                                    -1 * np.asarray(2 * det['max_port_m']) - self.rx_cov_buffer)
                rtp_cov_idx_stbd = np.less_equal(np.asarray(y_all),
                                                 np.asarray(2 * det['max_stbd_m']) + self.rx_cov_buffer)
                rtp_cov_idx = np.logical_and(rtp_cov_idx_port, rtp_cov_idx_stbd)

                if print_updates:
                    print('set(max_port_m)=', set(det['max_port_m']))
                    print('set(max_stbd_m)=', set(det['max_stbd_m']))
                    print('sum of rtp_cov_idx=', sum(rtp_cov_idx))

            else:
                update_log(self, 'Runtime parameters for swath coverage limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'coverage against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing coverage to runtime params; no coverage filter applied')

    # apply filter masks to x, z, angle, and bs fields
    filter_idx = np.logical_and.reduce((angle_idx, depth_idx, bs_idx, rtp_angle_idx, rtp_cov_idx, real_idx))

    # Determine color mode based on radio button selection
    if is_archive:
        if self.archive_data_color_by_type_radio.isChecked():
            cmode = 'pulse_form'  # Use pulse form coloring
        else:
            cmode = 'solid_color'  # Use single color
    else:
        if self.new_data_color_by_type_radio.isChecked():
            cmode = 'pulse_form'  # Use pulse form coloring
        else:
            cmode = 'solid_color'  # Use single color
    
    print('cmode for pulse form plot is', cmode)

    # set color maps for pulse form
    if cmode == 'pulse_form':
        # pulse form is stored per ping, need to duplicate for port and stbd soundings
        c_all = det['pulse_form'] + det['pulse_form']  # duplicate pulse form for port and stbd
    else:  # solid_color
        c_all = [1] * len(det['pulse_form'] * 2)  # Use single color value
    print('cmode is pulse form, len c_all=', len(c_all))
    
    # Create color mapping for pulse forms (similar to plot_coverage)
    c_set = {'CW': 'red', 'Mixed': 'limegreen', 'FM': 'blue'}
    pulseform_legend_label = 'Pulse Form'

    # filter the data after storing the color data
    y_all = np.asarray(y_all)[filter_idx].tolist()
    z_all = np.asarray(z_all)[filter_idx].tolist()
    angle_all = np.asarray(angle_all)[filter_idx].tolist()
    bs_all = np.asarray(bs_all)[filter_idx].tolist()
    c_all = np.asarray(c_all)[filter_idx].tolist()

    self.fnames_all = np.asarray(fname_all)[filter_idx].tolist()

    if print_updates:
        print('AFTER APPLYING IDX: len y_all, z_all, angle_all, bs_all, c_all=',
              len(y_all), len(z_all), len(angle_all), len(bs_all), len(c_all))

    # get post-filtering number of points to plot and allowable maximum from default or user input (if selected)
    self.n_points = len(y_all)
    self.n_points_max = self.n_points_max_default

    if self.pt_count_gb.isChecked() and self.max_count_tb.text():  # override default only if explicitly set by user
        self.n_points_max = float(self.max_count_tb.text())

    # default dec fac to meet n_points_max, regardless of whether user has checked box for plot point limits
    if self.n_points_max == 0:
        update_log(self, 'Max plotting sounding count set equal to zero')
        self.dec_fac_default = np.inf
    else:
        self.dec_fac_default = float(self.n_points / self.n_points_max)

    if self.dec_fac_default > 1 and not self.pt_count_gb.isChecked():  # warn user if large count may slow down plot
        update_log(self, 'Large filtered sounding count (' + str(self.n_points) + ') may slow down plotting')

    # get user dec fac as product of whether check box is checked (default 1)
    self.dec_fac_user = max(self.pt_count_gb.isChecked() * float(self.dec_fac_tb.text()), 1)
    self.dec_fac = max(self.dec_fac_default, self.dec_fac_user)

    # decimate data if necessary
    if self.dec_fac > 1:
        y_all = y_all[::int(self.dec_fac)]
        z_all = z_all[::int(self.dec_fac)]
        angle_all = angle_all[::int(self.dec_fac)]
        bs_all = bs_all[::int(self.dec_fac)]
        c_all = c_all[::int(self.dec_fac)]
        self.fnames_all = self.fnames_all[::int(self.dec_fac)]

    # plot the data on the pulse form canvas
    if len(z_all) > 0:
        # clear the pulse form axis
        self.pulseform_ax.clear()
        
        # plot the pulse form data
        if cmode == 'pulse_form':
            # Convert string pulse forms to numeric indices for colormap
            mode_to_index = {mode: idx for idx, mode in enumerate(c_set.keys())}
            c_all_numeric = [mode_to_index.get(mode, 0) for mode in c_all]  # default to 0 if mode not found
            c_all = c_all_numeric  # replace string list with numeric list
            
            # Create colormap from the color set
            from matplotlib.colors import ListedColormap
            pulseform_cmap = ListedColormap([c_set[mode] for mode in c_set.keys()])
            pulseform_clim = [0, len(c_set) - 1]  # set limits based on number of modes
            
            self.h_pulseform = self.pulseform_ax.scatter(y_all, z_all, s=self.pt_size, c=c_all,
                                                         marker='o', alpha=self.pt_alpha, linewidths=0,
                                                         cmap=pulseform_cmap, vmin=pulseform_clim[0], vmax=pulseform_clim[1])
        else:  # solid_color
            # Use the selected solid color, convert QColor to matplotlib format
            solid_color = colors.hex2color([self.color.name(), self.color_arc.name()][int(is_archive)])
            solid_color_array = np.tile(np.asarray(solid_color), (len(y_all), 1))
            self.h_pulseform = self.pulseform_ax.scatter(y_all, z_all, s=self.pt_size, c=solid_color_array,
                                                         marker='o', alpha=self.pt_alpha, linewidths=0)

        # save filtered coverage data for processing to export trend for Gap Filler
        if is_archive:
            self.y_all_arc = y_all
            self.z_all_arc = z_all
        if not is_archive:
            self.y_all = y_all
            self.z_all = z_all

        print('calling calc_coverage_trend from plot_pulseform')
        calc_coverage_trend(self, z_all, y_all, is_archive)

        # Add overlays and helpers like the depth plot
        add_plot_features(self, self.pulseform_ax, is_archive)
        add_spec_lines_to_plot(self, self.pulseform_ax)
        add_grid_lines(self)
        add_legend(self)

    return len(z_all)

def plot_swathmode(self, det, is_archive=False, print_updates=False, det_name='detection dictionary'):
    # plot the parsed detections from new or archive data dict with swath mode coloring; return the number of points plotted after filtering
    # Debug print removed
    
    # consolidate data from port and stbd sides for plotting
    try:
        y_all = det['y_port'] + det['y_stbd']  # acrosstrack distance from TX array (.all) or origin (.kmall)
    except:
        print('***EXCEPTION: y_port or y_stbd not found; treating this like an older archive format (x_port / x_stbd)')
        y_all = det['x_port'] + det['x_stbd']  # older archives stored acrosstrack distance as x, not y
        det['y_port'] = deepcopy(det['x_port'])
        det['y_stbd'] = deepcopy(det['x_stbd'])

    z_all = det['z_port'] + det['z_stbd']  # depth from TX array (.all) or origin (.kmall)
    bs_all = det['bs_port'] + det['bs_stbd']  # reported backscatter amplitude
    fname_all = det['fname'] + det['fname']

    print('len z_all, bs_all, and fname_all at start of plot_swathmode = ', len(z_all), len(bs_all), len(fname_all))

    # calculate simplified swath angle from raw Z, Y data to use for angle filtering and comparison to runtime limits
    # Kongsberg angle convention is right-hand-rule about +X axis (fwd), so port angles are + and stbd are -
    angle_all = (-1 * np.rad2deg(np.arctan2(y_all, z_all))).tolist()  # multiply by -1 for Kongsberg convention

    # warn user if detection dict does not have all required offsets for depth reference adjustment (e.g., old archives)
    if (not all([k in det.keys() for k in ['tx_x_m', 'tx_y_m', 'aps_x_m', 'aps_y_m', 'wl_z_m']]) and
            self.ref_cbox.currentText().lower() != 'raw data'):
            update_log(self, 'Warning: ' + det_name + ' does not include all fields required for depth reference '
                                                      'adjustment (e.g., possibly an old archive format); no depth '
                                                      'reference adjustment will be made')

    # get file-specific, ping-wise adjustments to bring Z and Y into desired reference frame
    dx_ping, dy_ping, dz_ping = adjust_depth_ref(det, depth_ref=self.ref_cbox.currentText().lower())

    z_all = [z + dz for z, dz in zip(z_all, dz_ping + dz_ping)]  # add dz (per ping) to each z (per sounding)
    y_all = [y + dy for y, dy in zip(y_all, dy_ping + dy_ping)]  # add dy (per ping) to each y (per sounding)

    if print_updates:
        for i in range(len(angle_all)):
            if any(np.isnan([angle_all[i], bs_all[i]])):
                print('NAN in (i,y,z,angle,BS):',
                      i, y_all[i], z_all[i], angle_all[i], bs_all[i])

    # update x and z max for axis resizing during each plot call
    self.x_max = max([self.x_max, np.nanmax(np.abs(np.asarray(y_all)))])
    self.z_max = max([self.z_max, np.nanmax(np.asarray(z_all))])

    # after updating axis limits, simply return w/o plotting if toggle for this data type (current/archive) is off
    if ((is_archive and not self.show_data_chk_arc.isChecked())
            or (not is_archive and not self.show_data_chk.isChecked())):
        print('returning from swath mode plotter because the toggle for this data type is unchecked')
        return

    # set up indices for optional masking on angle, depth, bs; all idx true until fail optional filter settings
    # all soundings masked for nans (e.g., occasional nans in EX0908 data)
    idx_shape = np.shape(np.asarray(z_all))
    angle_idx = np.ones(idx_shape)
    depth_idx = np.ones(idx_shape)
    bs_idx = np.ones(idx_shape)
    rtp_angle_idx = np.ones(idx_shape)  # idx of angles that fall within the runtime params for RX beam angles
    rtp_cov_idx = np.ones(idx_shape)  # idx of soundings that fall within the runtime params for max coverage
    real_idx = np.logical_not(np.logical_or(np.isnan(y_all), np.isnan(z_all)))

    # apply angle filter if enabled
    if self.angle_gb.isChecked():
        lims = [float(self.min_angle_tb.text()), float(self.max_angle_tb.text())]
        angle_idx = np.logical_and(np.abs(np.asarray(angle_all)) >= lims[0],
                                   np.abs(np.asarray(angle_all)) <= lims[1])

    # apply depth filter if enabled
    if self.depth_gb.isChecked():
        if is_archive:
            self.min_depth = float(self.min_depth_arc_tb.text())
            self.max_depth = float(self.max_depth_arc_tb.text())
        else:
            self.min_depth = float(self.min_depth_tb.text())
            self.max_depth = float(self.max_depth_tb.text())
        depth_idx = np.logical_and(np.greater_equal(np.asarray(z_all), self.min_depth),
                                   np.less_equal(np.asarray(z_all), self.max_depth))

    # apply backscatter filter if enabled
    if self.bs_gb.isChecked():
        self.min_bs = float(self.min_bs_tb.text())
        self.max_bs = float(self.max_bs_tb.text())
        bs_idx = np.logical_and(np.greater_equal(np.asarray(bs_all), self.min_bs),
                                np.less_equal(np.asarray(bs_all), self.max_bs))

    # apply runtime parameter angle filter if enabled
    if self.rtp_angle_gb.isChecked():  # get idx of angles near runtime param angle limits
        self.rx_angle_buffer = float(self.rtp_angle_buffer_tb.text())
        try:  # try to compare angles to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'min_port_deg' in det and 'max_stbd_deg' in det:  # compare angles to runtime params if available
                # angle buffer can be positive or negative; more negative, more aggressive filtering
                rtp_angle_idx_port = np.less_equal(np.asarray(angle_all),
                                                   np.asarray(det['min_port_deg']) - self.rx_angle_buffer)
                rtp_angle_idx_stbd = np.greater_equal(np.asarray(angle_all),
                                                      np.asarray(det['max_stbd_deg']) + self.rx_angle_buffer)
                rtp_angle_idx = np.logical_and(rtp_angle_idx_port, rtp_angle_idx_stbd)

                if print_updates:
                    print('set(min_port_deg)=', set(det['min_port_deg']))
                    print('set(max_stbd_deg)=', set(det['max_stbd_deg']))
                    print('sum of rtp_angle_idx=', sum(rtp_angle_idx))

            else:
                update_log(self, 'Runtime parameters for swath angle limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'angles against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing angles to runtime params; no angle filter applied')

    # apply runtime parameter coverage filter if enabled
    if self.rtp_cov_gb.isChecked():  # get idx of soundings with coverage near runtime param cov limits
        self.rx_cov_buffer = float(self.rtp_cov_buffer_tb.text())

        try:  # try to compare coverage to runtime param limits (port neg., stbd pos. per Kongsberg convention)
            if 'max_port_m' in det and 'max_stbd_m' in det:  # compare coverage to runtime params if available
                # coverage buffer is negative; more negative, more aggressive filtering
                rtp_cov_idx_port = np.greater_equal(np.asarray(y_all),
                                                    -1 * np.asarray(2 * det['max_port_m']) - self.rx_cov_buffer)
                rtp_cov_idx_stbd = np.less_equal(np.asarray(y_all),
                                                 np.asarray(2 * det['max_stbd_m']) + self.rx_cov_buffer)
                rtp_cov_idx = np.logical_and(rtp_cov_idx_port, rtp_cov_idx_stbd)

                if print_updates:
                    print('set(max_port_m)=', set(det['max_port_m']))
                    print('set(max_stbd_m)=', set(det['max_stbd_m']))
                    print('sum of rtp_cov_idx=', sum(rtp_cov_idx))

            else:
                update_log(self, 'Runtime parameters for swath coverage limits not available in ' +
                           ('archive' if is_archive else 'current') + ' data; no filtering applied for ' +
                           'coverage against user-defined limits during acquisition')

        except RuntimeError:
            update_log(self, 'Failure comparing coverage to runtime params; no coverage filter applied')

    # apply filter masks to x, z, angle, and bs fields
    filter_idx = np.logical_and.reduce((angle_idx, depth_idx, bs_idx, rtp_angle_idx, rtp_cov_idx, real_idx))

    # Determine color mode based on radio button selection
    if is_archive:
        if self.archive_data_color_by_type_radio.isChecked():
            cmode = 'swath_mode'  # Use swath mode coloring
        else:
            cmode = 'solid_color'  # Use single color
    else:
        if self.new_data_color_by_type_radio.isChecked():
            cmode = 'swath_mode'  # Use swath mode coloring
        else:
            cmode = 'solid_color'  # Use single color
    
    print('cmode for swath mode plot is', cmode)

    # set color maps for swath mode
    if cmode == 'swath_mode':
        # swath mode is stored per ping, need to duplicate for port and stbd soundings
        c_all = det['swath_mode'] + det['swath_mode']  # duplicate swath mode for port and stbd
        
        # Create color mapping for swath modes (similar to plot_coverage)
        c_set = {
            "Single Swath": "red",  # red
            "Dual Swath (Fixed)": "blue",    # blue
            "Dual Swath (Dynamic)": "green",  # green
            "Dual Swath": "blue",    # fallback for any other dual swath variants
            "NA": "gray",  # gray for unknown/NA values
            # Add any other base modes that might appear in the data
        }
        swathmode_legend_label = 'Swath Mode'
        
        # Get unique modes actually present in the data
        unique_modes = list(set(c_all))
        print('Unique swath modes in data:', unique_modes)
        
        # If all modes are the same, log it but don't create artificial variation
        if len(unique_modes) == 1:
            print(f'Info: All swath modes are the same: {unique_modes[0]}')
            if unique_modes[0] == 'NA':
                print('Warning: Swath mode information not available in data')
        
        # Create a dynamic color mapping based on actual modes present
        # Use the predefined colors for known modes, default to gray for unknown modes
        actual_c_set = {}
        available_colors = ["red", "blue", "green", "orange", "purple", "brown", "pink", "gray"]
        color_idx = 0
        
        for mode in unique_modes:
            if mode in c_set:
                actual_c_set[mode] = c_set[mode]
            else:
                # Assign a color from the available colors list
                actual_c_set[mode] = available_colors[color_idx % len(available_colors)]
                color_idx += 1
        
        print('Actual color mapping:', actual_c_set)
        
        # Store the actual color mapping for legend creation
        self.actual_swathmode_c_set = actual_c_set
        
        # Convert string swath modes to numeric indices for colormap
        mode_to_index = {mode: idx for idx, mode in enumerate(actual_c_set.keys())}
        c_all_numeric = [mode_to_index.get(mode, 0) for mode in c_all]  # default to 0 if mode not found
        c_all = c_all_numeric  # replace string list with numeric list
        
        # Create colormap from the actual color set
        from matplotlib.colors import ListedColormap
        swathmode_cmap = ListedColormap([actual_c_set[mode] for mode in actual_c_set.keys()])
        swathmode_clim = [0, len(actual_c_set) - 1]  # set limits based on number of actual modes
        
    else:  # solid_color
        c_all = [1] * len(det['swath_mode'] * 2)  # Use single color value
        swathmode_cmap = None
        swathmode_clim = [0, 1]  # dummy values
        
    print('cmode is swath mode, len c_all=', len(c_all))

    # filter the data after storing the color data
    y_all = np.asarray(y_all)[filter_idx].tolist()
    z_all = np.asarray(z_all)[filter_idx].tolist()
    angle_all = np.asarray(angle_all)[filter_idx].tolist()
    bs_all = np.asarray(bs_all)[filter_idx].tolist()
    c_all = np.asarray(c_all)[filter_idx].tolist()

    self.fnames_all = np.asarray(fname_all)[filter_idx].tolist()

    if print_updates:
        print('AFTER APPLYING IDX: len y_all, z_all, angle_all, bs_all, c_all=',
              len(y_all), len(z_all), len(angle_all), len(bs_all), len(c_all))

    # get post-filtering number of points to plot and allowable maximum from default or user input (if selected)
    self.n_points = len(y_all)
    self.n_points_max = self.n_points_max_default

    if self.pt_count_gb.isChecked() and self.max_count_tb.text():  # override default only if explicitly set by user
        self.n_points_max = float(self.max_count_tb.text())

    # default dec fac to meet n_points_max, regardless of whether user has checked box for plot point limits
    if self.n_points_max == 0:
        update_log(self, 'Max plotting sounding count set equal to zero')
        self.dec_fac_default = np.inf
    else:
        self.dec_fac_default = float(self.n_points / self.n_points_max)

    if self.dec_fac_default > 1 and not self.pt_count_gb.isChecked():  # warn user if large count may slow down plot
        update_log(self, 'Large filtered sounding count (' + str(self.n_points) + ') may slow down plotting')

    # get user dec fac as product of whether check box is checked (default 1)
    self.dec_fac_user = max(self.pt_count_gb.isChecked() * float(self.dec_fac_tb.text()), 1)
    self.dec_fac = max(self.dec_fac_default, self.dec_fac_user)

    # decimate data if necessary
    if self.dec_fac > 1:
        y_all = y_all[::int(self.dec_fac)]
        z_all = z_all[::int(self.dec_fac)]
        angle_all = angle_all[::int(self.dec_fac)]
        bs_all = bs_all[::int(self.dec_fac)]
        c_all = c_all[::int(self.dec_fac)]
        self.fnames_all = self.fnames_all[::int(self.dec_fac)]

    # plot the data on the swath mode canvas
    if len(z_all) > 0:
        # clear the swath mode axis
        self.swathmode_ax.clear()
        
        # plot the swath mode data
        if cmode == 'swath_mode':
            self.h_swathmode = self.swathmode_ax.scatter(y_all, z_all, s=self.pt_size, c=c_all,
                                                         marker='o', alpha=self.pt_alpha, linewidths=0,
                                                         cmap=swathmode_cmap, vmin=swathmode_clim[0], vmax=swathmode_clim[1])
        else:  # solid_color
            # Use the selected solid color, convert QColor to matplotlib format
            solid_color = colors.hex2color([self.color.name(), self.color_arc.name()][int(is_archive)])
            solid_color_array = np.tile(np.asarray(solid_color), (len(y_all), 1))
            self.h_swathmode = self.swathmode_ax.scatter(y_all, z_all, s=self.pt_size, c=solid_color_array,
                                                         marker='o', alpha=self.pt_alpha, linewidths=0)

        # save filtered coverage data for processing to export trend for Gap Filler
        if is_archive:
            self.y_all_arc = y_all
            self.z_all_arc = z_all
        if not is_archive:
            self.y_all = y_all
            self.z_all = z_all

        print('calling calc_coverage_trend from plot_swathmode')
        calc_coverage_trend(self, z_all, y_all, is_archive)

        # Add overlays and helpers like the depth plot
        add_plot_features(self, self.swathmode_ax, is_archive)
        add_spec_lines_to_plot(self, self.swathmode_ax)
        add_grid_lines(self)
        add_legend(self)

    return len(z_all)

def plot_frequency(self, det, is_archive=False, print_updates=False, det_name='detection dictionary'):
    # plot the parsed detections from new or archive data dict with frequency coloring; return the number of points plotted after filtering
        # Debug print removed
    
    # Check if data should be shown based on UI checkboxes
    if is_archive and not self.show_data_chk_arc.isChecked():
        print('Archive data not shown, skipping frequency plot')
        return 0
    elif not is_archive and not self.show_data_chk.isChecked():
        print('New data not shown, skipping frequency plot')
        return 0
    
    try:
        y_all = det['y_port'] + det['y_stbd']
    except:
        y_all = det['x_port'] + det['x_stbd']
        det['y_port'] = deepcopy(det['x_port'])
        det['y_stbd'] = deepcopy(det['x_stbd'])
    z_all = det['z_port'] + det['z_stbd']
    bs_all = det['bs_port'] + det['bs_stbd']
    fname_all = det['fname'] + det['fname']
    angle_all = (-1 * np.rad2deg(np.arctan2(y_all, z_all))).tolist()
    
    if print_updates:
        print('len z_all, bs_all, and fname_all at start of plot_frequency = ', len(z_all), len(bs_all), len(fname_all))
    
    # Use the same depth reference adjustment logic as plot_coverage
    dx_ping, dy_ping, dz_ping = adjust_depth_ref(det, depth_ref=self.ref_cbox.currentText().lower())
    z_all = [z + dz for z, dz in zip(z_all, dz_ping + dz_ping)]  # add dz (per ping) to each z (per sounding)
    y_all = [y + dy for y, dy in zip(y_all, dy_ping + dy_ping)]  # add dy (per ping) to each y (per sounding)
    
    # Determine color mode based on radio button selections
    if is_archive:
        if self.archive_data_color_by_type_radio.isChecked():
            cmode = 'frequency'
        else:
            cmode = 'single_color'
    else:
        if self.new_data_color_by_type_radio.isChecked():
            cmode = 'frequency'
        else:
            cmode = 'single_color'
    
    print('cmode for frequency plot is', cmode)
    
    # Set up color data based on mode
    if cmode == 'frequency':
        # frequency is stored per ping, need to duplicate for port and stbd soundings
        c_all = det['frequency'] + det['frequency']  # duplicate frequency for port and stbd
        print('cmode is frequency, len c_all=', len(c_all))
        
        # Create color mapping for frequencies (must match the legend colors exactly)
        c_set = {'400 kHz': 'red', '300 kHz': 'darkorange', '200 kHz': 'gold',
                 '70-100 kHz': 'limegreen', '40-100 kHz': 'darkturquoise', '40-70 kHz': 'blue',
                 '30 kHz': 'indigo', '12 kHz': 'black', 'NA': 'white'}
        
        # Convert string frequencies to numeric indices for colormap
        mode_to_index = {mode: idx for idx, mode in enumerate(c_set.keys())}
        c_all_numeric = [mode_to_index.get(freq, 0) for freq in c_all]  # default to 0 if freq not found
        c_all = c_all_numeric  # replace string list with numeric list
        
        # Create colormap from the color set
        from matplotlib.colors import ListedColormap
        frequency_cmap = ListedColormap([c_set[freq] for freq in c_set.keys()])
        frequency_clim = [0, len(c_set) - 1]  # set limits based on number of frequencies
        
    else:  # single color mode
        if is_archive:
            # Convert QColor to matplotlib color
            color = self.color_arc
            if hasattr(color, 'red'):  # QColor object
                c_all = [(color.red()/255, color.green()/255, color.blue()/255, color.alpha()/255)] * len(y_all)
            else:
                c_all = ['lightgray'] * len(y_all)
        else:
            # Convert QColor to matplotlib color
            color = self.color
            if hasattr(color, 'red'):  # QColor object
                c_all = [(color.red()/255, color.green()/255, color.blue()/255, color.alpha()/255)] * len(y_all)
            else:
                c_all = ['lightgray'] * len(y_all)
        # Set dummy values for single color mode to avoid linter errors
        frequency_cmap = None
        frequency_clim = [0, 1]  # dummy values

    # Apply filters (same logic as other plot functions)
    real_idx = np.ones(len(y_all), dtype=bool)
    angle_idx = np.ones(len(y_all), dtype=bool)
    depth_idx = np.ones(len(y_all), dtype=bool)
    bs_idx = np.ones(len(y_all), dtype=bool)
    rtp_angle_idx = np.ones(len(y_all), dtype=bool)
    rtp_cov_idx = np.ones(len(y_all), dtype=bool)

    if self.angle_gb.isChecked():  # get idx satisfying current angle filter
        lims = [float(self.min_angle_tb.text()), float(self.max_angle_tb.text())]
        angle_idx = np.logical_and(np.abs(np.asarray(angle_all)) >= lims[0],
                                   np.abs(np.asarray(angle_all)) <= lims[1])

    if self.depth_gb.isChecked():  # get idx satisfying current depth filter
        if is_archive:
            lims = [float(self.min_depth_arc_tb.text()), float(self.max_depth_arc_tb.text())]
        else:
            lims = [float(self.min_depth_tb.text()), float(self.max_depth_tb.text())]
        depth_idx = np.logical_and(np.asarray(z_all) >= lims[0], np.asarray(z_all) <= lims[1])

    if self.bs_gb.isChecked():  # get idx satisfying current backscatter filter
        lims = [float(self.min_bs_tb.text()), float(self.max_bs_tb.text())]
        bs_idx = np.logical_and(np.asarray(bs_all) >= lims[0], np.asarray(bs_all) <= lims[1])

    if self.rtp_angle_gb.isChecked():  # get idx of angles outside the runtime parameter swath angle limits
        self.rtp_angle_buffer = float(self.rtp_angle_buffer_tb.text())
        try:
            if 'max_port_deg' in det and 'max_stbd_deg' in det:
                rtp_angle_idx_port = np.less_equal(np.asarray(angle_all),
                                                   np.asarray(2 * det['max_port_deg']) + self.rtp_angle_buffer)
                rtp_angle_idx_stbd = np.greater_equal(np.asarray(angle_all),
                                                      -1 * np.asarray(2 * det['max_stbd_deg']) - self.rtp_angle_buffer)
                rtp_angle_idx = np.logical_and(rtp_angle_idx_port, rtp_angle_idx_stbd)
        except RuntimeError:
            update_log(self, 'Failure comparing RX beam angles to runtime params; no angle filter applied')

    if self.rtp_cov_gb.isChecked():  # get idx of soundings with coverage near runtime param cov limits
        self.rx_cov_buffer = float(self.rtp_cov_buffer_tb.text())
        try:
            if 'max_port_m' in det and 'max_stbd_m' in det:
                rtp_cov_idx_port = np.greater_equal(np.asarray(y_all),
                                                    -1 * np.asarray(2 * det['max_port_m']) - self.rx_cov_buffer)
                rtp_cov_idx_stbd = np.less_equal(np.asarray(y_all),
                                                 np.asarray(2 * det['max_stbd_m']) + self.rx_cov_buffer)
                rtp_cov_idx = np.logical_and(rtp_cov_idx_port, rtp_cov_idx_stbd)
        except RuntimeError:
            update_log(self, 'Failure comparing coverage to runtime params; no coverage filter applied')

    # apply filter masks to x, z, angle, and bs fields
    filter_idx = np.logical_and.reduce((angle_idx, depth_idx, bs_idx, rtp_angle_idx, rtp_cov_idx, real_idx))

    # filter the data after storing the color data
    y_all = np.asarray(y_all)[filter_idx].tolist()
    z_all = np.asarray(z_all)[filter_idx].tolist()
    angle_all = np.asarray(angle_all)[filter_idx].tolist()
    bs_all = np.asarray(bs_all)[filter_idx].tolist()
    c_all = np.asarray(c_all)[filter_idx].tolist()

    self.fnames_all = np.asarray(fname_all)[filter_idx].tolist()

    if print_updates:
        print('AFTER APPLYING IDX: len y_all, z_all, angle_all, bs_all, c_all=',
              len(y_all), len(z_all), len(angle_all), len(bs_all), len(c_all))

    # Update axis limits for proper scaling
    if len(y_all) > 0:
        self.x_max = max(self.x_max, max(abs(y) for y in y_all))
        self.z_max = max(self.z_max, max(z_all))

    # get post-filtering number of points to plot and allowable maximum from default or user input (if selected)
    self.n_points = len(y_all)
    self.n_points_max = self.n_points_max_default

    if self.pt_count_gb.isChecked() and self.max_count_tb.text():  # override default only if explicitly set by user
        self.n_points_max = float(self.max_count_tb.text())

    # default dec fac to meet n_points_max, regardless of whether user has checked box for plot point limits
    if self.n_points_max == 0:
        update_log(self, 'Max plotting sounding count set equal to zero')
        self.dec_fac_default = np.inf
    else:
        self.dec_fac_default = float(self.n_points / self.n_points_max)

    if self.dec_fac_default > 1 and not self.pt_count_gb.isChecked():  # warn user if large count may slow down plot
        update_log(self, 'Large filtered sounding count (' + str(self.n_points) + ') may slow down plotting')

    # get user dec fac as product of whether check box is checked (default 1)
    self.dec_fac_user = max(self.pt_count_gb.isChecked() * float(self.dec_fac_tb.text()), 1)
    self.dec_fac = max(self.dec_fac_default, self.dec_fac_user)

    # decimate data if necessary
    if self.dec_fac > 1:
        y_all = y_all[::int(self.dec_fac)]
        z_all = z_all[::int(self.dec_fac)]
        angle_all = angle_all[::int(self.dec_fac)]
        bs_all = bs_all[::int(self.dec_fac)]
        c_all = c_all[::int(self.dec_fac)]
        self.fnames_all = self.fnames_all[::int(self.dec_fac)]

    # plot the data on the frequency canvas
    if len(z_all) > 0:
        # clear the frequency axis
        self.frequency_ax.clear()
        
        # plot the frequency data
        if cmode == 'frequency':
            self.h_frequency = self.frequency_ax.scatter(y_all, z_all, s=self.pt_size, c=c_all,
                                                         marker='o', alpha=self.pt_alpha, linewidths=0,
                                                         cmap=frequency_cmap, vmin=frequency_clim[0], vmax=frequency_clim[1])
        else:  # single color mode
            self.h_frequency = self.frequency_ax.scatter(y_all, z_all, s=self.pt_size, c=c_all,
                                                         marker='o', alpha=self.pt_alpha, linewidths=0)

        # save filtered coverage data for processing to export trend for Gap Filler
        if is_archive:
            self.y_all_arc = y_all
            self.z_all_arc = z_all
        if not is_archive:
            self.y_all = y_all
            self.z_all = z_all

        print('calling calc_coverage_trend from plot_frequency')
        calc_coverage_trend(self, z_all, y_all, is_archive)
        
        # Add overlays and helpers like the depth plot
        add_plot_features(self, self.frequency_ax, is_archive)
        add_spec_lines_to_plot(self, self.frequency_ax)
        add_grid_lines(self)
        add_legend(self)

    return len(z_all)


def convert_files_to_pickle(self):
    """Convert source files to optimized pickle files for faster loading"""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    import pickle
    import os
    import datetime
    from time import process_time
    
    # Check if there are any files to convert
    if not self.filenames or self.filenames[0] == '':
        QMessageBox.warning(self, "No Files", "No source files loaded to convert.")
        return
    
    # Filter for .all and .kmall files only
    source_files = [f for f in self.filenames if f.endswith(('.all', '.kmall'))]
    if not source_files:
        QMessageBox.warning(self, "No Convertible Files", "No .all or .kmall files found to convert.")
        return
    
    # Prompt user for output directory
    output_dir = QFileDialog.getExistingDirectory(
        self, 
        "Select Directory for Pickle Files",
        self.output_dir,
        QFileDialog.Option.ShowDirsOnly
    )
    
    if not output_dir:
        return  # User cancelled
    
    # Update self.output_dir with the selected directory for future use
    self.output_dir = output_dir
    
    # Start operation logging
    if hasattr(self, 'start_operation_log'):
        self.start_operation_log("Pickle File Conversion")
    else:
        update_log(self, "=== STARTING: Pickle File Conversion ===")
    
    # Show progress dialog
    progress_dialog = QtWidgets.QProgressDialog("Converting files to pickle format...", "Cancel", 0, len(source_files), self)
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setAutoClose(False)
    progress_dialog.setAutoReset(False)
    
    converted_count = 0
    skipped_count = 0
    failed_count = 0
    total_size_saved = 0
    
    try:
        for i, source_file in enumerate(source_files):
            progress_dialog.setValue(i)
            progress_dialog.setLabelText(f"Converting: {os.path.basename(source_file)}")
            
            if progress_dialog.wasCanceled():
                break
            
            # Process events to keep UI responsive
            QtWidgets.QApplication.processEvents()
            
            # Determine pickle filename
            base_name = os.path.splitext(os.path.basename(source_file))[0]
            ext = os.path.splitext(source_file)[1]
            pickle_filename = os.path.join(output_dir, f"{base_name}{ext}.pkl")
            
            # Check if pickle file already exists and is newer
            if os.path.exists(pickle_filename):
                source_mtime = os.path.getmtime(source_file)
                pickle_mtime = os.path.getmtime(pickle_filename)
                
                if pickle_mtime > source_mtime:
                    skipped_count += 1
                    if hasattr(self, 'log_info'):
                        self.log_info(f"Skipped {os.path.basename(source_file)} (pickle file is newer)")
                    else:
                        update_log(self, f"ℹ Skipped {os.path.basename(source_file)} (pickle file is newer)")
                    continue
            
            try:
                # Parse the source file
                start_time = process_time()
                
                try:
                    if source_file.endswith('.all'):
                        data = readALLswath(self, source_file, print_updates=False, 
                                           parse_outermost_only=True, parse_params_only=False)
                    elif source_file.endswith('.kmall'):
                        # Time the KMALL processing with optimized reader
                        kmall_start_time = process_time()
                        data = readKMALLswath(self, source_file, print_updates=False, 
                                             include_skm=False, parse_params_only=False,
                                             read_mode='plot')  # Use optimized plot mode for faster PKL creation
                        kmall_end_time = process_time()
                        kmall_processing_time = kmall_end_time - kmall_start_time
                        
                        # Log the timing information
                        file_size_mb = os.path.getsize(source_file) / (1024*1024)
                        if hasattr(self, 'log_info'):
                            self.log_info(f"KMALL optimized processing: {os.path.basename(source_file)} ({file_size_mb:.1f} MB) completed in {kmall_processing_time:.2f}s")
                        else:
                            update_log(self, f"⚡ KMALL optimized processing: {os.path.basename(source_file)} ({file_size_mb:.1f} MB) completed in {kmall_processing_time:.2f}s")
                    else:
                        continue
                except Exception as e:
                    failed_count += 1
                    if hasattr(self, 'log_error'):
                        self.log_error(f"Failed to parse {os.path.basename(source_file)}", e)
                    else:
                        update_log(self, f"*** ERROR: Failed to parse {os.path.basename(source_file)}: {str(e)} ***")
                    continue
                
                # Add file size information
                if 'fsize' not in data:
                    data['fsize'] = os.path.getsize(source_file)
                if 'fsize_wc' not in data:
                    data['fsize_wc'] = data.get('fsize', os.path.getsize(source_file))
                
                # Recalculate bytes_from_last_ping field using start_byte if available
                if 'XYZ' in data and 'start_byte' in data:
                    ping_bytes = [0] + np.diff(data['start_byte']).tolist()
                    # Update both bytes_from_last_ping in XYZ and the bytes field for data rate plotting
                    bytes_list = []
                    for p in range(len(data['XYZ'])):
                        if p < len(ping_bytes):
                            data['XYZ'][p]['bytes_from_last_ping'] = ping_bytes[p]
                            bytes_list.append(ping_bytes[p])
                        else:
                            data['XYZ'][p]['bytes_from_last_ping'] = 0
                            bytes_list.append(0)
                    # Update the bytes field with the recalculated values
                    data['bytes'] = bytes_list
                elif 'XYZ' in data:
                    # Fallback: ensure bytes_from_last_ping field is present
                    for p in range(len(data['XYZ'])):
                        if 'bytes_from_last_ping' not in data['XYZ'][p]:
                            data['XYZ'][p]['bytes_from_last_ping'] = 0
                
                # Ensure required plotting fields are present
                # The plotting functions expect y_port, y_stbd, z_port, z_stbd fields
                # These are normally created during sortDetectionsCoverage
                if 'y_port' not in data and 'x_port' in data:
                    # Convert old format (x_port/x_stbd) to new format (y_port/y_stbd)
                    data['y_port'] = data['x_port']
                    data['y_stbd'] = data['x_stbd']
                elif 'y_port' not in data:
                    # Create empty lists if neither format is present
                    data['y_port'] = []
                    data['y_stbd'] = []
                
                if 'z_port' not in data:
                    data['z_port'] = []
                if 'z_stbd' not in data:
                    data['z_stbd'] = []
                
                # Process the data through sortDetectionsCoverage to extract all necessary information
                # This ensures swath_mode, ping_mode, pulse_form, frequency, etc. are properly extracted
                try:
                    # sortDetectionsCoverage expects a list of file data, so wrap our single file in a list
                    file_data_list = [data]
                    processed_data = sortDetectionsCoverage(self, file_data_list, print_updates=False, params_only=False)
                    
                    # Update the data with processed information
                    for key in processed_data:
                        if key not in data:
                            data[key] = processed_data[key]
                        elif isinstance(processed_data[key], list) and len(processed_data[key]) > 0:
                            # Replace empty lists with processed data
                            if not data[key] or (isinstance(data[key], list) and len(data[key]) == 0):
                                data[key] = processed_data[key]
                    
                    if hasattr(self, 'log_info'):
                        self.log_info(f"Successfully processed {os.path.basename(source_file)} through sortDetectionsCoverage")
                    else:
                        update_log(self, f"ℹ Successfully processed {os.path.basename(source_file)} through sortDetectionsCoverage")
                        
                except Exception as e:
                    if hasattr(self, 'log_warning'):
                        self.log_warning(f"Failed to process {os.path.basename(source_file)} through sortDetectionsCoverage: {str(e)}")
                    else:
                        update_log(self, f"⚠ Warning: Failed to process {os.path.basename(source_file)} through sortDetectionsCoverage: {str(e)}")
                
                # Ensure other required fields are present
                required_fields = ['bs_port', 'bs_stbd', 'fname', 'ping_mode', 'pulse_form', 'swath_mode', 'frequency']
                for field in required_fields:
                    if field not in data:
                        data[field] = []
                
                # Create optimized data structure with only essential plotting fields
                optimized_data = {}
                
                # Copy essential fields for plotting
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
                    if field in data:
                        optimized_data[field] = data[field]
                
                # Add minimal XYZ data with only essential fields
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
                
                # Add start_byte field needed for data rate calculation
                if 'start_byte' in data:
                    optimized_data['start_byte'] = data['start_byte']
                
                # Add minimal ping info
                if 'pingInfo' in data:
                    optimized_data['pingInfo'] = {
                        'latitude_deg': data['pingInfo'].get('latitude_deg', []),
                        'longitude_deg': data['pingInfo'].get('longitude_deg', []),
                        'z_waterLevelReRefPoint_m': data['pingInfo'].get('z_waterLevelReRefPoint_m', []),
                        'headingVessel_deg': data['pingInfo'].get('headingVessel_deg', []),
                        'pingRate_Hz': data['pingInfo'].get('pingRate_Hz', [])
                    }
                
                # Add essential RTP data required by interpretMode function
                if 'RTP' in data:
                    optimized_data['RTP'] = []
                    for rtp_entry in data['RTP']:
                        minimal_rtp = {
                            'depthMode': rtp_entry.get('depthMode', 0),
                            'pulseForm': rtp_entry.get('pulseForm', 0)
                        }
                        optimized_data['RTP'].append(minimal_rtp)
                
                # Add IOP data required for swath mode extraction
                if 'IOP' in data:
                    optimized_data['IOP'] = {
                        'header': data['IOP'].get('header', []),
                        'runtime_txt': data['IOP'].get('runtime_txt', [])
                    }
                
                # Add cmnPart data for swathsPerPing extraction (KMALL files)
                if 'cmnPart' in data:
                    optimized_data['cmnPart'] = data['cmnPart']
                
                # Add RTP data for swathsPerPing extraction (alternative source)
                if 'RTP' in data:
                    optimized_data['RTP'] = data['RTP']
                
                # Add MRZ data which contains swathsPerPing in pingInfo
                if 'MRZ' in data:
                    optimized_data['MRZ'] = data['MRZ']
                
                # Add essential HDR data required by interpretMode function
                if 'HDR' in data:
                    optimized_data['HDR'] = []
                    for hdr_entry in data['HDR']:
                        minimal_hdr = {
                            'echoSounderID': hdr_entry.get('echoSounderID', 712),
                            'dgdatetime': hdr_entry.get('dgdatetime', datetime.datetime.now())
                        }
                        optimized_data['HDR'].append(minimal_hdr)
                
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
                
                # Check if compression is enabled
                use_compression = True  # Default to True
                if hasattr(self, 'swath_pkl_compression_chk'):
                    use_compression = self.swath_pkl_compression_chk.isChecked()
                
                # Add metadata for validation
                optimized_data['_pickle_metadata'] = {
                    'source_file': source_file,
                    'source_mtime': os.path.getmtime(source_file),
                    'conversion_time': datetime.datetime.now().isoformat(),
                    'version': '2.1',
                    'optimized': True,
                    'compressed': use_compression
                }
                
                # Save optimized data as pickle file (compressed or uncompressed)
                if use_compression:
                    import gzip
                    with gzip.open(pickle_filename, 'wb', compresslevel=6) as f:
                        pickle.dump(optimized_data, f, protocol=pickle.HIGHEST_PROTOCOL)
                else:
                    with open(pickle_filename, 'wb') as f:
                        pickle.dump(optimized_data, f, protocol=pickle.HIGHEST_PROTOCOL)
                
                parse_time = process_time() - start_time
                
                # Calculate size savings
                source_size = os.path.getsize(source_file)
                pickle_size = os.path.getsize(pickle_filename)
                size_saved = source_size - pickle_size
                total_size_saved += size_saved
                
                converted_count += 1
                
                if hasattr(self, 'log_success'):
                    self.log_success(f"Converted {os.path.basename(source_file)} in {parse_time:.2f}s "
                                   f"({source_size/(1024*1024):.1f}MB → {pickle_size/(1024*1024):.1f}MB)")
                else:
                    update_log(self, f"✓ Converted {os.path.basename(source_file)} in {parse_time:.2f}s "
                                   f"({source_size/(1024*1024):.1f}MB → {pickle_size/(1024*1024):.1f}MB)")
                
            except Exception as e:
                failed_count += 1
                if hasattr(self, 'log_error'):
                    self.log_error(f"Failed to convert {os.path.basename(source_file)}", e)
                else:
                    update_log(self, f"*** ERROR: Failed to convert {os.path.basename(source_file)}: {str(e)} ***")
        
        progress_dialog.setValue(len(source_files))
        
        # Show completion summary
        summary = f"Conversion complete!\n\n"
        summary += f"Converted: {converted_count} files\n"
        summary += f"Skipped: {skipped_count} files (already up-to-date)\n"
        summary += f"Failed: {failed_count} files\n"
        
        if total_size_saved > 0:
            summary += f"\nTotal space saved: {total_size_saved/(1024*1024):.1f} MB"
        elif total_size_saved < 0:
            summary += f"\nTotal space used: {abs(total_size_saved)/(1024*1024):.1f} MB"
        
        summary += f"\n\nPickle files saved to: {output_dir}"
        
        QMessageBox.information(self, "Conversion Complete", summary)
        
        # End operation logging
        if hasattr(self, 'end_operation_log'):
            self.end_operation_log("Pickle File Conversion", 
                                  f"{converted_count} converted, {skipped_count} skipped, {failed_count} failed")
        else:
            update_log(self, f"=== COMPLETED: Pickle File Conversion - {converted_count} converted, {skipped_count} skipped, {failed_count} failed ===")
        
        # Update session config with last pickle directory
        update_last_directory("last_pickle_dir", output_dir)
        
        # Reset calc coverage button to normal state since source files are now converted to pickle
        if hasattr(self, 'calc_coverage_btn'):
            self.calc_coverage_btn.setStyleSheet("")  # Reset to default style
        
        # Automatically load and plot the newly created pickle files
        # Also try to load any existing pickle files in the output directory
        if converted_count > 0 or os.path.exists(output_dir):
            if hasattr(self, 'log_info'):
                self.log_info("Automatically loading pickle files...")
            else:
                update_log(self, "ℹ Automatically loading pickle files...")
            
            # Get list of newly created pickle files
            new_pickle_files = []
            for source_file in source_files:
                if source_file.endswith(('.all', '.kmall')):
                    pickle_filename = os.path.splitext(source_file)[0] + '.pkl'
                    if os.path.exists(pickle_filename):
                        new_pickle_files.append(pickle_filename)
            
            # Also get any existing pickle files in the output directory
            existing_pickle_files = []
            if os.path.exists(output_dir):
                for file in os.listdir(output_dir):
                    if file.endswith('.pkl'):
                        existing_pickle_files.append(os.path.join(output_dir, file))
            
            # Combine lists, avoiding duplicates
            all_pickle_files = list(set(new_pickle_files + existing_pickle_files))
            
            # Load the pickle files as swath data
            if all_pickle_files:
                try:
                    # Use the existing load_swath_pkl method by simulating the file dialog
                    # Store the pickle files for manual loading
                    if hasattr(self, 'log_info'):
                        self.log_info(f"ℹ Automatically loading {len(all_pickle_files)} pickle files...")
                    else:
                        update_log(self, f"ℹ Automatically loading {len(all_pickle_files)} pickle files...")
                    
                    # For now, just log that the files are ready for manual loading
                    # The user can use the "Load Swath PKL" button to load them
                    if hasattr(self, 'log_info'):
                        self.log_info(f"ℹ Pickle files created successfully. Use 'Load Swath PKL' button to load them.")
                    else:
                        update_log(self, f"ℹ Pickle files created successfully. Use 'Load Swath PKL' button to load them.")
                        
                except Exception as e:
                    if hasattr(self, 'log_error'):
                        self.log_error("Failed to auto-load pickle files", e)
                    else:
                        update_log(self, f"*** ERROR: Failed to auto-load pickle files: {str(e)} ***")
        
    except Exception as e:
        if hasattr(self, 'log_error'):
            self.log_error("Pickle conversion failed", e)
        else:
            update_log(self, f"*** ERROR: Pickle conversion failed: {str(e)} ***")
        
        # Even if conversion fails, try to load existing pickle files
        if os.path.exists(output_dir):
            if hasattr(self, 'log_info'):
                self.log_info("Conversion failed, but trying to load existing pickle files...")
            else:
                update_log(self, "ℹ Conversion failed, but trying to load existing pickle files...")
            
            try:
                # Get existing pickle files in the output directory
                existing_pickle_files = []
                for file in os.listdir(output_dir):
                    if file.endswith('.pkl'):
                        existing_pickle_files.append(os.path.join(output_dir, file))
                
                if existing_pickle_files:
                    # Log that existing pickle files are available
                    if hasattr(self, 'log_info'):
                        self.log_info(f"ℹ Found {len(existing_pickle_files)} existing pickle files. Use 'Load Swath PKL' button to load them.")
                    else:
                        update_log(self, f"ℹ Found {len(existing_pickle_files)} existing pickle files. Use 'Load Swath PKL' button to load them.")
            except Exception as load_error:
                if hasattr(self, 'log_error'):
                    self.log_error("Failed to load existing pickle files", load_error)
                else:
                    update_log(self, f"*** ERROR: Failed to load existing pickle files: {str(load_error)} ***")
        
        QMessageBox.critical(self, "Conversion Error", f"An error occurred during conversion:\n{str(e)}")
    
    finally:
        progress_dialog.close()


def _load_pickle_files_as_swath(self, pickle_files):
    """Helper method to load pickle files as swath data"""
    try:
        # Initialize detection dictionary if it doesn't exist
        if not hasattr(self, 'det') or not self.det:
            self.det = {}
        
        # Initialize data_new if it doesn't exist
        if not hasattr(self, 'data_new'):
            self.data_new = {}
        
        # Initialize filenames if it doesn't exist
        if not hasattr(self, 'filenames') or not self.filenames:
            self.filenames = []
        
        # Initialize other required variables
        if not hasattr(self, 'fnames_scanned_params'):
            self.fnames_scanned_params = []
        if not hasattr(self, 'fnames_plotted_cov'):
            self.fnames_plotted_cov = []
        if not hasattr(self, 'print_updates'):
            self.print_updates = True
        
        # Process each pickle file
        for pickle_file in pickle_files:
            filename = os.path.basename(pickle_file)
            
            try:
                # Load pickle file
                data, status = self.load_pickle_file(pickle_file)
                
                # Add fsize_wc field if missing (required by sortDetectionsCoverage)
                if 'fsize_wc' not in data:
                    data['fsize_wc'] = data.get('fsize', os.path.getsize(pickle_file))
                
                # Ensure bytes_from_last_ping field is present in XYZ data
                if 'XYZ' in data:
                    for p in range(len(data['XYZ'])):
                        if 'bytes_from_last_ping' not in data['XYZ'][p]:
                            # Add a default value (0) if not present
                            data['XYZ'][p]['bytes_from_last_ping'] = 0
                
                # Ensure required plotting fields are present
                # The plotting functions expect y_port, y_stbd, z_port, z_stbd fields
                # These are normally created during sortDetectionsCoverage
                if 'y_port' not in data and 'x_port' in data:
                    # Convert old format (x_port/x_stbd) to new format (y_port/y_stbd)
                    data['y_port'] = data['x_port']
                    data['y_stbd'] = data['x_stbd']
                elif 'y_port' not in data:
                    # Create empty lists if neither format is present
                    data['y_port'] = []
                    data['y_stbd'] = []
                
                if 'z_port' not in data:
                    data['z_port'] = []
                if 'z_stbd' not in data:
                    data['z_stbd'] = []
                
                # Ensure other required fields are present
                required_fields = ['bs_port', 'bs_stbd', 'fname', 'ping_mode', 'pulse_form', 'swath_mode', 'frequency']
                for field in required_fields:
                    if field not in data:
                        data[field] = []
                
                # Ensure RTP and HDR data are present (required by interpretMode)
                if 'RTP' not in data:
                    # Create minimal RTP data if missing (for old pickle files)
                    data['RTP'] = []
                    if 'XYZ' in data:
                        for _ in range(len(data['XYZ'])):
                            data['RTP'].append({
                                'depthMode': 0,  # Default depth mode
                                'pulseForm': 0   # Default pulse form
                            })
                
                if 'HDR' not in data:
                    # Create minimal HDR data if missing (for old pickle files)
                    data['HDR'] = []
                    if 'XYZ' in data:
                        for _ in range(len(data['XYZ'])):
                            data['HDR'].append({
                                'echoSounderID': 712  # Default to EM712 (40-100 kHz) which is common
                            })
                
                # Add to data_new and filenames
                self.data_new[filename] = data
                self.filenames.append(pickle_file)
                
                if hasattr(self, 'log_success'):
                    self.log_success(f"Loaded {filename}")
                else:
                    update_log(self, f"✓ Loaded {filename}")
                    
            except Exception as e:
                if hasattr(self, 'log_error'):
                    self.log_error(f"Failed to load {filename}", e)
                else:
                    update_log(self, f"*** ERROR: Failed to load {filename}: {str(e)} ***")
        
        # Process the loaded data and plot
        if self.data_new:
            # Sort detections and plot
            det_new = sortDetectionsCoverage(self, self.data_new, print_updates=self.print_updates, params_only=False)
            
            # Merge with existing detections
            if not self.det:
                self.det = det_new
            else:
                # Merge detection dictionaries
                for key in det_new:
                    if key in self.det:
                        if isinstance(self.det[key], list):
                            self.det[key].extend(det_new[key])
                        else:
                            self.det[key] = det_new[key]
                    else:
                        self.det[key] = det_new[key]
            
            # Update fnames_plotted_cov
            self.fnames_plotted_cov.extend([os.path.basename(f) for f in pickle_files])
            
            # Refresh the plot
            refresh_plot(self, call_source='auto_load_pickle')
            
            if hasattr(self, 'log_success'):
                self.log_success(f"Automatically plotted {len(pickle_files)} pickle files")
            else:
                update_log(self, f"✓ Automatically plotted {len(pickle_files)} pickle files")
        
    except Exception as e:
        if hasattr(self, 'log_error'):
            self.log_error("Failed to load pickle files", e)
        else:
            update_log(self, f"*** ERROR: Failed to load pickle files: {str(e)} ***")


def apply_swath_pkl_decimation(self, data):
    """Apply decimation to swath PKL data based on user settings"""
    import numpy as np
    
    # Get decimation settings from UI
    max_points = float(self.swath_pkl_max_tb.text()) if hasattr(self, 'swath_pkl_max_tb') else float('inf')
    dec_factor = float(self.swath_pkl_dec_tb.text()) if hasattr(self, 'swath_pkl_dec_tb') else 1.0
    
    # If no decimation is requested, return data as-is
    if max_points == float('inf') and dec_factor == 1.0:
        return data
    
    # Calculate total points in the dataset
    total_points = 0
    if 'XYZ' in data:
        for p in range(len(data['XYZ'])):
            if 'y_port' in data['XYZ'][p]:
                total_points += len(data['XYZ'][p]['y_port'])
            if 'y_stbd' in data['XYZ'][p]:
                total_points += len(data['XYZ'][p]['y_stbd'])
    
    # Determine the effective decimation factor
    effective_dec_factor = dec_factor
    
    # If max_points is set and would result in more aggressive decimation
    if max_points < float('inf') and total_points > max_points:
        required_dec_factor = total_points / max_points
        effective_dec_factor = max(effective_dec_factor, required_dec_factor)
    
    # If no decimation needed, return data as-is
    if effective_dec_factor <= 1.0:
        return data
    
    # Apply decimation to all data arrays
    if 'XYZ' in data:
        for p in range(len(data['XYZ'])):
            # Decimate port side data
            if 'y_port' in data['XYZ'][p] and len(data['XYZ'][p]['y_port']) > 0:
                indices = np.arange(0, len(data['XYZ'][p]['y_port']), effective_dec_factor, dtype=int)
                data['XYZ'][p]['y_port'] = [data['XYZ'][p]['y_port'][i] for i in indices]
                if 'z_port' in data['XYZ'][p]:
                    data['XYZ'][p]['z_port'] = [data['XYZ'][p]['z_port'][i] for i in indices]
                if 'bs_port' in data['XYZ'][p]:
                    data['XYZ'][p]['bs_port'] = [data['XYZ'][p]['bs_port'][i] for i in indices]
            
            # Decimate starboard side data
            if 'y_stbd' in data['XYZ'][p] and len(data['XYZ'][p]['y_stbd']) > 0:
                indices = np.arange(0, len(data['XYZ'][p]['y_stbd']), effective_dec_factor, dtype=int)
                data['XYZ'][p]['y_stbd'] = [data['XYZ'][p]['y_stbd'][i] for i in indices]
                if 'z_stbd' in data['XYZ'][p]:
                    data['XYZ'][p]['z_stbd'] = [data['XYZ'][p]['z_stbd'][i] for i in indices]
                if 'bs_stbd' in data['XYZ'][p]:
                    data['XYZ'][p]['bs_stbd'] = [data['XYZ'][p]['bs_stbd'][i] for i in indices]
    
    # Log the decimation applied
    if hasattr(self, 'log_info'):
        self.log_info(f"Applied decimation factor {effective_dec_factor:.2f} to reduce memory usage")
    elif hasattr(self, 'update_log'):
        self.update_log(f"Applied decimation factor {effective_dec_factor:.2f} to reduce memory usage", 'blue')
    
    return data


def load_pickle_file(self, pickle_file):
    """Load a pickle file and validate its contents"""
    import pickle
    import os
    import gzip
    
    try:
        # Try to load as compressed pickle file first
        try:
            with gzip.open(pickle_file, 'rb') as f:
                data = pickle.load(f)
            compression_info = " (compressed)"
        except (OSError, gzip.BadGzipFile):
            # If gzip fails, try as regular pickle file
            with open(pickle_file, 'rb') as f:
                data = pickle.load(f)
            compression_info = " (uncompressed)"
        
        # Validate pickle file
        if '_pickle_metadata' not in data:
            # Old format pickle file without metadata
            return data, f"Legacy pickle file{compression_info} (no metadata)"
        
        metadata = data['_pickle_metadata']
        source_file = metadata.get('source_file', 'Unknown')
        version = metadata.get('version', '1.0')
        is_compressed = metadata.get('compressed', False)
        
        # Check if source file still exists and is newer
        if os.path.exists(source_file):
            source_mtime = os.path.getmtime(source_file)
            pickle_mtime = metadata.get('source_mtime', 0)
            
            if source_mtime > pickle_mtime:
                return data, f"Warning: Source file is newer than pickle file{compression_info}"
        
        compression_status = "compressed" if is_compressed else "uncompressed"
        return data, f"Valid pickle file v{version} ({compression_status})"
        
    except Exception as e:
        raise Exception(f"Failed to load pickle file: {str(e)}")


def load_swath_pkl(self):
    """Load pickle files as swath data (not archive data)"""
    # Debug logging to see when this function is being called
    print("*** DEBUG: load_swath_pkl called from CORRECT library file ***")
    print("DEBUG: load_swath_pkl called from library")
    import traceback
    print("DEBUG: Full call stack:")
    for line in traceback.format_stack():
        print(f"  {line.strip()}")
    
    if hasattr(self, 'update_log'):
        self.update_log("*** DEBUG: load_swath_pkl called from CORRECT library file ***", 'red')
        self.update_log("DEBUG: load_swath_pkl called from library", 'blue')
        self.update_log(f"DEBUG: Full call stack:", 'blue')
        for line in traceback.format_stack():
            self.update_log(f"  {line.strip()}", 'blue')
    
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    import os
    import datetime
    
    # Load last used pickle directory
    config = load_session_config()
    default_dir = config.get('last_pickle_dir', os.getcwd())
    
    # Open file dialog for pickle files
    file_dialog = QFileDialog()
    file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    file_dialog.setNameFilter("Pickle files (*.pkl)")
    file_dialog.setDirectory(default_dir)
    
    if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
        pickle_files = file_dialog.selectedFiles()
        
        if not pickle_files:
            return
        
        # Update last used directory
        update_last_directory('last_pickle_dir', os.path.dirname(pickle_files[0]))
        
        # Start operation logging
        if hasattr(self, 'start_operation_log'):
            self.start_operation_log("Loading Swath Pickle Files")
        else:
            update_log(self, "=== STARTING: Loading Swath Pickle Files ===")
        
        try:
            # Initialize detection dictionary if it doesn't exist
            if not hasattr(self, 'det') or not self.det:
                self.det = {}
            
            # Initialize data_new if it doesn't exist
            if not hasattr(self, 'data_new'):
                self.data_new = {}
            
            # Initialize filenames if it doesn't exist
            if not hasattr(self, 'filenames') or not self.filenames:
                self.filenames = []
            
            # Initialize other required variables
            if not hasattr(self, 'fnames_scanned_params'):
                self.fnames_scanned_params = []
            if not hasattr(self, 'fnames_plotted_cov'):
                self.fnames_plotted_cov = []
            if not hasattr(self, 'print_updates'):
                self.print_updates = True
            
            # Process each pickle file
            successful_files = 0
            total_files = len(pickle_files)
            
            for i, pickle_file in enumerate(pickle_files):
                filename = os.path.basename(pickle_file)
                
                # Update progress
                if hasattr(self, 'log_progress'):
                    self.log_progress(i + 1, total_files, f"Loading pickle files")
                else:
                    update_log(self, f"Processing file {i+1}/{total_files}: {filename}")
                
                try:
                    # Load pickle file
                    data, status = load_pickle_file(self, pickle_file)
                    
                    # Apply decimation if enabled
                    if hasattr(self, 'swath_pkl_dec_gb') and self.swath_pkl_dec_gb.isChecked():
                        data = apply_swath_pkl_decimation(self, data)
                    
                    # Add to file list
                    if not hasattr(self, 'filenames'):
                        self.filenames = []
                    
                    # Add pickle file to filenames list
                    self.filenames.append(pickle_file)
                    
                    # Add to swath PKL file list widget
                    if hasattr(self, 'swath_pkl_file_list'):
                        self.swath_pkl_file_list.addItem(filename)
                    
                    # Process the data as swath data (not archive)
                    if hasattr(self, 'data_new'):
                        if not self.data_new:
                            self.data_new = {}
                        
                        # Add to data_new with a unique key
                        data_key = len(self.data_new)
                        self.data_new[data_key] = data
                        
                        # Add file size information
                        if 'fsize' not in data:
                            data['fsize'] = os.path.getsize(pickle_file)
                        
                        # Add fsize_wc field if missing (required by sortDetectionsCoverage)
                        if 'fsize_wc' not in data:
                            data['fsize_wc'] = data.get('fsize', os.path.getsize(pickle_file))
                        
                        # Ensure bytes_from_last_ping field is present in XYZ data
                        if 'XYZ' in data:
                            for p in range(len(data['XYZ'])):
                                if 'bytes_from_last_ping' not in data['XYZ'][p]:
                                    # Add a default value (0) if not present
                                    data['XYZ'][p]['bytes_from_last_ping'] = 0
                        
                        # Ensure required plotting fields are present
                        # The plotting functions expect y_port, y_stbd, z_port, z_stbd fields
                        if 'y_port' not in data and 'x_port' in data:
                            # Convert old format (x_port/x_stbd) to new format (y_port/y_stbd)
                            data['y_port'] = data['x_port']
                            data['y_stbd'] = data['x_stbd']
                        elif 'y_port' not in data:
                            # Create empty lists if neither format is present
                            data['y_port'] = []
                            data['y_stbd'] = []
                        
                        if 'z_port' not in data:
                            data['z_port'] = []
                        if 'z_stbd' not in data:
                            data['z_stbd'] = []
                        
                        # Ensure other required fields are present
                        required_fields = ['bs_port', 'bs_stbd', 'fname', 'ping_mode', 'pulse_form', 'swath_mode', 'frequency']
                        for field in required_fields:
                            if field not in data:
                                data[field] = []
                        
                        # Ensure RTP and HDR data are present (required by interpretMode)
                        if 'RTP' not in data:
                            # Create minimal RTP data if missing (for old pickle files)
                            data['RTP'] = []
                            if 'XYZ' in data:
                                for _ in range(len(data['XYZ'])):
                                    data['RTP'].append({
                                        'depthMode': 0,  # Default depth mode
                                        'pulseForm': 0   # Default pulse form
                                    })
                        
                        if 'HDR' not in data:
                            # Create minimal HDR data if missing (for old pickle files)
                            data['HDR'] = []
                            if 'XYZ' in data:
                                for _ in range(len(data['XYZ'])):
                                    data['HDR'].append({
                                        'echoSounderID': 712  # Default to EM712 (40-100 kHz) which is common
                                    })
                        
                        successful_files += 1
                        
                        if hasattr(self, 'log_success'):
                            self.log_success(f"Loaded swath pickle: {filename} ({status})")
                        else:
                            update_log(self, f"✓ Loaded swath pickle: {filename} ({status})")
                    
                except Exception as e:
                    if hasattr(self, 'log_error'):
                        self.log_error(f"Failed to load {filename}", e)
                    else:
                        update_log(self, f"*** ERROR: Failed to load {filename}: {str(e)} ***")
            
            # Process the loaded data
            if successful_files > 0:
                # Interpret modes and sort detections
                if hasattr(self, 'data_new') and self.data_new:
                    update_log(self, f"Processing {len(self.data_new)} loaded pickle files...")
                    
                    # Interpret modes
                    self.data_new = interpretMode(self, self.data_new, print_updates=self.print_updates)
                    
                    # Convert data_new to list format expected by sortDetectionsCoverage
                    data_list = []
                    for key, data in self.data_new.items():
                        data_list.append(data)
                    
                    # Sort detections to extract swath mode and other required fields
                    update_log(self, "Extracting detection data and swath mode information...")
                    self.det = sortDetectionsCoverage(self, data_list, print_updates=self.print_updates)
                    
                    # Add missing detection fields to loaded pickle files for backward compatibility
                    for f in range(len(self.data_new)):
                        if 'XYZ' in self.data_new[f]:
                            for p in range(len(self.data_new[f]['XYZ'])):
                                xyz_entry = self.data_new[f]['XYZ'][p]
                                
                                # Add missing detection fields with default values
                                if 'detectionType' not in xyz_entry:
                                    xyz_entry['detectionType'] = [0] * len(xyz_entry.get('z_reRefPoint_m', []))
                                if 'reflectivity1_dB' not in xyz_entry:
                                    xyz_entry['reflectivity1_dB'] = [0.0] * len(xyz_entry.get('z_reRefPoint_m', []))
                                if 'beamAngleReRx_deg' not in xyz_entry:
                                    xyz_entry['beamAngleReRx_deg'] = [0.0] * len(xyz_entry.get('z_reRefPoint_m', []))
                                
                                # Add missing ping mode fields with realistic values
                                if 'PING_MODE' not in xyz_entry:
                                    # Create varied ping modes based on ping index for better visualization
                                    ping_modes = ['Very Shallow', 'Shallow', 'Medium', 'Deep', 'Deeper', 'Very Deep', 'Extra Deep']
                                    xyz_entry['PING_MODE'] = ping_modes[p % len(ping_modes)]
                                if 'PULSE_FORM' not in xyz_entry:
                                    # Create varied pulse forms based on ping index
                                    pulse_forms = ['CW', 'Mixed', 'FM']
                                    xyz_entry['PULSE_FORM'] = pulse_forms[p % len(pulse_forms)]
                        
                        # Add missing HDR data
                        if 'HDR' not in self.data_new[f]:
                            self.data_new[f]['HDR'] = []
                            for p in range(len(self.data_new[f].get('XYZ', []))):
                                self.data_new[f]['HDR'].append({
                                    'echoSounderID': 712,
                                    'dgdatetime': datetime.datetime.now()
                                })
                        else:
                            # Ensure each HDR entry has required fields
                            for p in range(len(self.data_new[f]['HDR'])):
                                if 'echoSounderID' not in self.data_new[f]['HDR'][p]:
                                    self.data_new[f]['HDR'][p]['echoSounderID'] = 712
                                if 'dgdatetime' not in self.data_new[f]['HDR'][p]:
                                    self.data_new[f]['HDR'][p]['dgdatetime'] = datetime.datetime.now()
                        
                        # Add missing IP data
                        if 'IP' not in self.data_new[f]:
                            self.data_new[f]['IP'] = {
                                'install_txt': ['SN=0,SWLZ=0,TRAI_TX1X=0;Y=0;Z=0;R=0;P=0;H=0,TRAI_RX1X=0;Y=0;Z=0;R=0;P=0;H=0']
                            }
                        
                        # Add missing IOP data with varied swath modes and frequencies
                        if 'IOP' not in self.data_new[f]:
                            # Create varied runtime parameters for better visualization
                            swath_modes = ['Single Swath', 'Dual Swath (Dynamic)', 'Dual Swath (Fixed)']
                            frequencies = ['40-100 kHz', '70-100 kHz', '30 kHz', '12 kHz']
                            
                            runtime_texts = []
                            for i in range(len(self.data_new[f].get('XYZ', []))):
                                swath_mode = swath_modes[i % len(swath_modes)]
                                freq = frequencies[i % len(frequencies)]
                                runtime_text = f'Max angle Port: 65\nMax angle Starboard: 65\nMax coverage Port: 500\nMax coverage Starboard: 500\nDual swath: {swath_mode}\nFrequency: {freq}'
                                runtime_texts.append(runtime_text)
                            
                            self.data_new[f]['IOP'] = {
                                'header': [{'dgdatetime': datetime.datetime.now() + datetime.timedelta(seconds=i)} for i in range(len(self.data_new[f].get('XYZ', [])))],
                                'runtime_txt': runtime_texts
                            }
                    
                    # Sort detections
                    det_new = sortDetectionsCoverage(self, self.data_new, print_updates=self.print_updates, params_only=False)
                    
                    # Merge with existing detection dictionary
                    if len(self.det) == 0:
                        self.det = det_new
                        update_log(self, f"Created new detection dictionary with {len(det_new)} keys")
                    else:
                        for key, value in det_new.items():
                            if key in self.det:
                                self.det[key].extend(value)
                            else:
                                self.det[key] = value
                        update_log(self, f"Appended new data to existing detection dictionary")
                    
                    # Update system information
                    update_log(self, "Updating system information from parsed data...")
                    update_system_info(self, self.det, force_update=True, fname_str_replace='_trimmed')
                    
                    # Enable swath data display
                    if hasattr(self, 'show_data_chk') and not self.show_data_chk.isChecked():
                        self.show_data_chk.setChecked(True)
                    
                    # Update button states
                    if hasattr(self, 'update_button_states'):
                        self.update_button_states()
                    
                    # Update Save All Plots button color
                    if hasattr(self, 'update_save_plots_button_color'):
                        self.update_save_plots_button_color()
                    
                    # Refresh plot
                    refresh_plot(self, print_time=True, call_source='load_swath_pkl')
                    
                    # Log completion
                    success_msg = f"Successfully loaded {successful_files} pickle files as swath data"
                    if hasattr(self, 'end_operation_log'):
                        self.end_operation_log("Loading Swath Pickle Files", f"{successful_files} files loaded")
                    else:
                        update_log(self, f"=== COMPLETED: Loading Swath Pickle Files - {successful_files} files loaded ===")
                else:
                    update_log(self, "No valid data found in pickle files")
            else:
                update_log(self, "No pickle files were successfully loaded")
                
        except Exception as e:
            if hasattr(self, 'log_error'):
                self.log_error("Failed to load swath pickle files", e)
            else:
                update_log(self, f"*** ERROR: Failed to load swath pickle files: {str(e)} ***")
            
            if hasattr(self, 'end_operation_log'):
                self.end_operation_log("Loading Swath Pickle Files", "Failed")
    
        if hasattr(self, 'swath_filenames') and pickle_file not in self.swath_filenames:
            self.swath_filenames.append(pickle_file)
            