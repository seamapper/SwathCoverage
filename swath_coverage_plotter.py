# -*- coding: utf-8 -*-
"""
Created on Fri Feb 15 14:33:30 2019

@author: kjerram and pjohnson

Multibeam Echosounder Assessment Toolkit: Swath Coverage Plotter

This application provides a comprehensive GUI for analyzing and visualizing 
multibeam sonar data from Kongsberg systems (EM series). It supports:
- Loading and processing KMALL and ALL format files
- Converting data to compressed PKL format for faster loading
- Generating various plot types (depth, backscatter, ping mode, etc.)
- Coverage analysis and trend calculations
- Data archiving and export functionality
- Interactive plotting with hover information
- Configurable color schemes and plot parameters

Key Features:
- Real-time data visualization with matplotlib integration
- Session persistence for directory preferences
- Gzip compression for PKL files
- Multiple plot types and export options
- Interactive data exploration tools
"""

# Standard library imports
from PyQt6 import QtWidgets, QtGui
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtCore import Qt, QSize

import sys
import time
import datetime
import os
import traceback

# Third-party imports for plotting and GUI
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from libs.gui_widgets import *
try:
    from .libs.swath_coverage_lib import *
except ImportError:
    from libs.swath_coverage_lib import *
import matplotlib.pyplot as plt


# Version tracking for the application
# __version__ = "0.2.4"  # added EM2042 support, using old version of kmall.py from Seabream
#__version__ = "999999"  # EM2042 example from Tony + transition to POLLACK / Python 3.10
# __version__ = "2025.02"  # New features, new swath PKL, GUI redesign
# __version__ = "2025.03"  # Fixed some issues with the swath coverage plotter
# __version__ = "2025.05"  # Fixed frequency plot export size and text field styling
# __version__ = "2025.06"  # Fixed issue with loading new PKL files, added loading directory
# __version__ = "2025.07"  # Improved swatch coverage curve specification plotting 
#__version__ = "2025.08"  # Enhanced theoretical performance plotting 
__version__ = "2025.09"  # GUI improvements, Fixed Plots Scaling

class MainWindow(QtWidgets.QMainWindow):
    """
    Main application window for the Swath Coverage Plotter.
    
    This class handles the complete GUI interface including:
    - File loading and management
    - Data visualization and plotting
    - User interaction and event handling
    - Session configuration and persistence
    - Export and archiving functionality
    
    Attributes:
        media_path (str): Path to media resources (icons, etc.)
        start_time (float): Application start timestamp
        operation_start_time (float): Current operation start timestamp
        plot_save_dir (str): Directory for saving plot files
        archive_save_dir (str): Directory for saving archive files
        export_save_dir (str): Directory for exporting data
        param_save_dir (str): Directory for saving parameter logs
        det (dict): Detection data dictionary for new/current data
        det_archive (dict): Detection data dictionary for archive data
    """

    # Path to media resources (icons, etc.)
    media_path = os.path.join(os.path.dirname(__file__), "media")

    def __init__(self, parent=None):
        """
        Initialize the main application window.
        
        Sets up the GUI layout, initializes data structures,
        loads session configuration, and establishes event connections.
        """
        super(MainWindow, self).__init__()

        # Initialize logging and timing
        self.start_time = time.time()
        self.operation_start_time = None

        # Configure main window properties
        self.mainWidget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.mainWidget)
        self.setMinimumWidth(1600)
        self.setMinimumHeight(1100)
        self.setMaximumWidth(1600)
        self.setMaximumHeight(1100)
        self.setWindowTitle('Swath Coverage Plotter v.%s' % __version__ + ' - kjerram@ccom.unh.edu & pjohnson@ccom.unh.edu')
        self.setWindowIcon(QtGui.QIcon(os.path.join(self.media_path, "icon.png")))

        # Windows-specific taskbar icon configuration
        if os.name == 'nt':  # necessary to explicitly set taskbar icon
            import ctypes
            current_app_id = 'MAC.CoveragePlotter.' + __version__  # arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(current_app_id)

        # Initialize essential attributes that UI elements need
        self.sounding_fname_default = 'hover over sounding for filename'
        
        # Load last directories from configuration for different operations
        # This provides session persistence for user convenience
        try:
            from swath_coverage_lib import load_session_config
            config = load_session_config()
            self.plot_save_dir = config.get("last_plot_save_dir", os.getcwd())
            self.archive_save_dir = config.get("last_archive_save_dir", os.getcwd())
            self.export_save_dir = config.get("last_export_save_dir", os.getcwd())
            self.param_save_dir = config.get("last_param_save_dir", os.getcwd())
        except ImportError:
            # Fallback to current working directory if config loading fails
            self.plot_save_dir = os.getcwd()
            self.archive_save_dir = os.getcwd()
            self.export_save_dir = os.getcwd()
            self.param_save_dir = os.getcwd()
        
        # Initialize data model and reference lists
        self.model_list = ['EM 2040', 'EM 2042', 'EM 302', 'EM 304', 'EM 710', 'EM 712', 'EM 122', 'EM 124']
        self.depth_ref_list = ['Waterline', 'Origin', 'TX Array', 'Raw Data']
        self.top_data_list = []
        self.clim_list = ['All data', 'Filtered data', 'Fixed limits']
        self.clim_last_user = {'depth': [0, 1000], 'backscatter': [-50, -10]}
        
        # Initialize default parameters
        self.rtp_angle_buffer_default = 0
        self.n_points_max_default = 50000
        self.dec_fac_default = 1
        self.std_fig_width_inches = 12
        self.std_fig_height_inches = 12
        
        # Initialize data storage containers
        self.fnames_all = []  # Initialize for hover function
        self.fnames_sorted = []  # Initialize for hover function
        self.det = {}  # detection dict (new data)
        self.det_archive = {}  # detection dict (archive data)
        self.swath_filenames = []  # List of loaded swath PKL files (new data)
        
        # Store original file paths for path display toggle
        self.original_swath_pkl_paths = {}  # Store original paths for Swath PKL files
        
        # Initialize decimation cache for performance optimization
        self.decimation_cache = {}  # Cache for decimated data per file
        self.decimation_cache_valid = False  # Flag to track if cache is valid
        self.last_decimation_settings = {}  # Track last decimation settings
        self.last_filter_settings = {}  # Track last filter settings
        self.archive_filenames = []  # List of loaded archive PKL files
        
        # Initialize UI state tracking attributes
        self.ship_name_updated = False
        self.model_updated = False
        self.cruise_name_updated = False
        self.sn_updated = False
        self.ship_name = 'R/V Unsinkable II'
        self.cruise_name = ''
        self.filenames = ['']  # initial file list
        self.input_dir = ''  # initial input dir
        self.verbose_logging = False
        self.print_updates = True
        
        # Performance mode flag - when True, disables enhanced logging for better performance
        self.performance_mode = False
        
        # Pause plotting flag - when True, prevents automatic plot updates
        
        # Initialize data analysis containers
        self.spec = {}  # dict of theoretical coverage specs
        self.spec_colors = {}  # dict to store assigned colors for each spec curve
        self.spec_color_palette = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
        self.skm_time = {}
        self.sounding_fname = ''
        self.y_all = []
        self.trend_bin_centers = []
        self.trend_bin_means = []
        self.trend_bin_centers_arc = []
        self.trend_bin_means_arc = []
        self.c_all_data_rate = []
        self.c_all_data_rate_arc = []
        
        # Initialize plot limits and parameters
        self.x_max = 0.0
        self.z_max = 0.0
        self.subplot_adjust_top = 0.9
        self.title_str = ''
        self.ping_int_min = 0.25
        self.ping_int_max = 60
        
        # Initialize plotting parameters
        self.n_points_max = 50000  # Initialize for add_plot_features
        self.n_points_max_default = 50000
        self.dec_fac = 1
        self.rtp_angle_buffer = 0
        self.last_cmode = 'depth'
        
        # Initialize colorbar and legend objects
        self.cbar_ax1 = None
        self.cbar_ax2 = None
        self.cbar_ax3 = None
        self.cbar_ax4 = None
        self.legendbase = None
        self.cbar_font_size = 8
        self.cbar_title_font_size = 8
        self.cbar_loc = 1
        
        # Initialize color and plot settings
        self.clim = []
        self.clim_all_data = []
        self.cset = []
        self.n_wd_max = 8
        self.nominal_angle_line_interval = 15
        self.nominal_angle_line_max = 75
        self.swath_ax_margin = 1.1
        self.color = QtGui.QColor('lightGray')
        self.color_arc = QtGui.QColor('lightGray')
        
        # Initialize custom plot limits
        self.x_max_custom = 0.0
        self.z_max_custom = 0.0
        self.dr_max_custom = 1000
        self.pi_max_custom = 10
        self.dr_max = 1000
        self.pi_max = 10

        # Set up the three main layout sections
        self.set_left_layout()    # File controls and data management
        self.set_center_layout()  # Main plotting area
        self.set_right_layout()   # Plot controls and parameters
        self.set_main_layout()    # Combine all layouts
        
        # Initialize plotting axes and setup
        init_all_axes(self)
        setup(self)  # initialize remaining variables and plotter params after UI elements are created

        # Set up button controls for specific actions
        # File management buttons
        self.add_file_btn.clicked.connect(lambda: add_cov_files(self, 'Kongsberg (*.all *.kmall)'))
        self.get_indir_btn.clicked.connect(lambda: add_cov_files(self, ['.all', '.kmall'], input_dir='',
                                                                 include_subdir=self.include_subdir_chk.isChecked()))
        self.rmv_file_btn.clicked.connect(lambda: remove_cov_files(self))
        self.clr_file_btn.clicked.connect(lambda: remove_cov_files(self, clear_all=True))

        
        # Data management buttons
        self.archive_data_btn.clicked.connect(lambda: archive_data(self))
        self.load_archive_btn.clicked.connect(lambda: load_archive(self))
        self.remove_archive_btn.clicked.connect(self.remove_selected_archive_files)
        self.clear_archive_btn.clicked.connect(self.clear_all_archive_files)
        self.remove_swath_pkl_btn.clicked.connect(self.remove_selected_swath_pkl_files)
        self.clear_swath_pkl_btn.clicked.connect(self.clear_all_swath_pkl_files)
        self.load_swath_pkl_btn.clicked.connect(lambda: load_swath_pkl(self))
        self.get_pkl_dir_btn.clicked.connect(self.add_pkl_files_from_directory)
        self.convert_pickle_btn.clicked.connect(lambda: convert_files_to_pickle(self))
        
        # Analysis and plotting buttons
        self.load_spec_btn.clicked.connect(lambda: load_spec(self))
        self.remove_spec_btn.clicked.connect(self.remove_selected_spec_curves)
        self.calc_coverage_btn.clicked.connect(lambda: calc_coverage(self))
        self.save_all_plots_btn.clicked.connect(self.handle_save_all_plots)
        
        # Color and appearance buttons
        self.new_data_color_btn.clicked.connect(lambda: update_solid_color(self, 'color'))
        self.archive_data_color_btn.clicked.connect(lambda: update_solid_color(self, 'color_arc'))
        
        # Export and parameter buttons
        self.export_gf_btn.clicked.connect(lambda: export_gap_filler_trend(self))
        self.param_search_btn.clicked.connect(lambda: update_param_search(self))
        self.save_param_log_btn.clicked.connect(lambda: save_param_log(self))
        self.scan_params_btn.clicked.connect(lambda: calc_coverage(self, params_only=True))

        # Set up event actions that call refresh_plot
        gb_map = [self.custom_info_gb,
                  self.plot_lim_gb,
                  self.rtp_angle_gb,
                  self.rtp_cov_gb,
                  self.angle_gb,
                  self.depth_gb,
                  self.bs_gb,
                  self.angle_lines_gb,
                  self.n_wd_lines_gb,
                  self.pt_count_gb,
                  self.ping_int_gb,
                  self.swath_pkl_dec_gb]

        cbox_map = [self.model_cbox,
                    self.pt_size_cbox,
                    self.pt_alpha_cbox,
                    self.clim_cbox,
                    self.top_data_cbox,
                    self.ref_cbox]

        chk_map = [self.show_data_chk,
                   self.show_data_chk_arc,
                   self.grid_lines_toggle_chk,
                   self.colorbar_chk,
                   self.clim_filter_chk,
                   self.spec_chk,
                   self.show_ref_fil_chk,
                   self.show_spec_legend_chk,
                   self.show_hist_chk,
                   self.match_data_cmodes_chk,
                   self.show_model_chk,
                   self.show_ship_chk,
                   self.show_cruise_chk,
                   self.show_coverage_trend_chk]
        
        # add radio button connections for color mode changes
        radio_map = [self.new_data_color_by_type_radio,
                     self.new_data_single_color_radio,
                     self.archive_data_color_by_type_radio,
                     self.archive_data_single_color_radio]

        tb_map = [self.ship_tb,
                  self.cruise_tb,
                  self.max_x_tb, self.max_z_tb,
                  self.min_angle_tb, self.max_angle_tb,
                  self.min_depth_arc_tb, self.max_depth_arc_tb,
                  self.min_depth_tb, self.max_depth_tb,
                  self.min_bs_tb, self.max_bs_tb,
                  self.rtp_angle_buffer_tb,
                  self.rtp_cov_buffer_tb,
                  self.max_count_tb,
                  self.dec_fac_tb,
                  self.angle_lines_tb_max,
                  self.angle_lines_tb_int,
                  self.n_wd_lines_tb_max,
                  self.n_wd_lines_tb_int,
                  self.min_clim_tb,
                  self.max_clim_tb,
                  self.min_ping_int_tb,
                  self.max_ping_int_tb,
                  self.max_dr_tb,
                  self.max_pi_tb,
                  self.swath_pkl_max_tb,
                  self.swath_pkl_dec_tb]

        # if self.det or self.det_archive:  # execute only if data are loaded, not on startup
        for gb in gb_map:
            #groupboxes tend to not have objectnames, so use generic sender string
            gb.clicked.connect(lambda: self.update_filter_widget_styling())
            gb.clicked.connect(lambda: refresh_plot(self, sender='GROUPBOX_CHK'))

        for cbox in cbox_map:
            # lambda needs _ for cbox
            cbox.activated.connect(lambda _, sender=cbox.objectName(): refresh_plot(self, sender=sender))

        for chk in chk_map:
            # lambda needs _ for chk
            chk.stateChanged.connect(lambda _, sender=chk.objectName(): refresh_plot(self, sender=sender))
            
        for radio in radio_map:
            # lambda needs _ for radio
            radio.toggled.connect(lambda _, sender=radio.objectName(): refresh_plot(self, sender=sender))
            
        # Connect radio buttons to enable/disable color buttons
        self.new_data_single_color_radio.toggled.connect(self.update_new_data_color_button)
        self.archive_data_single_color_radio.toggled.connect(self.update_archive_data_color_button)
        
        

        for tb in tb_map:
            # lambda seems to not need _ for tb
            tb.returnPressed.connect(lambda sender=tb.objectName(): refresh_plot(self, sender=sender))

        # set up annotations on hovering
        self.swath_canvas.mpl_connect('motion_notify_event', self.hover)
        self.data_canvas.mpl_connect('motion_notify_event', self.hover_data)
        # self.swath_canvas.mpl_connect('motion_notify_event', self.hover)
        # plt.show()
        
        # Apply initial styling to filter widgets
        self.update_filter_widget_styling()

    def update_filter_widget_styling(self):
        """Update the styling of filter widgets based on their GroupBox state"""
        # Define the filter widgets and their corresponding GroupBoxes
        filter_widgets = [
            # Angle filter - always show as enabled
            ([self.min_angle_tb, self.max_angle_tb], self.angle_gb, True),
            # Depth filter - should always look enabled (like Limit plotted point count)
            ([self.min_depth_tb, self.max_depth_tb, self.min_depth_arc_tb, self.max_depth_arc_tb], self.depth_gb, True),
            # Backscatter filter - always show as enabled
            ([self.min_bs_tb, self.max_bs_tb], self.bs_gb, True),
            # Hide angles filter - always show as enabled
            ([self.rtp_angle_buffer_tb], self.rtp_angle_gb, True),
            # Hide coverage filter - always show as enabled
            ([self.rtp_cov_buffer_tb], self.rtp_cov_gb, True),
            # Angle lines filter - always show as enabled
            ([self.angle_lines_tb_max, self.angle_lines_tb_int], self.angle_lines_gb, True),
            # Water depth lines filter - always show as enabled
            ([self.n_wd_lines_tb_max, self.n_wd_lines_tb_int], self.n_wd_lines_gb, True),
        ]
        
        for filter_info in filter_widgets:
            if len(filter_info) == 3:
                # Special case for depth filter - always show as enabled
                widgets, groupbox, force_enabled_style = filter_info
                is_enabled = force_enabled_style
            else:
                # Normal case - use GroupBox state
                widgets, groupbox = filter_info
                is_enabled = groupbox.isChecked()
            
            for widget in widgets:
                if is_enabled:
                    # Enabled state: white background, black text
                    widget.setStyleSheet("""
                        QLineEdit {
                            color: black !important;
                            background-color: white !important;
                            border: 1px solid #404040;
                        }
                        QLineEdit:focus {
                            color: black !important;
                            background-color: white !important;
                        }
                        QLineEdit:hover {
                            color: black !important;
                            background-color: white !important;
                        }
                    """)
                else:
                    # Disabled state: black background, light grey text
                    widget.setStyleSheet("""
                        QLineEdit {
                            color: #C0C0C0 !important;
                            background-color: black !important;
                            border: 1px solid #404040;
                        }
                        QLineEdit:focus {
                            color: #C0C0C0 !important;
                            background-color: black !important;
                        }
                        QLineEdit:hover {
                            color: #C0C0C0 !important;
                            background-color: black !important;
                        }
                    """)

    def start_operation_log(self, operation_name):
        """Start timing an operation and log the start"""
        self.operation_start_time = time.time()
        # Skip detailed logging in performance mode
        if not self.performance_mode:
            self.update_log(f"=== STARTING: {operation_name} ===", 'blue')
        
    def end_operation_log(self, operation_name, additional_info=""):
        """End timing an operation and log the completion with duration"""
        if self.operation_start_time:
            duration = time.time() - self.operation_start_time
            # Skip detailed logging in performance mode
            if not self.performance_mode:
                status_msg = f"=== COMPLETED: {operation_name} in {duration:.2f} seconds ==="
                if additional_info:
                    status_msg += f" - {additional_info}"
                self.update_log(status_msg, 'green')
            self.operation_start_time = None

    def log_progress(self, current, total, operation="Processing"):
        """Log progress updates with percentage and timing"""
        # Skip progress logging in performance mode
        if self.performance_mode:
            return
            
        if total > 0:
            percentage = (current / total) * 100
            elapsed = time.time() - self.start_time
            if current > 0:
                estimated_total = (elapsed / current) * total
                remaining = estimated_total - elapsed
                self.update_log(f"{operation}: {current}/{total} ({percentage:.1f}%) - "
                              f"Elapsed: {elapsed:.1f}s, Est. remaining: {remaining:.1f}s")
            else:
                self.update_log(f"{operation}: {current}/{total} ({percentage:.1f}%) - "
                              f"Elapsed: {elapsed:.1f}s")

    def log_error(self, error_msg, exception=None):
        """Log errors with detailed information"""
        # Always log errors, even in performance mode
        error_entry = f"*** ERROR: {error_msg} ***"
        if exception:
            error_entry += f"\nException: {str(exception)}"
            if not self.performance_mode:
                error_entry += f"\nTraceback: {traceback.format_exc()}"
        self.update_log(error_entry, 'red')

    def log_warning(self, warning_msg):
        """Log warnings with orange color"""
        # Skip warnings in performance mode
        if not self.performance_mode:
            self.update_log(f"*** WARNING: {warning_msg} ***", 'orange')

    def log_success(self, success_msg):
        """Log success messages with green color"""
        # Skip success messages in performance mode
        if not self.performance_mode:
            self.update_log(f"✓ {success_msg}", 'green')

    def log_info(self, info_msg):
        """Log informational messages with blue color"""
        # Skip info messages in performance mode
        if not self.performance_mode:
            self.update_log(f"ℹ {info_msg}", 'blue')

    def update_log(self, entry, font_color='black'):
        """Enhanced logging function with color support and auto-scroll"""
        # Skip non-error logging in performance mode (except for performance mode toggle messages)
        if self.performance_mode and font_color != 'red' and 'Performance mode' not in entry:
            return
            
        try:
            # Get current timestamp
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Format the log entry
            log_entry = f"{timestamp} {entry}"
            
            # Set text color
            self.log.setTextColor(QtGui.QColor(font_color))
            
            # Append to log
            self.log.append(log_entry)
            
            # Auto-scroll to bottom to show the latest entry
            scrollbar = self.log.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())
            
            # Process events to keep UI responsive (skip in performance mode)
            if not self.performance_mode:
                QtWidgets.QApplication.processEvents()
            
        except Exception as e:
            # Fallback logging if the log widget fails
            print(f"Logging error: {e}")
            print(f"Original entry: {entry}")

    def update_new_data_color_button(self):
        """Enable/disable new data color button based on radio selection"""
        self.new_data_color_btn.setEnabled(self.new_data_single_color_radio.isChecked())

    def update_archive_data_color_button(self):
        """Enable/disable archive data color button based on radio selection"""
        self.archive_data_color_btn.setEnabled(self.archive_data_single_color_radio.isChecked())




    def hover_data(self, event):  # adapted from SO example
        # print('\n\nnew hover event!')
        if self.det and hasattr(self, 'data_rate_ax1') and hasattr(self, 'data_rate_ax2'):
            # print('det exists, making ax_dict')
            # Check if the required attributes exist before creating the dictionary
            if hasattr(self, 'h_data_rate_smoothed') and hasattr(self, 'h_ping_interval'):
                ax_dict = dict(zip([self.data_rate_ax1, self.data_rate_ax2],
                                   [self.h_data_rate_smoothed, self.h_ping_interval]))
            else:
                # If plotting hasn't happened yet, return early
                return
        else:
            # print('det does not exist, returning...')
            return

        for ax in ax_dict.keys():
            # print('working on ax = ', ax)
            # print('*event.inaxes = ', event.inaxes)

            if event.inaxes == ax:  # check if event is in this axis
                # print('***event is in a data rate ax')
                cont, ind = ax_dict[ax].contains(event)  # check if the scatter plot contains this event
                # print('cont, ind =', cont, ind)

                if cont:
                    # print('cont is true')
                    # self.update_annotation(ind)
                    # self.data_canvas.draw_idle()
                    text_all = [self.fnames_sorted[n] for n in ind["ind"]]  # fnames sorted per data plots
                    self.sounding_fname = text_all[0].replace('[\'','').replace('\']','')

                    self.sounding_file_lbl.setText('Cursor: ' + self.sounding_fname)
                    return  # leave after updating
                else:
                    # print('cont is NOT true')
                    self.sounding_file_lbl.setText('Cursor: ' + self.sounding_fname_default)


    def hover(self, event):  # adapted from SO example
        if not self.det or not hasattr(self, 'swath_ax'):
            return

        # print('working on swath_ax=', self.swath_ax)
        # print('*event.inaxes = ', event.inaxes)
        # print('are these equal --> ', event.inaxes == self.swath_ax)

        if event.inaxes == self.swath_ax:
            # print('event.inaxes == self.swath_ax')
            # Check if h_swath exists before trying to use it
            if hasattr(self, 'h_swath') and self.h_swath is not None:
                cont, ind = self.h_swath.contains(event)
                # print('cont, ind =', cont, ind)
                if cont:
                    # print('cont is true')
                    text_all = [self.fnames_all[n] for n in ind["ind"]]  # fnames_all from plot_coverage step
                    # print('got text_all =', text_all)
                    self.sounding_fname = text_all[0].replace('[\'','').replace('\']','')
                    # print('got sounding fname = ', self.sounding_fname)

                    # self.update_annotation(ind)
                    # swath plot has two soundings per fname, stbd then port
                    self.sounding_file_lbl.setText('Cursor: ' + self.sounding_fname)
                else:
                    # print('cont is NOT true')
                    self.sounding_file_lbl.setText('Cursor: ' + self.sounding_fname_default)


    def set_left_layout(self):
        """
        Set up the left panel layout containing file controls, activity log, and progress indicators.
        
        This layout includes:
        - Tabbed interface for different data sources (Raw Swath Files, Swath PKL, Archive Data, Specifications)
        - File management buttons (Add, Remove, Archive, Load)
        - PKL conversion and compression options
        - File list with selection capabilities
        - Activity log with color-coded messages
        - Progress tracking and status information
        - Directory path displays
        """
        # Button dimensions for consistent sizing
        btnh = 20  # height of file control button
        btnw = 130  # width of file control button
        
        # Create file management buttons with tooltips
        self.add_file_btn = PushButton('Add Files', btnw, btnh, 'add_file_btn', 'Add files')
        self.get_indir_btn = PushButton('Add Directory', btnw, btnh, 'get_indir_btn', 'Add a directory')
        self.include_subdir_chk = CheckBox('Incl. subfolders', False, 'include_subdir_chk',
                                           'Include subdirectories when adding a directory')

        # File removal and data management buttons
        self.rmv_file_btn = PushButton('Remove Selected', btnw, btnh, 'rmv_file_btn', 'Remove selected files')
        self.clr_file_btn = PushButton('Remove All Files', btnw, btnh, 'clr_file_btn', 'Remove all files')
        self.archive_data_btn = PushButton('Convert to Archive PKL', btnw, btnh, 'archive_data_btn',
                                           'Archive current data from new files to a .pkl file')
        self.load_archive_btn = PushButton('Add Archive PKL', btnw, btnh, 'load_archive_btn',
                                           'Add archive data from a .pkl file')
        self.archive_compression_chk = CheckBox('Enable compression', True, 'archive_compression_chk',
                                                'Enable gzip compression for archive files (30-70% smaller)')
        
        # PKL file management buttons
        self.load_swath_pkl_btn = PushButton('Add PKL Files', btnw, btnh, 'load_swath_pkl_btn',
                                             'Load pickle files as swath data (faster than source files)')
        self.get_pkl_dir_btn = PushButton('Add Directory', btnw, btnh, 'get_pkl_dir_btn', 'Add a directory of PKL files')
        self.include_pkl_subdir_chk = CheckBox('Incl. subfolders', False, 'include_pkl_subdir_chk',
                                               'Include subdirectories when adding a directory of PKL files')
        self.convert_pickle_btn = PushButton('Convert to Swath PKL', btnw, btnh, 'convert_pickle_btn',
                                             'Convert source files to optimized pickle files for faster loading')
        self.swath_pkl_compression_chk = CheckBox('Enable compression', True, 'swath_pkl_compression_chk',
                                                  'Enable gzip compression for Swath PKL files (30-70% smaller)')
        
        # Analysis and plotting buttons
        self.load_spec_btn = PushButton('Load Spec. Curve', btnw, btnh, 'load_spec_btn',
                                        'IN DEVELOPMENT: Load theoretical performance file')
        self.remove_spec_btn = PushButton('Remove Selected', btnw, btnh, 'remove_spec_btn',
                                          'Remove selected specification curves from the list and plot')
        self.calc_coverage_btn = PushButton('Calc Coverage', btnw, btnh, 'calc_coverage_btn',
                                            'Calculate coverage from loaded files')
        self.calc_coverage_btn.setEnabled(False)  # Disable on startup until files are loaded
        
        # Parameter scanning button (fast mode)
        self.scan_params_btn = PushButton('Scan Params Only', btnw, btnh, 'scan_params_btn',
                                            'Scan acquisition parameters ONLY for loaded files\n\n'
                                            'This can be orders of magnitude faster than parsing full coverage data\n\n'
                                            'See the Parameters and Search tabs for history and search options\n\n'
                                            'WARNING: NO COVERAGE or TIMING data will be parsed or plotted!\n\n'
                                            'NOTE: Zeros will be used for coverage placeholders\n\n'
                                            'Runtime and installation parameter data will be assigned to the first '
                                            'ping time following any parameter changes')
        self.scan_params_btn.setEnabled(False)  # Disable on startup until files are loaded
        
        # Export and save buttons
        self.save_all_plots_btn = PushButton('Save All Plots', btnw, btnh, 'save_all_plots_btn', 'Save all plots (Depth, Backscatter, Ping Mode, Pulse Form, Swath Mode, Frequency, Data Rate, Timing) with settings')

        # Swath PKL file management buttons
        self.remove_swath_pkl_btn = PushButton('Remove Selected', btnw, btnh, 'remove_swath_pkl_btn', 'Remove selected Swath PKL files')
        self.clear_swath_pkl_btn = PushButton('Remove All', btnw, btnh, 'clear_swath_pkl_btn', 'Remove all Swath PKL files')
        
        # Archive file management buttons
        self.remove_archive_btn = PushButton('Remove Selected', btnw, btnh, 'remove_archive_btn', 'Remove selected archive files')
        self.clear_archive_btn = PushButton('Remove All', btnw, btnh, 'clear_archive_btn', 'Remove all archive files')
        
        # Create file list widgets
        self.file_list = FileList()  # add file list with extended selection and icon size = (0,0) to avoid indent
        self.file_list.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        
        self.swath_pkl_file_list = FileList()  # add swath PKL file list with extended selection capabilities
        self.swath_pkl_file_list.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        
        self.archive_file_list = FileList()  # add archive file list with extended selection capabilities
        self.archive_file_list.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        
        self.spec_file_list = FileList()  # add specification curves file list with extended selection capabilities
        self.spec_file_list.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        
        # Connect file list model signals for button state management
        # Check if model exists before connecting signals
        if self.file_list.model():
            self.file_list.model().rowsInserted.connect(self.update_file_buttons)
            self.file_list.model().rowsRemoved.connect(self.update_file_buttons)
        
        # Create tabbed widget for the sources section
        self.sources_tab_widget = QtWidgets.QTabWidget()
        
        # TAB 1: Raw Swath Files
        raw_swath_widget = QtWidgets.QWidget()
        raw_swath_layout = QtWidgets.QVBoxLayout()
        
        # Raw swath files buttons
        raw_swath_btn_layout = BoxLayout([self.add_file_btn, self.get_indir_btn, self.rmv_file_btn,
                                         self.clr_file_btn, self.include_subdir_chk], 'v')
        raw_swath_btn_gb = GroupBox('Raw File Management', raw_swath_btn_layout, False, False, 'raw_swath_btn_gb')
        
        # Process swath files buttons - group related buttons and checkboxes
        swath_pkl_group_layout = BoxLayout([self.convert_pickle_btn, self.swath_pkl_compression_chk], 'v')
        archive_group_layout = BoxLayout([self.archive_data_btn, self.archive_compression_chk], 'v')
        process_btn_layout = BoxLayout([self.calc_coverage_btn, self.scan_params_btn, swath_pkl_group_layout, archive_group_layout], 'v')
        process_btn_gb = GroupBox('Process Raw Files', process_btn_layout, False, False, 'process_btn_gb')
        
        # Show path checkbox for raw swath sources
        self.show_path_chk = CheckBox('Show Path', False, 'show_path_chk',
                                      'Show full file path along with filename in the file list')
        
        # Swath sources file list with show path checkbox
        swath_sources_layout = QtWidgets.QVBoxLayout()
        swath_sources_layout.addWidget(self.file_list)
        swath_sources_layout.addWidget(self.show_path_chk)
        swath_sources_gb = GroupBox('Raw Swath Sources', swath_sources_layout, False, False, 'swath_sources_gb')
        
        # Connect show path checkbox signal after it's created
        self.show_path_chk.toggled.connect(self.toggle_file_path_display)
        
        # Create horizontal layout for File Management and Process Raw Files
        file_process_layout = QtWidgets.QHBoxLayout()
        file_process_layout.addWidget(raw_swath_btn_gb)
        file_process_layout.addWidget(process_btn_gb)
        
        # Combine raw swath components
        raw_swath_layout.addWidget(swath_sources_gb, 1)  # Give file list more space
        raw_swath_layout.addLayout(file_process_layout, 0)  # Minimal space for buttons
        raw_swath_layout.addStretch()
        raw_swath_widget.setLayout(raw_swath_layout)
        self.sources_tab_widget.addTab(raw_swath_widget, "Raw Files")
        
        # TAB 2: Swath PKL
        swath_pkl_widget = QtWidgets.QWidget()
        swath_pkl_layout = QtWidgets.QVBoxLayout()
        
        # Swath PKL buttons - create horizontal layouts for Add/Remove button pairs
        add_remove_layout = BoxLayout([self.load_swath_pkl_btn, self.remove_swath_pkl_btn], 'h')
        dir_clear_layout = BoxLayout([self.get_pkl_dir_btn, self.clear_swath_pkl_btn], 'h')
        swath_pkl_btn_layout = BoxLayout([add_remove_layout, dir_clear_layout, self.include_pkl_subdir_chk], 'v')
        swath_pkl_btn_gb = GroupBox('Swath PKL Management', swath_pkl_btn_layout, False, False, 'swath_pkl_btn_gb')
        
        # Show path checkbox for swath PKL sources
        self.show_swath_pkl_path_chk = CheckBox('Show Path', False, 'show_swath_pkl_path_chk',
                                                'Show full file path along with filename in the Swath PKL file list')
        
        # Swath PKL file list with show path checkbox
        swath_pkl_sources_layout = QtWidgets.QVBoxLayout()
        swath_pkl_sources_layout.addWidget(self.swath_pkl_file_list)
        swath_pkl_sources_layout.addWidget(self.show_swath_pkl_path_chk)
        swath_pkl_list_gb = GroupBox('Swath PKL Sources', swath_pkl_sources_layout, False, False, 'swath_pkl_list_gb')
        
        # Connect show path checkbox signal after it's created
        self.show_swath_pkl_path_chk.toggled.connect(self.toggle_swath_pkl_path_display)
        
        # Connect to file list changes to store original paths
        self.swath_pkl_file_list.itemChanged.connect(self.store_swath_pkl_original_path)
        
        # Combine swath PKL components
        swath_pkl_layout.addWidget(swath_pkl_list_gb, 1)  # Give file list more space
        swath_pkl_layout.addWidget(swath_pkl_btn_gb, 0)  # Minimal space for buttons
        swath_pkl_layout.addStretch()
        swath_pkl_widget.setLayout(swath_pkl_layout)
        self.sources_tab_widget.addTab(swath_pkl_widget, "Swath PKL")
        
        # TAB 3: Archive Data
        archive_data_widget = QtWidgets.QWidget()
        archive_data_layout = QtWidgets.QVBoxLayout()
        
        # Archive data buttons
        archive_btn_layout = BoxLayout([self.load_archive_btn, self.remove_archive_btn, self.clear_archive_btn], 'v')
        archive_btn_gb = GroupBox('Archive PKL Management', archive_btn_layout, False, False, 'archive_btn_gb')
        
        # Archive data file list
        archive_data_list_gb = GroupBox('Archive PKL Sources', BoxLayout([self.archive_file_list], 'v'), False, False, 'archive_data_list_gb')
        
        # Combine archive data components
        archive_data_layout.addWidget(archive_data_list_gb, 1)  # Stretch factor 1 to fill available space
        archive_data_layout.addWidget(archive_btn_gb)
        archive_data_widget.setLayout(archive_data_layout)
        self.sources_tab_widget.addTab(archive_data_widget, "Archive PKL")
        
        # TAB 4: Specifications
        specifications_widget = QtWidgets.QWidget()
        specifications_layout = QtWidgets.QVBoxLayout()
        
        # Specification buttons
        spec_btn_layout = BoxLayout([self.load_spec_btn, self.remove_spec_btn], 'v')
        spec_btn_gb = GroupBox('Specification Management', spec_btn_layout, False, False, 'spec_btn_gb')
        
        # Specification curves file list
        spec_curves_gb = GroupBox('Specification Curves', BoxLayout([self.spec_file_list], 'v'), False, False, 'spec_curves_gb')
        
        # Combine specification components
        specifications_layout.addWidget(spec_curves_gb)
        specifications_layout.addWidget(spec_btn_gb)
        specifications_layout.addStretch()
        specifications_widget.setLayout(specifications_layout)
        self.sources_tab_widget.addTab(specifications_widget, "Spec Curve")
        
        # Create sources group box containing the tabbed widget
        file_gb = GroupBox('Sources', BoxLayout([self.sources_tab_widget], 'v'), False, False, 'file_gb')
        
        # Create activity log widget for user feedback
        self.log = TextEdit("background-color: white", True, 'log')
        self.log.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.log.setMinimumHeight(200)  # Set minimum height to force more space for activity log
        self.update_log('*** New swath coverage processing log ***', 'blue')
        log_gb = GroupBox('Activity Log', BoxLayout([self.log], 'v'), False, False, 'log_gb')

        # Create progress tracking and status display widgets
        self.current_file_lbl = Label('Current file:')
        self.sounding_file_lbl = Label('Cursor: ' + self.sounding_fname_default)
        
        # Progress bar for overall processing
        calc_pb_lbl = Label('Total Progress:')
        self.calc_pb = QtWidgets.QProgressBar()
        self.calc_pb.setGeometry(0, 0, 150, 30)
        self.calc_pb.setMaximum(100)  # this will update with number of files
        self.calc_pb.setValue(0)
        calc_pb_layout = BoxLayout([calc_pb_lbl, self.calc_pb], 'h')
        
        # Combine status information and progress bar
        self.prog_layout = BoxLayout([self.current_file_lbl, self.sounding_file_lbl], 'v')
        self.prog_layout.addLayout(calc_pb_layout)

        # Set the left panel layout with file controls on top and log on bottom
        # Sources area gets 75% of space, activity log gets 25%
        self.left_layout = QtWidgets.QVBoxLayout()
        self.left_layout.addWidget(file_gb, 7)  # Sources area gets 70% of space (stretch factor 7)
        self.left_layout.addWidget(log_gb, 3)   # Activity log gets 30% of space (stretch factor 3)
        self.left_layout.addLayout(self.prog_layout, 0)  # Progress area gets minimal space

    def update_file_buttons(self):
        """
        Update the enabled state of file-dependent buttons based on whether files are loaded.
        
        This method is called whenever files are added or removed from the file list.
        """
        # Check for .all or .kmall files specifically
        has_source_files = False
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item and (item.text().endswith('.all') or item.text().endswith('.kmall')):
                has_source_files = True
                break
        
        self.calc_coverage_btn.setEnabled(has_source_files)
        self.scan_params_btn.setEnabled(has_source_files)
        self.convert_pickle_btn.setEnabled(has_source_files)
        
        # Update Convert to Swath PKL button color
        if has_source_files:
            self.convert_pickle_btn.setStyleSheet("background-color: #FFB347; color: black; font-weight: bold;")
        else:
            self.convert_pickle_btn.setStyleSheet("")
        
        # Update Save All Plots button color based on data availability
        self.update_save_plots_button_color()

    def toggle_file_path_display(self):
        """
        Toggle the display of file paths in the file list based on the show path checkbox.
        """
        show_path = self.show_path_chk.isChecked()
        
        # Update each item in the file list
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item:
                current_text = item.text()
                
                if show_path:
                    # Show full path - if it's already a full path, keep it as is
                    if not os.path.isabs(current_text):
                        # If it's a relative path, try to make it absolute
                        # This assumes the file is in the current working directory or input directory
                        if hasattr(self, 'input_dir') and self.input_dir:
                            full_path = os.path.join(self.input_dir, current_text)
                            if os.path.exists(full_path):
                                item.setText(full_path)
                        else:
                            # Try current working directory
                            full_path = os.path.abspath(current_text)
                            if os.path.exists(full_path):
                                item.setText(full_path)
                else:
                    # Show only filename
                    filename = os.path.basename(current_text)
                    item.setText(filename)

    def toggle_swath_pkl_path_display(self):
        """
        Toggle the display of file paths in the Swath PKL file list based on the show path checkbox.
        """
        show_path = self.show_swath_pkl_path_chk.isChecked()
        
        # Update each item in the Swath PKL file list
        for i in range(self.swath_pkl_file_list.count()):
            item = self.swath_pkl_file_list.item(i)
            if item:
                current_text = item.text()
                
                # Store the original path if not already stored
                if i not in self.original_swath_pkl_paths:
                    # If we don't have the original path stored, use the current text as original
                    self.original_swath_pkl_paths[i] = current_text
                
                if show_path:
                    # Show full path - use stored original path or current text
                    original_path = self.original_swath_pkl_paths.get(i, current_text)
                    if not os.path.isabs(original_path):
                        # If it's a relative path, try to make it absolute
                        if hasattr(self, 'input_dir') and self.input_dir:
                            full_path = os.path.join(self.input_dir, original_path)
                            if os.path.exists(full_path):
                                item.setText(full_path)
                            else:
                                item.setText(original_path)
                        else:
                            # Try current working directory
                            full_path = os.path.abspath(original_path)
                            if os.path.exists(full_path):
                                item.setText(full_path)
                            else:
                                item.setText(original_path)
                    else:
                        # Already an absolute path
                        item.setText(original_path)
                else:
                    # Show only filename
                    original_path = self.original_swath_pkl_paths.get(i, current_text)
                    filename = os.path.basename(original_path)
                    item.setText(filename)

    def store_swath_pkl_original_path(self, item):
        """
        Store the original path when a new item is added to the Swath PKL file list.
        """
        if item:
            # Find the index of the item
            for i in range(self.swath_pkl_file_list.count()):
                if self.swath_pkl_file_list.item(i) == item:
                    # Store the original path if not already stored
                    if i not in self.original_swath_pkl_paths:
                        self.original_swath_pkl_paths[i] = item.text()
                    break

    def update_save_plots_button_color(self):
        """
        Update the Save All Plots button color based on data availability.
        Green text when data is available, default color when not.
        """
        has_data = False
        
        # Check if there's processed data (det dictionary has content)
        if hasattr(self, 'det') and self.det:
            has_data = True
        
        # Check if there's archive data
        if hasattr(self, 'det_archive') and self.det_archive:
            has_data = True
        
        # Check if there's data_new (from Swath PKL files)
        if hasattr(self, 'data_new') and self.data_new:
            has_data = True
        
        # Set button color
        if has_data:
            self.save_all_plots_btn.setStyleSheet("background-color: lightgreen; color: black; font-weight: bold;")
        else:
            self.save_all_plots_btn.setStyleSheet("")

    def remove_selected_archive_files(self):
        """
        Remove selected archive files from the archive file list and data structures.
        """
        selected_items = self.archive_file_list.selectedItems()
        if not selected_items:
            return
        
        removed_files = []
        for item in selected_items:
            filename = item.text()
            removed_files.append(filename)
            # Remove from archive data structures
            if filename in self.det_archive:
                self.det_archive.pop(filename, None)
            if filename in self.archive_filenames:
                self.archive_filenames.remove(filename)
            # Remove from file list widget
            self.archive_file_list.takeItem(self.archive_file_list.row(item))
        
        if removed_files:
            self.update_log(f"Removed {len(removed_files)} archive file(s): {', '.join(removed_files)}")
            # Update button states and refresh plot if needed
            self.update_file_buttons()
            if hasattr(self, 'refresh_plot'):
                refresh_plot(self, call_source='remove_archive_files')

    def clear_all_archive_files(self):
        """
        Clear all archive files from the archive file list and data structures.
        """
        if self.archive_file_list.count() == 0:
            return
        
        self.archive_file_list.clear()
        self.det_archive = {}
        self.archive_filenames = []
        self.show_data_chk_arc.setChecked(False)
        
        self.update_log("Cleared all archive files")
        # Update button states and refresh plot if needed
        self.update_file_buttons()
        if hasattr(self, 'refresh_plot'):
            refresh_plot(self, call_source='clear_all_archive_files')

    def remove_selected_swath_pkl_files(self):
        """
        Remove selected Swath PKL files from the swath PKL file list and data structures.
        """
        selected_items = self.swath_pkl_file_list.selectedItems()
        if not selected_items:
            return
        
        removed_files = []
        for item in selected_items:
            filename = item.text()
            removed_files.append(filename)
            # Remove from file list widget
            self.swath_pkl_file_list.takeItem(self.swath_pkl_file_list.row(item))
            # Remove from data structures if they exist
            if hasattr(self, 'data_new') and self.data_new:
                # Find and remove from data_new
                for key in list(self.data_new.keys()):
                    if self.data_new[key].get('fname', '') == filename:
                        del self.data_new[key]
                        break
        
        if removed_files:
            self.update_log(f"Removed {len(removed_files)} Swath PKL file(s): {', '.join(removed_files)}")
            # Update button states and refresh plot if needed
            self.update_file_buttons()
            if hasattr(self, 'refresh_plot'):
                refresh_plot(self, call_source='remove_swath_pkl_files')

    def clear_all_swath_pkl_files(self):
        """
        Clear all Swath PKL files from the swath PKL file list and data structures.
        """
        if self.swath_pkl_file_list.count() == 0:
            return
        
        # Get all files from the swath PKL file list
        pkl_files = []
        for i in range(self.swath_pkl_file_list.count()):
            item = self.swath_pkl_file_list.item(i)
            if item:
                pkl_files.append(item.text())
        
        # Clear the swath PKL file list
        self.swath_pkl_file_list.clear()
        
        # Clear data_new if it exists
        if hasattr(self, 'data_new'):
            self.data_new = {}
        
        self.update_log(f"Cleared {len(pkl_files)} Swath PKL file(s)")
        # Update button states and refresh plot if needed
        self.update_file_buttons()
        if hasattr(self, 'refresh_plot'):
            refresh_plot(self, call_source='clear_all_swath_pkl_files')

    def remove_selected_spec_curves(self):
        """
        Remove selected specification curves from the spec file list and data structures.
        """
        selected_items = self.spec_file_list.selectedItems()
        if not selected_items:
            self.update_log("No specification curves selected for removal")
            return
        
        removed_files = []
        for item in selected_items:
            filename = item.text()
            removed_files.append(filename)
            # Remove from spec data structures
            if hasattr(self, 'spec') and filename in self.spec:
                del self.spec[filename]
            # Remove from spec colors
            if hasattr(self, 'spec_colors') and filename in self.spec_colors:
                del self.spec_colors[filename]
            # Remove from file list widget
            self.spec_file_list.takeItem(self.spec_file_list.row(item))
        
        if removed_files:
            self.update_log(f"Removed {len(removed_files)} specification curve(s): {', '.join(removed_files)}")
            # Refresh plot to remove spec lines
            if hasattr(self, 'refresh_plot'):
                refresh_plot(self, call_source='remove_selected_spec_curves')

    def set_center_layout(self):
        """
        Set up the center panel layout containing all the plotting canvases and toolbars.
        
        This layout includes multiple matplotlib figures for different plot types:
        - Swath coverage plot (main plot)
        - Backscatter plot
        - Ping mode plot
        - Pulse form plot
        - Swath mode plot
        - Frequency plot
        - Data rate plot
        - Timing plot
        
        Each plot has its own canvas, figure, and navigation toolbar.
        """
        # Main swath coverage plot setup
        self.swath_canvas_height = 14
        self.swath_canvas_width = 12
        self.swath_figure = Figure(figsize=(self.swath_canvas_width, self.swath_canvas_height))  # figure instance
        self.swath_canvas = FigureCanvas(self.swath_figure)  # canvas widget that displays the figure
        self.swath_canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                        QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.swath_toolbar = NavigationToolbar(self.swath_canvas, self)  # swath plot toolbar
        self.swath_layout = BoxLayout([self.swath_toolbar, self.swath_canvas], 'v')

        # Backscatter plot setup
        self.backscatter_canvas_height = 14
        self.backscatter_canvas_width = 12
        self.backscatter_figure = Figure(figsize=(self.backscatter_canvas_width, self.backscatter_canvas_height))
        self.backscatter_canvas = FigureCanvas(self.backscatter_figure)
        self.backscatter_canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                              QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.backscatter_toolbar = NavigationToolbar(self.backscatter_canvas, self)
        self.backscatter_layout = BoxLayout([self.backscatter_toolbar, self.backscatter_canvas], 'v')

        # Ping mode plot setup
        self.pingmode_canvas_height = 14
        self.pingmode_canvas_width = 12
        self.pingmode_figure = Figure(figsize=(self.pingmode_canvas_width, self.pingmode_canvas_height))
        self.pingmode_canvas = FigureCanvas(self.pingmode_figure)
        self.pingmode_canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                           QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.pingmode_toolbar = NavigationToolbar(self.pingmode_canvas, self)
        self.pingmode_layout = BoxLayout([self.pingmode_toolbar, self.pingmode_canvas], 'v')

        # Pulse form plot setup
        self.pulseform_canvas_height = 14
        self.pulseform_canvas_width = 12
        self.pulseform_figure = Figure(figsize=(self.pulseform_canvas_width, self.pulseform_canvas_height))
        self.pulseform_canvas = FigureCanvas(self.pulseform_figure)
        self.pulseform_canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                            QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.pulseform_toolbar = NavigationToolbar(self.pulseform_canvas, self)
        self.pulseform_layout = BoxLayout([self.pulseform_toolbar, self.pulseform_canvas], 'v')

        # Swath mode plot setup
        self.swathmode_canvas_height = 14
        self.swathmode_canvas_width = 12
        self.swathmode_figure = Figure(figsize=(self.swathmode_canvas_width, self.swathmode_canvas_height))
        self.swathmode_canvas = FigureCanvas(self.swathmode_figure)
        self.swathmode_canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                            QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.swathmode_toolbar = NavigationToolbar(self.swathmode_canvas, self)
        self.swathmode_layout = BoxLayout([self.swathmode_toolbar, self.swathmode_canvas], 'v')

        # Frequency plot setup
        self.frequency_canvas_height = 14
        self.frequency_canvas_width = 12
        self.frequency_figure = Figure(figsize=(self.frequency_canvas_width, self.frequency_canvas_height))
        self.frequency_canvas = FigureCanvas(self.frequency_figure)
        self.frequency_canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                            QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.frequency_toolbar = NavigationToolbar(self.frequency_canvas, self)
        self.frequency_layout = BoxLayout([self.frequency_toolbar, self.frequency_canvas], 'v')

        # Data rate plot setup (smaller size for secondary plots)
        self.data_canvas_height = 10
        self.data_canvas_width = 10
        self.data_figure = Figure(figsize=(self.data_canvas_width, self.data_canvas_height))
        self.data_canvas = FigureCanvas(self.data_figure)
        self.data_canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                       QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.data_toolbar = NavigationToolbar(self.data_canvas, self)
        self.x_max_data = 0.0
        self.y_max_data = 0.0
        self.data_layout = BoxLayout([self.data_toolbar, self.data_canvas], 'v')

        # Data timing plot setup (smaller size for secondary plots)
        self.time_canvas_height = 10
        self.time_canvas_width = 10
        self.time_figure = Figure(figsize=(self.time_canvas_width, self.time_canvas_height))
        self.time_canvas = FigureCanvas(self.time_figure)
        self.time_canvas.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                       QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.time_toolbar = NavigationToolbar(self.time_canvas, self)
        self.x_max_time = 0.0
        self.y_max_time = 0.0
        self.time_layout = BoxLayout([self.time_toolbar, self.time_canvas], 'v')

        # Parameter log widget for the Parameters tab
        self.param_log = TextEdit("background-color: lightgray", True, 'log')
        self.param_log.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        update_param_log(self, '*** New acquisition parameter log ***')
        param_log_gb = GroupBox('Runtime Parameter Log', BoxLayout([self.param_log], 'v'), False, False, 'param_log_gb')
        self.param_layout = BoxLayout([param_log_gb], 'v')

        # set up tabs
        self.plot_tabs = QtWidgets.QTabWidget()
        self.plot_tabs.setStyleSheet("background-color: none")
        self.plot_tabs.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)

        # set up tab 1: swath coverage
        self.plot_tab1 = QtWidgets.QWidget()
        self.plot_tab1.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab1_layout = self.swath_layout
        self.plot_tab1.setLayout(self.plot_tab1_layout)

        # set up tab 2: backscatter
        self.plot_tab2 = QtWidgets.QWidget()
        self.plot_tab2.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab2_layout = self.backscatter_layout
        self.plot_tab2.setLayout(self.plot_tab2_layout)

        # set up tab 3: ping mode
        self.plot_tab3 = QtWidgets.QWidget()
        self.plot_tab3.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab3_layout = self.pingmode_layout
        self.plot_tab3.setLayout(self.plot_tab3_layout)

        # set up tab 4: pulse form
        self.plot_tab4 = QtWidgets.QWidget()
        self.plot_tab4.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab4_layout = self.pulseform_layout
        self.plot_tab4.setLayout(self.plot_tab4_layout)

        # set up tab 5: swath mode
        self.plot_tab5 = QtWidgets.QWidget()
        self.plot_tab5.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab5_layout = self.swathmode_layout
        self.plot_tab5.setLayout(self.plot_tab5_layout)

        # set up tab 6: frequency
        self.plot_tab6 = QtWidgets.QWidget()
        self.plot_tab6.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab6_layout = self.frequency_layout
        self.plot_tab6.setLayout(self.plot_tab6_layout)

        # set up tab 7: data rate
        self.plot_tab7 = QtWidgets.QWidget()
        self.plot_tab7.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab7_layout = self.data_layout
        self.plot_tab7.setLayout(self.plot_tab7_layout)

        # set up tab 8: timing
        self.plot_tab8 = QtWidgets.QWidget()
        self.plot_tab8.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab8_layout = self.time_layout
        self.plot_tab8.setLayout(self.plot_tab8_layout)

        # set up tab 9: runtime parameters
        self.plot_tab9 = QtWidgets.QWidget()
        self.plot_tab9.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        self.plot_tab9_layout = self.param_layout
        self.plot_tab9.setLayout(self.plot_tab9_layout)

        # add tabs to tab layout
        self.plot_tabs.addTab(self.plot_tab1, 'Depth')
        self.plot_tabs.addTab(self.plot_tab2, 'Backscatter')
        self.plot_tabs.addTab(self.plot_tab3, 'Ping Mode')
        self.plot_tabs.addTab(self.plot_tab4, 'Pulse Form')
        self.plot_tabs.addTab(self.plot_tab5, 'Swath Mode')
        self.plot_tabs.addTab(self.plot_tab6, 'Frequency')
        self.plot_tabs.addTab(self.plot_tab7, 'Data Rate')
        self.plot_tabs.addTab(self.plot_tab8, 'Timing')
        self.plot_tabs.addTab(self.plot_tab9, 'Parameters')

        self.center_layout = BoxLayout([self.plot_tabs], 'v')
        # self.center_layout.addStretch()

    
    def set_right_layout(self):
        # set right layout with swath plot controls
        # add text boxes for system, ship, cruise
        
        # Export Gap Filler button and controls (moved from left panel)
        self.export_gf_btn = PushButton('Export Gap Filler', 100, 20, 'export_gf_btn',
                                             'Export text file of swath coverage trend for Gap Filler import')
        self.export_gf_cbox = ComboBox(['New', 'Archive'], 55, 20, 'export_gf_cbox',
                                       'Select data source to use for trend export')
        model_tb_lbl = Label('Model:', width=100, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.model_cbox = ComboBox(self.model_list, 100, 20, 'model_cbox', 'Select the model')
        self.show_model_chk = CheckBox('', True, 'show_model_chk', 'Show model in plot title')
        model_info_layout_left = BoxLayout([model_tb_lbl, self.model_cbox], 'h',
                                           alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        model_info_layout = BoxLayout([model_info_layout_left, self.show_model_chk], 'h',
                                      alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

        ship_tb_lbl = Label('Ship Name:', width=100, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.ship_tb = LineEdit('R/V Unsinkable II', 100, 20, 'ship_tb', 'Enter the ship name')
        self.show_ship_chk = CheckBox('', True, 'show_ship_chk', 'Show ship name in plot title')
        ship_info_layout_left = BoxLayout([ship_tb_lbl, self.ship_tb], 'h',
                                          alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        ship_info_layout = BoxLayout([ship_info_layout_left, self.show_ship_chk], 'h',
                                     alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

        cruise_tb_lbl = Label('Description:', width=100, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.cruise_tb = LineEdit('A 3-hour tour', 100, 20, 'cruise_tb', 'Enter the description')
        self.show_cruise_chk = CheckBox('', True, 'show_cruise_chk', 'Show cruise in plot title')
        cruise_info_layout_left = BoxLayout([cruise_tb_lbl, self.cruise_tb], 'h',
                                            alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        cruise_info_layout = BoxLayout([cruise_info_layout_left, self.show_cruise_chk], 'h',
                                       alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

        self.custom_info_gb = GroupBox('Use custom system information',
                                       BoxLayout([model_info_layout, ship_info_layout, cruise_info_layout], 'v'),
                                       True, False, 'custom_info_gb')
        self.custom_info_gb.setToolTip('Add system/cruise info; system info parsed from the file is used if available')

        # add depth reference options and groupbox
        self.ref_cbox = ComboBox(self.depth_ref_list, 100, 20, 'ref_cbox',
                                 'Select the reference for plotting depth and acrosstrack distance\n\n'
                                 'As parsed, .all depths are referenced to the TX array and .kmall depths are '
                                 'referenced to the mapping system origin in SIS\n\n'
                                 'Waterline reference is appropriate for normal surface vessel data; '
                                 'other options are available for special cases (e.g., underwater vehicles or '
                                 'troubleshooting installation offset discrepancies)\n\n'
                                 'Overview of adjustments:\n\nWaterline: change reference to the waterline '
                                 '(.all: shift Y and Z ref from TX array to origin, then Z ref to waterline; '
                                 '.kmall: shift Z ref from origin to waterline)\n\n'
                                 'Origin: change reference to the mapping system origin '
                                 '(.all: shift Y and Z ref from TX array to origin; .kmall: no change)\n\n'
                                 'TX Array: change reference to the TX array reference point '
                                 '(.all: no change; .kmall: shift Y and Z ref from origin to TX array)\n\n'
                                 'Raw: use the native depths and acrosstrack distances parsed from the file '
                                 '(.all: referenced to TX array; .kmall: referenced to mapping system origin)')

        depth_ref_lbl = Label('Reference data to:', 100, 20, 'depth_ref_lbl', (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        depth_ref_layout = BoxLayout([depth_ref_lbl, self.ref_cbox], 'h')
        self.depth_ref_gb = GroupBox('Depth reference', depth_ref_layout, False, False, 'depth_ref_gb')

        # add point color options for swath data (was new data)
        self.show_data_chk = CheckBox('Swath data', True, 'show_data_chk', 'Show swath data')
        self.new_data_color_by_type_radio = RadioButton('Color by data type', True, 'new_data_color_by_type_radio', 
                                                       'Color swath data according to the tab type (depth, backscatter, ping mode, etc.)')
        self.new_data_single_color_radio = RadioButton('Single color', False, 'new_data_single_color_radio',
                                                      'Use a single color for all swath data')
        self.new_data_color_btn = PushButton('Select Color', 80, 20, 'new_data_color_btn', 'Select solid color for swath data')
        self.new_data_color_btn.setEnabled(False)  # disable until 'Single color' is selected
        new_data_color_layout = BoxLayout([self.new_data_color_by_type_radio, self.new_data_single_color_radio, self.new_data_color_btn], 'v')
        cbox_layout_new = BoxLayout([self.show_data_chk, new_data_color_layout], 'v')

        # add point color options for archive data
        self.show_data_chk_arc = CheckBox('Archive data', False, 'show_data_chk_arc', 'Show archive data')
        self.archive_data_color_by_type_radio = RadioButton('Color by data type', False, 'archive_data_color_by_type_radio',
                                                           'Color archive data according to the tab type (depth, backscatter, ping mode, etc.)')
        self.archive_data_single_color_radio = RadioButton('Single color', True, 'archive_data_single_color_radio',
                                                          'Use a single color for all archive data')
        self.archive_data_color_btn = PushButton('Select Color', 80, 20, 'archive_data_color_btn', 'Select solid color for archive data')
        self.archive_data_color_btn.setEnabled(True)  # enabled since single color is default
        # Set default archive color to light grey
        self.color_arc = QtGui.QColor('lightGray')
        archive_data_color_layout = BoxLayout([self.archive_data_color_by_type_radio, self.archive_data_single_color_radio, self.archive_data_color_btn], 'v')
        cbox_layout_arc = BoxLayout([self.show_data_chk_arc, archive_data_color_layout], 'v')
        cmode_layout = BoxLayout([cbox_layout_new, cbox_layout_arc], 'h')

        # add selection for data to plot last (on top)
        top_data_lbl = Label('Plot data on top:', width=90, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.top_data_cbox = ComboBox(self.top_data_list, 90, 20, 'top_data_cbox',
                                      'Select the loaded dataset to plot last (on top)\n\n'
                                      'NOTE: the colorbar or legend, if shown, will correspond to the "top" dataset; '
                                      'the colorbar or legend may not clearly represent all data shown if '
                                      'a) the option to apply color modes to data plots is checked, and '
                                      'b) the new and archive color modes do not match.')
        top_data_layout = BoxLayout([top_data_lbl, self.top_data_cbox], 'h')

        # add color limit options
        clim_cbox_lbl = Label('Scale colormap to:', width=90, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.clim_cbox = ComboBox(self.clim_list, 90, 20, 'clim_cbox',
                                  'Scale the colormap limits to fit all unfiltered data, user-filtered '
                                  'data (e.g., masked for depth or backscatter), or fixed values.\n\n'
                                  'If the same color mode is used for new and archive data, then the colormap '
                                  'and its limits are scaled to all plotted data according to the selected '
                                  'colormap limit scheme.\n\n'
                                  'If different color modes are used, the colormap and its limits are scaled '
                                  'to the dataset plotted last (on top) according to the selected colormap '
                                  'limit scheme.\n\n'
                                  'Note: The order of plotting can be reversed by the user, e.g., to '
                                  'plot archive data on top.')
        clim_options_layout = BoxLayout([clim_cbox_lbl, self.clim_cbox], 'h')
        pt_param_layout_top = BoxLayout([top_data_layout, clim_options_layout], 'v')
        pt_param_layout_top.addStretch()

        # add fixed color limit options
        min_clim_lbl = Label('Min:', width=40, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.min_clim_tb = LineEdit(str(self.clim_last_user['depth'][0]), 40, 20, 'min_clim_tb',
                                    'Set the minimum color limit')
        self.min_clim_tb.setEnabled(False)
        min_clim_layout = BoxLayout([min_clim_lbl, self.min_clim_tb], 'h')
        max_clim_lbl = Label('Max:', width=40, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.max_clim_tb = LineEdit(str(self.clim_last_user['depth'][1]), 40, 20, 'max_clim_tb',
                                    'Set the maximum color limit')
        self.max_clim_tb.setEnabled(False)
        max_clim_layout = BoxLayout([max_clim_lbl, self.max_clim_tb], 'h')
        self.min_clim_tb.setValidator(QDoubleValidator(-1*np.inf, np.inf, 2))
        self.max_clim_tb.setValidator(QDoubleValidator(-1*np.inf, np.inf, 2))

        pt_param_layout_right = BoxLayout([min_clim_layout, max_clim_layout], 'v')

        # add point size and opacity comboboxes
        self.pt_size_cbox = ComboBox([str(pt) for pt in range(1,11)], 45, 20, 'pt_size_cbox', 'Select point size')
        self.pt_size_cbox.setCurrentIndex(4)

        # set point size layout
        pt_size_lbl = Label('Point size:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        pt_size_layout = BoxLayout([pt_size_lbl, self.pt_size_cbox], 'h')
        pt_size_layout.addStretch()

        # add point transparency/opacity slider (can help to visualize density of data)
        pt_alpha_lbl = Label('Opacity (%):', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.pt_alpha_cbox = ComboBox([str(10 * pt) for pt in range(1,11)], 45, 20, 'pt_alpha_cbox', 'Select opacity')
        self.pt_alpha_cbox.setCurrentIndex(self.pt_alpha_cbox.count() - 1)  # update opacity to greatest value
        pt_alpha_layout = BoxLayout([pt_alpha_lbl, self.pt_alpha_cbox], 'h')
        pt_alpha_layout.addStretch()

        # set final point parameter layout with color modes, colorscale limit options, point size, and opacity
        pt_param_layout_left = BoxLayout([pt_size_lbl, pt_alpha_lbl], 'v')
        pt_param_layout_center = BoxLayout([self.pt_size_cbox, self.pt_alpha_cbox], 'v')
        pt_param_layout_bottom = BoxLayout([pt_param_layout_left, pt_param_layout_center, pt_param_layout_right], 'h')
        pt_param_layout = BoxLayout([cmode_layout, pt_param_layout_top, pt_param_layout_bottom], 'v')
        pt_param_gb = GroupBox('Point style', pt_param_layout, False, False, 'pt_param_gb')

        # add custom plot axis limits
        max_z_lbl = Label('Depth:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        max_x_lbl = Label('Width:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        max_dr_lbl = Label('Data rate:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        max_pi_lbl = Label('Ping int.:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

        self.max_z_tb = LineEdit('', 40, 20, 'max_z_tb', 'Set the maximum depth of the plot')
        self.max_z_tb.setValidator(QDoubleValidator(0, 15000, 2))
        self.max_x_tb = LineEdit('', 40, 20, 'max_x_tb', 'Set the maximum width of the plot')
        self.max_x_tb.setValidator(QDoubleValidator(0, 30000, 2))
        self.max_dr_tb = LineEdit('', 40, 20, 'max_dr_tb', 'Set the maximum data rate of the plot')
        self.max_dr_tb.setValidator(QDoubleValidator(0, np.inf, 2))
        self.max_pi_tb = LineEdit('', 40, 20, 'max_pi_tb', 'Set the maximum ping interval of the plot')
        self.max_pi_tb.setValidator(QDoubleValidator(0, np.inf, 2))
        # plot_lim_layout = BoxLayout([max_z_lbl, self.max_z_tb, max_x_lbl, self.max_x_tb], 'h')
        plot_lim_layout_upper = BoxLayout([max_z_lbl, self.max_z_tb, max_x_lbl, self.max_x_tb], 'h')
        plot_lim_layout_lower = BoxLayout([max_dr_lbl, self.max_dr_tb, max_pi_lbl, self.max_pi_tb], 'h')
        plot_lim_layout = BoxLayout([plot_lim_layout_upper, plot_lim_layout_lower], 'v')
        self.plot_lim_gb = GroupBox('Use custom plot limits', plot_lim_layout, True, False, 'plot_lim_gb')
        self.plot_lim_gb.setToolTip('Set maximum depth and width (0-30000 m) to override automatic plot scaling.')

        # add custom swath angle limits
        min_angle_lbl = Label('Min:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        max_angle_lbl = Label('Max:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.min_angle_tb = LineEdit('0', 40, 20, 'min_angle_tb', 'Set the minimum angle to plot (<= max angle)')
        self.max_angle_tb = LineEdit('75', 40, 20, 'max_angle_tb', 'Set the maximum angle to plot (>= min angle)')
        angle_layout = BoxLayout([min_angle_lbl, self.min_angle_tb, max_angle_lbl, self.max_angle_tb], 'h')
        self.angle_gb = GroupBox('Angle (deg)', angle_layout, True, False, 'angle_gb')
        self.angle_gb.setToolTip('Hide soundings based on nominal swath angles calculated from depths and '
                                 'acrosstrack distances; these swath angles may differ slightly from RX beam '
                                 'angles (w.r.t. RX array) due to installation, attitude, and refraction.')
        self.min_angle_tb.setValidator(QDoubleValidator(0, float(self.max_angle_tb.text()), 2))
        self.max_angle_tb.setValidator(QDoubleValidator(float(self.min_angle_tb.text()), np.inf, 2))

        # add custom depth limits
        min_depth_lbl = Label('Min depth (m):', alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        max_depth_lbl = Label('Max depth (m):', alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.min_depth_tb = LineEdit('0', 40, 20, 'min_depth_tb', 'Min depth of the new data')
        self.min_depth_arc_tb = LineEdit('0', 40, 20, 'min_depth_arc_tb', 'Min depth of the archive data')
        self.max_depth_tb = LineEdit('10000', 40, 20, 'max_depth_tb', 'Max depth of the new data')
        self.max_depth_arc_tb = LineEdit('10000', 40, 20, 'max_depth_arc_tb', 'Max depth of the archive data')
        self.min_depth_tb.setValidator(QDoubleValidator(0, float(self.max_depth_tb.text()), 2))
        self.max_depth_tb.setValidator(QDoubleValidator(float(self.min_depth_tb.text()), np.inf, 2))
        self.min_depth_arc_tb.setValidator(QDoubleValidator(0, float(self.max_depth_arc_tb.text()), 2))
        self.max_depth_arc_tb.setValidator(QDoubleValidator(float(self.min_depth_arc_tb.text()), np.inf, 2))
        depth_layout_left = BoxLayout([QtWidgets.QLabel(''), min_depth_lbl, max_depth_lbl], 'v')
        depth_layout_center = BoxLayout([QtWidgets.QLabel('New'), self.min_depth_tb, self.max_depth_tb], 'v')
        depth_layout_right = BoxLayout([QtWidgets.QLabel('Archive'), self.min_depth_arc_tb, self.max_depth_arc_tb], 'v')
        depth_layout = BoxLayout([depth_layout_left, depth_layout_center, depth_layout_right], 'h')
        self.depth_gb = GroupBox('Depth (new/archive)', depth_layout, True, False, 'depth_gb')
        self.depth_gb.setToolTip('Hide data by depth (m, positive down).\n\nAcceptable min/max fall within [0 inf].')

        # add custom reported backscatter limits
        min_bs_lbl = Label('Min:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.min_bs_tb = LineEdit('-50', 40, 20, 'min_bs_tb',
                                  'Set the minimum reported backscatter (e.g., -50 dB); '
                                  'while backscatter values in dB are inherently negative, the filter range may '
                                  'include positive values to accommodate anomalous reported backscatter data')
        max_bs_lbl = Label('Max:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.max_bs_tb = LineEdit('0', 40, 20, 'max_bs_tb',
                                  'Set the maximum reported backscatter of the data (e.g., 0 dB); '
                                  'while backscatter values in dB are inherently negative, the filter range may '
                                  'include positive values to accommodate anomalous reported backscatter data')
        self.min_bs_tb.setValidator(QDoubleValidator(-1*np.inf, float(self.max_bs_tb.text()), 2))
        self.max_bs_tb.setValidator(QDoubleValidator(float(self.min_bs_tb.text()), np.inf, 2))
        bs_layout = BoxLayout([min_bs_lbl, self.min_bs_tb, max_bs_lbl, self.max_bs_tb], 'h')
        self.bs_gb = GroupBox('Backscatter (dB)', bs_layout, True, False, 'bs_gb')
        self.bs_gb.setToolTip('Hide data by reported backscatter amplitude (dB).\n\n'
                              'Acceptable min/max fall within [-inf inf] to accommodate anomalous data >0.')

        # add custom ping interval limits
        min_ping_int_lbl = Label('Min:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.min_ping_int_tb = LineEdit('0.25', 40, 20, 'min_ping_int_tb',
                                        'Set the minimum ping interval (e.g., 0.25 sec)')
        max_ping_int_lbl = Label('Max:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.max_ping_int_tb = LineEdit('20', 40, 20, 'max_ping_int_tb',
                                  'Set the maximum ping interval (e.g., 15 sec)')
        self.min_ping_int_tb.setValidator(QDoubleValidator(-1 * np.inf, float(self.max_ping_int_tb.text()), 2))
        self.max_ping_int_tb.setValidator(QDoubleValidator(float(self.min_ping_int_tb.text()), np.inf, 2))
        ping_int_layout = BoxLayout([min_ping_int_lbl, self.min_ping_int_tb, max_ping_int_lbl, self.max_ping_int_tb], 'h')
        self.ping_int_gb = GroupBox('Ping Interval (sec)', ping_int_layout, True, False, 'ping_int_gb')
        self.ping_int_gb.setToolTip('Hide data by detected ping interval (sec).\n\n'
                                    'Filtering is applied to the time interval between swaths and affects only the '
                                    'ping interval plot.  The minimum filter value should be a small non-zero value'
                                    'to exclude the very short intervals between swaths in dual-swath operation and '
                                    'more clearly show the time intervals between the major ping cycles.')

        # add custom threshold/buffer for comparing RX beam angles to runtime parameters
        rtp_angle_buffer_lbl = Label('Angle buffer (+/-10 deg):', width=40, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.rtp_angle_buffer_tb = LineEdit(str(self.rtp_angle_buffer_default), 40, 20, 'rtp_angle_buffer_tb', '')
        self.rtp_angle_buffer_tb.setValidator(QDoubleValidator(-10, 10, 2))
        rtp_angle_layout = BoxLayout([rtp_angle_buffer_lbl, self.rtp_angle_buffer_tb], 'h')
        self.rtp_angle_gb = GroupBox('Hide angles near runtime limits', rtp_angle_layout, True, False, 'rtp_angle_gb')
        self.rtp_angle_gb.setToolTip('Hide soundings that may have been limited by user-defined RX angle '
                                     'constraints during collection.\n\n'
                                     'Note that soundings limited by the echosounder mode are preserved '
                                     '(e.g., soundings at 52 deg in Very Deep mode are shown) as long as they do not '
                                     'fall within the angle buffer of the swath angle limit set during acquisition.'
                                     '\n\nNote also RX beam angles (w.r.t. RX array) differ slightly from achieved '
                                     'swath angles (calculated from depth and acrosstrack distance) due to'
                                     'installation, attitude, and refraction.')
        self.rtp_angle_buffer_tb.setToolTip('RX angle buffer may be set between -10 and +10 deg to accommodate RX beam '
                                            'angle variability near the user-defined runtime limits, e.g., due to beam-'
                                            'steering for vessel attitude and refraction correction.\n\n'
                                            'A zero buffer value will mask soundings only if the associated RX beam '
                                            'angles (or nominal swath angles, if RX beam angles are not available) '
                                            'exceeds the user-defined runtime parameter; there is no accomodation of '
                                            'variability around this threshold.\n\n'
                                            'Decrease the buffer (down to -10 deg) for more aggressive masking '
                                            'of soundings approaching the runtime limits (e.g., narrower swath) and '
                                            'increase the buffer (positive up to +10 deg) for a wider allowance of '
                                            'soundings near the runtime limits.\n\n'
                                            'Fine tuning may help to visualize (and remove) outer soundings that were '
                                            'clearly limited by runtime parameters during acquisition.')

        # add custom threshold/buffer for comparing RX beam angles to runtime parameters
        rtp_cov_buffer_lbl = Label('Coverage buffer (-inf-0 m):', alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.rtp_cov_buffer_tb = LineEdit('-100', 40, 20, 'rtp_cov_buffer_tb', '')
        self.rtp_cov_buffer_tb.setValidator(QDoubleValidator(-1*np.inf, 0, 2))
        rtp_cov_layout = BoxLayout([rtp_cov_buffer_lbl, self.rtp_cov_buffer_tb], 'h')
        self.rtp_cov_gb = GroupBox('Hide coverage near runtime limits', rtp_cov_layout, True, False, 'rtp_cov_gb')
        self.rtp_cov_gb.setToolTip('Hide soundings that may have been limited by user-defined acrosstrack '
                                   'coverage constraints during data collection.\n\n'
                                   'Buffer must be negative.  Decrease the buffer (down to -inf m) for more aggressive'
                                   'masking of soundings approaching the runtime coverage.\n\n'
                                   'Soundings outside the runtime coverage limit (i.e., within a buffer > 0 m) should '
                                   'not available, as they are rejected during acquisition.\n\n'
                                   'Fine tuning may help to visualize (and remove) outer soundings that were '
                                   'clearly limited by runtime parameters during acquisition.')

        # add plotted point max count and decimation factor control in checkable groupbox
        max_count_lbl = Label('Max. plotted points (0-inf):', width=140, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.max_count_tb = LineEdit(str(self.n_points_max_default), 50, 20, 'max_count_tb',
                                     'Set the maximum number of plotted points for each data set')
        self.max_count_tb.setValidator(QDoubleValidator(0, np.inf, 2))
        max_count_layout = BoxLayout([max_count_lbl, self.max_count_tb], 'h')
        dec_fac_lbl = Label('Decimation factor (1-inf):', width=140, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.dec_fac_tb = LineEdit(str(self.dec_fac_default), 50, 20, 'dec_fac_tb', 'Set the custom decimation factor')
        self.dec_fac_tb.setValidator(QDoubleValidator(1, np.inf, 2))
        dec_fac_layout = BoxLayout([dec_fac_lbl, self.dec_fac_tb], 'h')
        pt_count_layout = BoxLayout([max_count_layout, dec_fac_layout], 'v')
        self.pt_count_gb = GroupBox('Limit plotted point count (plot faster)', pt_count_layout, True, True, 'pt_ct_gb')
        self.pt_count_gb.setToolTip('To maintain reasonable plot and refresh speeds, the display will be limited '
                                   'by default to a total of ' + str(self.n_points_max_default) + ' soundings.  '
                                   'The limit is applied to new and archive datasets separately.  If needed, the user '
                                   'may specify a custom maximum point count.\n\n'
                                   'Reduction of each dataset is accomplished by simple decimation as a final step '
                                   'after all user-defined filtering (depth, angle, backscatter, etc.).  Non-integer '
                                   'decimation factors are handled using nearest-neighbor interpolation; soundings '
                                   'are not altered, just downsampled to display the maximum count allowed by the '
                                   'user parameters.'
                                   '\n\nAlternatively, the user may also specify a custom decimation factor.  '
                                   'Each dataset will be downsampled according to the more aggressive of the two '
                                   'inputs (max. count or dec. fac.) to achieve the greatest reduction in total '
                                   'displayed sounding count.  Unchecking these options will revert to the default.  '
                                   'In any case, large sounding counts may significantly slow the plotting process.')

        # add swath PKL decimation options for memory management
        swath_pkl_max_lbl = Label('Max points per file (0-inf):', width=140, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.swath_pkl_max_tb = LineEdit('1000000', 50, 20, 'swath_pkl_max_tb',
                                         'Set the maximum number of points to load from each Swath PKL file\n\n'
                                         'This helps reduce memory usage when loading large pickle files. '
                                         'Points are decimated evenly across the dataset to maintain coverage representation.')
        self.swath_pkl_max_tb.setValidator(QDoubleValidator(0, np.inf, 2))
        swath_pkl_dec_lbl = Label('Decimation factor (1-inf):', width=140, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.swath_pkl_dec_tb = LineEdit('1', 50, 20, 'swath_pkl_dec_tb',
                                         'Set the decimation factor for Swath PKL files\n\n'
                                         'A factor of 1 means no decimation. Higher values reduce memory usage '
                                         'by loading every Nth point (e.g., 2 = every 2nd point, 5 = every 5th point).')
        self.swath_pkl_dec_tb.setValidator(QDoubleValidator(1, np.inf, 2))
        swath_pkl_layout = BoxLayout([swath_pkl_max_lbl, self.swath_pkl_max_tb], 'h')
        swath_pkl_dec_layout = BoxLayout([swath_pkl_dec_lbl, self.swath_pkl_dec_tb], 'h')
        swath_pkl_options_layout = BoxLayout([swath_pkl_layout, swath_pkl_dec_layout], 'v')
        self.swath_pkl_dec_gb = GroupBox('Swath PKL Memory Management', swath_pkl_options_layout, True, False, 'swath_pkl_dec_gb')
        self.swath_pkl_dec_gb.setToolTip('Control memory usage when loading large Swath PKL files.\n\n'
                                         'These options apply decimation at load time to reduce memory footprint. '
                                         'The more restrictive of max points or decimation factor will be applied.\n\n'
                                         'This is particularly useful for very large datasets that would otherwise '
                                         'consume excessive memory.')

        # add swath angle line controls in chackable groupbox
        angle_lines_lbl_max = Label('Max:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.angle_lines_tb_max = LineEdit('75', 40, 20, 'angle_lines_tb_max', 'Set the angle line maximum (0-90 deg)')
        self.angle_lines_tb_max.setValidator(QDoubleValidator(0, 90, 2))
        angle_lines_lbl_int = Label('Interval:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.angle_lines_tb_int = LineEdit('15', 40, 20, 'angle_lines_tb_int', 'Set the angle line interval (5-30 deg)')
        self.angle_lines_tb_int.setValidator(QDoubleValidator(5, 30, 2))
        angle_lines_layout = BoxLayout([angle_lines_lbl_max, self.angle_lines_tb_max,
                                        angle_lines_lbl_int, self.angle_lines_tb_int], 'h')
        self.angle_lines_gb = GroupBox('Show swath angle lines', angle_lines_layout, True, False, 'angle_lines_gb')
        self.angle_lines_gb.setToolTip('Plot swath angle lines.\n\n'
                                       'Specify a custom maximum (0-90 deg) and interval (5-30 deg).\n\n'
                                       'These lines represent the achieved swath angles (calculated simply from depth '
                                       'and acrosstrack distance) and may differ from RX beam angles.')

        # add water depth multiple (N*WD) line controls in checkable groupbox
        n_wd_lines_lbl_max = Label('Max:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.n_wd_lines_tb_max = LineEdit('6', 40, 20, 'n_wd_lines_tb_max', 'Set the N*WD lines maximum (0-10 WD)')
        self.n_wd_lines_tb_max.setValidator(QDoubleValidator(0, 20, 2))
        n_wd_lines_lbl_int = Label('Interval:', width=50, alignment=(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.n_wd_lines_tb_int = LineEdit('1', 40, 20, 'n_wd_lines_tb_int', 'Set the N*WD lines interval (0.5-5 WD)')
        self.n_wd_lines_tb_int.setValidator(QDoubleValidator(0.5, 5, 2))
        n_wd_lines_layout = BoxLayout([n_wd_lines_lbl_max, self.n_wd_lines_tb_max,
                                       n_wd_lines_lbl_int, self.n_wd_lines_tb_int], 'h')
        self.n_wd_lines_gb = GroupBox('Show water depth multiple lines', n_wd_lines_layout, True, False, 'wd_lines_gb')
        self.n_wd_lines_gb.setToolTip('Plot water depth multiple (N*WD) lines.\n\n'
                                      'Specify a custom maximum (0-10 WD) and interval (0.5-5 WD).')

        # add check boxes to show archive data, grid lines, WD-multiple lines
        self.show_ref_fil_chk = CheckBox('Show reference/filter text', False, 'show_ref_fil_chk',
                                         'Show text box with sounding reference and filter information')
        self.show_spec_legend_chk = CheckBox('Show spec. curve legend', False, 'show_spec_legend_chk',
                                             'Show legend with unique colors for each specification curve')
        self.grid_lines_toggle_chk = CheckBox('Show grid lines', True, 'show_grid_chk', 'Show grid lines')
        self.colorbar_chk = CheckBox('Show colorbar/legend', True, 'show_colorbar_chk',
                                     'Enable colorbar or legend to follow the selected color mode.\n\n'
                                     'By default, the colorbar/legend follows the color mode of the last '
                                     'dataset added to the plot.  Typically, new data are plotted last (on '
                                     'top of any archive) and the new data color mode sets the colorbar.'
                                     '\n\nThe colorbar can be set to follow the archive data, if loaded, by '
                                     'checking the option to reverse the plot order.')

        self.clim_filter_chk = CheckBox('Set color scale from data filters', False, 'clim_from_filter_chk',
                                        'Scale the colorbar to limits used for hiding data by depth or '
                                        'backscatter.\n\nIf the same color mode is used for new and archive '
                                        'data, then the color scale applies to both datasets and the min/max '
                                        'are taken from the limits that are actively applied to the data.\n\n'
                                        'If different color modes are used, the color scale follows the '
                                        'dataset plotted last (on top) and the min/max are taken from the '
                                        'limits entered by the user for that dataset.\n\n'
                                        'Note the order of plotting can be reversed by the user, e.g., to '
                                        'plot archive data on top.')

        self.spec_chk = CheckBox('Show specification lines', False, 'show_spec_chk',
                                 'IN DEVELOPMENT: Load a text file with theoretical swath coverage performance')

        self.standard_fig_size_chk = CheckBox('Save standard figure size', True, 'standard_fig_size_chk',
                                              'Save figures in a standard size '
                                              '(H: ' + str(self.std_fig_height_inches) + '", '
                                              'W: ' + str(self.std_fig_width_inches) + '", 600 PPI).  Uncheck to '
                                              'allow the saved figure size to scale with the current plotter window.')

        self.show_hist_chk = CheckBox('Show histogram of soundings', False, 'show_hist_chk',
                                      'Show the distribution of soundings on the swath coverage plot.')
        self.match_data_cmodes_chk = CheckBox('Apply color modes to data plots', True, 'match_data_cmodes_chk',
                                              'Apply the chosen color modes for new / archive data to the data rate '
                                              'and ping interval plots.  Uncheck to use solid colors for data plots; '
                                              'the most recent solid colors will be used for new / archive data plots')

        self.show_coverage_trend_chk = CheckBox('Show coverage trend points', False, 'show_cov_trend_chk',
                                                'Show coverage trend points that will be used for export (e.g., to Gap '
                                                'Filler text file), if available')




        toggle_chk_layout = BoxLayout([self.show_ref_fil_chk, self.show_spec_legend_chk, self.grid_lines_toggle_chk, self.colorbar_chk,
                                       self.spec_chk, self.standard_fig_size_chk, self.show_hist_chk,
                                       self.match_data_cmodes_chk, self.show_coverage_trend_chk], 'v')

        toggle_chk_gb = GroupBox('Other options', toggle_chk_layout, False, False, 'other_options_gb')

        # Plotting and analysis group
        plot_btn_gb = GroupBox('Plot Data',
                               BoxLayout([self.save_all_plots_btn], 'v'),
                               False, False, 'plot_btn_gb')

        # Export functionality group (moved from left panel)
        export_gf_lbl = Label('Source:')
        export_gf_source = BoxLayout([export_gf_lbl, self.export_gf_cbox], 'h')
        export_horizontal_layout = BoxLayout([self.export_gf_btn, export_gf_source], 'h')
        export_btn_gb = GroupBox('Export Trend', export_horizontal_layout,
                                 False, False, 'export_btn_gb')

        # add runtime parameter search options
        param_cond_lbl = Label('Show when', 60, 20, 'param_cond_lbl', (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        self.param_cond_cbox = ComboBox(['ANY parameter matches', 'ALL parameters match'], 140, 20, 'param_cond_cbox',
                                        'Search for parameter changes that match ANY or ALL of the selections.\n\n'
                                        '"ANY parameter matches" will return every time a parameter change satisfies'
                                        'any of the checked search options.\n\n'
                                        '"ALL parameters match" will return only times where every checked search '
                                        'option is satisfied')

        param_cond_layout = BoxLayout([param_cond_lbl, self.param_cond_cbox], 'h', False, (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

        self.p1_chk = CheckBox('Depth Mode:', False, 'ping_mode', 'Search by Depth Mode', 100, 20)
        self.p1_cbox = ComboBox(['All', 'Very Shallow', 'Shallow', 'Medium', 'Deep', 'Deeper', 'Very Deep',
                                     'Extra Deep', 'Extreme Deep'], 100, 20, 'param1_cbox',
                                    'Depth Modes (not all modes apply for all models)')

        self.p2_chk = CheckBox('Swath Mode:', False, 'swath_mode', 'Search by Swath Mode', 100, 20)
        self.p2_cbox = ComboBox(['All', 'Single Swath', 'Dual Swath'], 100, 20, 'param2_cbox',
                                    'Swath Modes (Dual Swath includes "Dynamic" and "Fixed" spacing)')

        self.p3_chk = CheckBox('Pulse Form:', False, 'pulse_form', 'Search by Pulse Form', 100, 20)
        self.p3_cbox = ComboBox(['All', 'CW', 'FM', 'Mixed'], 100, 20, 'param3_cbox', 'Pulse Form')

        self.p4_chk = CheckBox('Swath Angle (deg):', False, 'swath_angle', 'Search by Swath Angle Limits', 140, 20)
        self.p4_cbox = ComboBox(['All', '<=', '>=', '=='], 40, 20, 'param4_cbox',
                                    'Select swath angle limit search criterion')
        self.p4_tb = LineEdit('75', 38, 20, 'swath_angle_tb', 'Search by swath angle limit (0-75 deg, port/stbd)')
        self.p4_tb.setValidator(QDoubleValidator(0, 75.0, 1))  # assume 0-75 deg range for either side
        param4_tb_layout = BoxLayout([self.p4_cbox, self.p4_tb], 'h', False, (Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

        self.p5_chk = CheckBox('Swath Cover. (m):', False, 'swath_cov', 'Search by Swath Coverage Limits', 140, 20)
        self.p5_cbox = ComboBox(['All', '<=', '>=', '=='], 40, 20, 'param5_cbox',
                                    'Select swath coverage limit search criterion')
        self.p5_tb = LineEdit('20000', 38, 20, 'swath_cov_tb', 'Search by swath coverage limit (0-30000 m, port/stbd)')
        self.p5_tb.setValidator(QDoubleValidator(0, 30000.0, 1))  # assume 30 km max (EM124)
        param5_tb_layout = BoxLayout([self.p5_cbox, self.p5_tb], 'h', False, (Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

        self.p6_chk = CheckBox('Frequency:', False, 'frequency', 'Search by Frequency', 100, 20)
        self.p6_cbox = ComboBox(['All', '12 kHz', '30 kHz', '40-100 kHz', '70-100 kHz', '200 kHz', '300 kHz', '400 kHz'],
                                100, 20, 'param6_cbox', 'Frequency')

        self.p7_chk = CheckBox('Waterline', True, 'wl_z_m', 'Search by Waterline', 100, 20)
        self.p7_cbox = ComboBox(['All'], 100, 20, 'param7_cbox', 'Waterline (m, positive down from origin)')

        # update Array Offsets to include LINEAR and ANGULAR offsets
        self.p8_chk = CheckBox('Array Offsets', True, 'array_xyz_m', 'Search by TX/RX Array Offsets (m)', 100, 20)
        self.p8_cbox = ComboBox(['All'], 100, 20, 'param8_cbox', 'TX/RX Array Offsets (m)')

        # update Active Position System offsets to include Attitude LINEAR and ANGULAR offsets (perhaps as Att. Offsets)
        self.p9_chk = CheckBox('Pos. Offsets', True, 'pos_xyz_m', 'Search by Active Pos. Sys. offsets (m)', 100, 20)
        self.p9_cbox = ComboBox(['All'], 100, 20, 'param9_cbox', 'Active Position System Offsets (m)')

        install_chk_layout1 = BoxLayout([self.p7_chk, self.p8_chk], 'h', False)
        install_chk_layout2 = BoxLayout([self.p9_chk], 'h', False)
        install_chk_layout = BoxLayout([install_chk_layout1, install_chk_layout2], 'v', False)
        install_search_gb = GroupBox('Installation Parameters', install_chk_layout, False, False, 'install_search_gb')

        # making separate vertical layouts of checkbox widgets and combobox widgets to set alignments separately
        self.param_chk_layout = BoxLayout([self.p1_chk, self.p2_chk, self.p3_chk, self.p4_chk, self.p5_chk, self.p6_chk], 'v', False)
        param_value_layout = BoxLayout([self.p1_cbox, self.p2_cbox, self.p3_cbox, param4_tb_layout, param5_tb_layout, self.p6_cbox],
                                       'v', False, (Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        param_search_hlayout = BoxLayout([self.param_chk_layout, param_value_layout], 'h')

        param_search_vlayout = BoxLayout([param_cond_layout, param_search_hlayout, install_search_gb], 'v', False)

        self.param_search_gb = GroupBox('Search Acquisition Parameters', param_search_vlayout,
                                        True, False, 'param_search_gb')


        # add search / update button
        self.param_search_btn = PushButton('Update Search', 100, 20, 'param_search_btn',
                                           'Search acquisition parameters for settings specified above.\n\n'
                                           'Results reflect the first ping time(s) when settings match the selected '
                                           'search options (i.e., the first ping and after any changes that match).\n\n'
                                           'ALL changes will be shown by default if no settings are specified.\n\n'
                                           'If individual settings are selected, the results can be further filtered by'
                                           'matching ANY or ALL selections:\n\n'
                                           '  a) ANY selected parameter matches (e.g., any time Depth Mode is changed '
                                           '  to Deep *and* any time Swath Mode is changed to Dual Swath), or\n\n'
                                           '  b) ALL selected parameters match (e.g., only times when a change has'
                                           '  been made so the Depth Mode is Deep *and* Swath Mode is Dual Swath\n\n'
                                           'Results will be printed to the acquisition parameter log. ')

        self.save_param_log_btn = PushButton('Save Search Log', 100, 20, 'param_log_save_btn',
                                             'Save the current Acquisition Parameter Log to a text file')

         # set up tabs
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("background-color: none")

        # set up tab 1: plot options
        self.tab1 = QtWidgets.QWidget()
        self.tab1_layout = BoxLayout([self.custom_info_gb, self.depth_ref_gb, cmode_layout, pt_param_gb, self.plot_lim_gb,
                                      self.angle_lines_gb, self.n_wd_lines_gb, toggle_chk_gb, plot_btn_gb, export_btn_gb], 'v')
        self.tab1_layout.addStretch()
        self.tab1.setLayout(self.tab1_layout)

        # set up tab 2: filtering options
        self.tab2 = QtWidgets.QWidget()
        self.tab2_layout = BoxLayout([self.angle_gb, self.depth_gb, self.bs_gb, self.ping_int_gb, self.rtp_angle_gb,
                                      self.rtp_cov_gb, self.pt_count_gb, self.swath_pkl_dec_gb], 'v')
        self.tab2_layout.addStretch()
        self.tab2.setLayout(self.tab2_layout)

        # set up tab 3: parameter search options
        self.tab3 = QtWidgets.QWidget()
        self.tab3_layout = BoxLayout([self.param_search_gb, self.param_search_btn, self.save_param_log_btn], 'v')
        self.tab3_layout.addStretch()
        self.tab3.setLayout(self.tab3_layout)

        # add tabs to tab layout
        self.tabs.addTab(self.tab1, 'Plot')
        self.tabs.addTab(self.tab2, 'Filter')
        self.tabs.addTab(self.tab3, 'Search')

        self.tabw = 240  # set fixed tab width
        self.tabs.setFixedWidth(self.tabw)

        # Add single CCOM_MAC logo to the right layout at the bottom
        ccom_mac_logo_path = os.path.join(self.media_path, 'CCOM_MAC.png')
        logo_row = QtWidgets.QHBoxLayout()
        logo_row.setContentsMargins(0, 0, 0, 0)  # Remove any default margins
        logo_row.addStretch()  # Add stretch to push logo to the right
        # Add CCOM_MAC logo
        if os.path.exists(ccom_mac_logo_path):
            logo_label = QtWidgets.QLabel()
            logo_pixmap = QtGui.QPixmap(ccom_mac_logo_path)
            logo_pixmap = logo_pixmap.scaled(96, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
            logo_row.addWidget(logo_label)
        
        # Create a container for the tabs and logo
        right_content_layout = QtWidgets.QVBoxLayout()
        right_content_layout.addWidget(self.tabs)
        right_content_layout.addLayout(logo_row)
        
        self.right_layout = BoxLayout([right_content_layout], 'v')
        self.right_layout.addStretch()


    def set_main_layout(self):
        # set the main layout with file controls on left and swath figure on right
        # self.mainWidget.setLayout(BoxLayout([self.left_layout, self.swath_layout, self.right_layout], 'h'))
        
        self.mainWidget.setLayout(BoxLayout([self.left_layout, self.center_layout, self.right_layout], 'h'))


    def add_pkl_files_from_directory(self):
        """Add PKL files from a selected directory"""
        try:
            # Get the last used directory from session config
            config = load_session_config()
            last_dir = config.get("last_crossline_dir", os.getcwd())
            
            # Open directory dialog
            selected_dir = QtWidgets.QFileDialog.getExistingDirectory(self, 'Add PKL Directory', last_dir)
            if selected_dir:
                # Update session config with the selected directory
                update_last_directory("last_crossline_dir", selected_dir)
                
                # Get the include subfolders setting
                include_subdir = self.include_pkl_subdir_chk.isChecked()
                
                # Find all PKL files in the directory
                pkl_files = []
                if include_subdir:
                    # Walk through all subdirectories
                    for dirpath, dirnames, filenames in os.walk(selected_dir):
                        for filename in filenames:
                            if filename.lower().endswith('.pkl'):
                                pkl_files.append(os.path.join(dirpath, filename))
                else:
                    # Only look in the selected directory
                    for filename in os.listdir(selected_dir):
                        if filename.lower().endswith('.pkl'):
                            pkl_files.append(os.path.join(selected_dir, filename))
                
                if pkl_files:
                    # Add the PKL files to the swath PKL file list
                    added_count = 0
                    newly_added_files = []
                    for pkl_file in pkl_files:
                        # Check if file is already in the list
                        already_exists = False
                        for i in range(self.swath_pkl_file_list.count()):
                            if self.swath_pkl_file_list.item(i).text() == pkl_file:
                                already_exists = True
                                break
                        
                        if not already_exists:
                            self.swath_pkl_file_list.addItem(pkl_file)
                            # Store the original path for path display toggle
                            item_index = self.swath_pkl_file_list.count() - 1
                            self.original_swath_pkl_paths[item_index] = pkl_file
                            newly_added_files.append(pkl_file)
                            added_count += 1
                    
                    self.update_log(f"Added {added_count} PKL files from directory")
                    self.update_file_buttons()
                    
                    # Automatically load the PKL files after adding them
                    if added_count > 0:
                        self.update_log("Auto-loading PKL files from directory...")
                        self.load_new_pkl_files(newly_added_files)
                else:
                    self.update_log("No PKL files found in the selected directory")
                    
        except Exception as e:
            self.update_log(f"Error adding PKL files from directory: {str(e)}")

    def load_new_pkl_files(self, pkl_files):
        """Load only the newly added PKL files"""
        try:
            if not pkl_files:
                self.update_log("No PKL files to load")
                return
            
            # Process only the newly added files
            self._process_pkl_files_directly(pkl_files)
                
        except Exception as e:
            self.update_log(f"*** ERROR: Failed to load new PKL files ***")
            self.update_log(f"Exception: {str(e)}")
            if hasattr(self, 'print_updates') and self.print_updates:
                import traceback
                self.update_log(f"Traceback: {traceback.format_exc()}")

    def load_swath_pkl_from_list(self):
        """Load PKL files that are already in the swath_pkl_file_list"""
        # Debug logging to see if this function is being called
        if hasattr(self, 'update_log'):
            self.update_log("DEBUG: load_swath_pkl_from_list called", 'blue')
            import traceback
            self.update_log(f"DEBUG: load_swath_pkl_from_list call stack: {traceback.format_stack()[-3:-1]}", 'blue')
        
        try:
            # Get all files from the list
            pkl_files = []
            for i in range(self.swath_pkl_file_list.count()):
                item = self.swath_pkl_file_list.item(i)
                if item:
                    pkl_files.append(item.text())
            
            if not pkl_files:
                self.update_log("No PKL files in the list to load")
                return
            
            # Use the existing load_swath_pkl function but bypass the file dialog
            # We'll temporarily set the filenames and call the function
            original_filenames = getattr(self, 'filenames', [])
            self.filenames = pkl_files
            
            # Call the existing function - it will process the files in self.filenames
            try:
                from .libs.swath_coverage_lib import load_swath_pkl
            except ImportError:
                from libs.swath_coverage_lib import load_swath_pkl
            
            # We need to modify the function to skip the dialog
            # Let's call the core processing logic directly
            self._process_pkl_files_directly(pkl_files)
            
            # Restore original filenames
            self.filenames = original_filenames
                
        except Exception as e:
            self.update_log(f"*** ERROR: Failed to load swath pickle files ***")
            self.update_log(f"Exception: {str(e)}")
            if hasattr(self, 'print_updates') and self.print_updates:
                import traceback
                self.update_log(f"Traceback: {traceback.format_exc()}")
    
    def _process_pkl_files_directly(self, pkl_files):
        """Process PKL files using the same logic as load_swath_pkl but without the dialog"""
        # Debug logging to see when this method is called
        if hasattr(self, 'update_log'):
            self.update_log(f"DEBUG: _process_pkl_files_directly called with {len(pkl_files)} files", 'blue')
            import traceback
            self.update_log(f"DEBUG: Call stack: {traceback.format_stack()[-3:-1]}", 'blue')
            self.update_log(f"DEBUG: About to start processing PKL files...", 'blue')
        
        try:
            # Start operation logging
            if hasattr(self, 'start_operation_log'):
                self.start_operation_log("Loading Swath Pickle Files")
            else:
                self.update_log("=== STARTING: Loading Swath Pickle Files ===")
            
            # Initialize required variables
            if not hasattr(self, 'data_new'):
                self.data_new = {}
            else:
                # Ensure data_new is always a dictionary
                if not isinstance(self.data_new, dict):
                    self.data_new = {}
            if not hasattr(self, 'filenames'):
                self.filenames = []
            if not hasattr(self, 'det'):
                self.det = {}
            
            # Invalidate decimation cache when loading new data
            # Only invalidate if we're actually loading new files, not just refreshing
            if pkl_files:  # Only invalidate if we have files to process
                self._invalidate_decimation_cache()
            
            # Process each PKL file using the same logic as load_swath_pkl
            for pickle_file in pkl_files:
                try:
                    from .libs.swath_coverage_lib import load_pickle_file
                except ImportError:
                    from libs.swath_coverage_lib import load_pickle_file
                
                data, status = load_pickle_file(self, pickle_file)
                
                if status and data:
                    # Apply decimation if enabled
                    if hasattr(self, 'swath_pkl_dec_gb') and self.swath_pkl_dec_gb.isChecked():
                        try:
                            from .libs.swath_coverage_lib import apply_swath_pkl_decimation
                        except ImportError:
                            from libs.swath_coverage_lib import apply_swath_pkl_decimation
                        data = apply_swath_pkl_decimation(self, data)
                    
                    # Add to data_new and filenames
                    filename = os.path.basename(pickle_file)
                    self.data_new[filename] = data
                    self.filenames.append(pickle_file)
                    
                    self.update_log(f"✓ Loaded swath pickle: {filename} ({status})")
            
            # Process the loaded data using the same logic as load_swath_pkl
            if self.data_new:
                try:
                    from .libs.swath_coverage_lib import interpretMode, sortDetectionsCoverage, update_system_info, refresh_plot
                except ImportError:
                    from libs.swath_coverage_lib import interpretMode, sortDetectionsCoverage, update_system_info, refresh_plot
                
                # Convert data_new to list format expected by interpretMode
                data_list = []
                for key, data in self.data_new.items():
                    # Add fname field to data if it doesn't exist
                    if 'fname' not in data:
                        data['fname'] = key
                    data_list.append(data)
                
                # Interpret modes
                interpreted_data = interpretMode(self, data_list, print_updates=self.print_updates)
                
                # Convert interpreted data back to dictionary format
                if isinstance(interpreted_data, list):
                    # Convert list back to dictionary using filenames as keys
                    self.data_new = {}
                    for i, data in enumerate(interpreted_data):
                        if 'fname' in data:
                            key = data['fname']
                        else:
                            key = f"file_{i}"
                        self.data_new[key] = data
                else:
                    self.data_new = interpreted_data
                
                # Convert data_new to list format expected by sortDetectionsCoverage
                data_list = []
                for key, data in self.data_new.items():
                    data_list.append(data)
                
                # Sort detections
                det_new = sortDetectionsCoverage(self, data_list, print_updates=self.print_updates, params_only=False)
                
                # Merge with existing detection dictionary
                if len(self.det) == 0:
                    self.det = det_new
                    self.update_log(f"Created new detection dictionary with {len(det_new)} keys")
                else:
                    for key, value in det_new.items():
                        if key in self.det:
                            self.det[key].extend(value)
                        else:
                            self.det[key] = value
                    self.update_log("Appended new data to existing detection dictionary")
                
                # Update system information
                update_system_info(self, self.det, force_update=True)
                
                # Refresh plot
                refresh_plot(self, print_time=True, call_source='load_swath_pkl_from_list')
                
                # Mark decimation cache as valid after successful processing
                self.decimation_cache_valid = True
                
                self.update_log(f"✓ Loaded {len(pkl_files)} PKL files successfully")
            else:
                self.update_log("No data loaded from PKL files")
                
        except Exception as e:
            self.update_log(f"*** ERROR: Failed to load swath pickle files ***")
            self.update_log(f"Exception: {str(e)}")
            if hasattr(self, 'print_updates') and self.print_updates:
                import traceback
                self.update_log(f"Traceback: {traceback.format_exc()}")
        finally:
            # End operation logging
            if hasattr(self, 'end_operation_log'):
                self.end_operation_log("Loading Swath Pickle Files")
            else:
                self.update_log("=== COMPLETED: Loading Swath Pickle Files ===")

    def handle_save_all_plots(self):
        description = self.cruise_tb.text().strip()
        if not description:
            QtWidgets.QMessageBox.warning(self, "Missing Description", "Please enter a description before saving all plots.")
            return
        save_all_plots(self)


    def _check_decimation_settings_changed(self):
        """Check if decimation settings have changed since last cache"""
        current_settings = {}
        
        # Get current decimation settings
        if hasattr(self, 'swath_pkl_dec_gb') and self.swath_pkl_dec_gb.isChecked():
            current_settings['decimation_enabled'] = True
            if hasattr(self, 'swath_pkl_max_tb'):
                current_settings['max_points'] = self.swath_pkl_max_tb.text()
            if hasattr(self, 'swath_pkl_dec_tb'):
                current_settings['dec_factor'] = self.swath_pkl_dec_tb.text()
        else:
            current_settings['decimation_enabled'] = False
        
        # Check if settings have changed
        if current_settings != self.last_decimation_settings:
            self.last_decimation_settings = current_settings.copy()
            return True
        return False
    
    def _check_filter_settings_changed(self):
        """Check if filter settings have changed since last cache"""
        current_settings = {}
        
        # Get current filter settings - only data processing filters, not display options
        if hasattr(self, 'min_angle_tb'):
            current_settings['min_angle'] = self.min_angle_tb.text()
        if hasattr(self, 'max_angle_tb'):
            current_settings['max_angle'] = self.max_angle_tb.text()
        if hasattr(self, 'min_depth_tb'):
            current_settings['min_depth'] = self.min_depth_tb.text()
        if hasattr(self, 'max_depth_tb'):
            current_settings['max_depth'] = self.max_depth_tb.text()
        if hasattr(self, 'min_bs_tb'):
            current_settings['min_bs'] = self.min_bs_tb.text()
        if hasattr(self, 'max_bs_tb'):
            current_settings['max_bs'] = self.max_bs_tb.text()
        
        # Check if settings have changed
        if current_settings != self.last_filter_settings:
            self.last_filter_settings = current_settings.copy()
            return True
        return False
    
    def _invalidate_decimation_cache(self):
        """Invalidate the decimation cache when settings change"""
        self.decimation_cache = {}
        self.decimation_cache_valid = False
        if hasattr(self, 'update_log'):
            self.update_log("DEBUG: Decimation cache invalidated", 'blue')
    
    def _should_use_decimation_cache(self):
        """Determine if we can use cached decimated data"""
        # Cache is invalid if:
        # 1. No cache exists
        # 2. Decimation settings changed
        # 3. Data processing filter settings changed (not display options)
        # 4. New data was loaded
        
        if not self.decimation_cache_valid:
            return False
        
        # Only check decimation settings - these are the only ones that affect data processing
        if self._check_decimation_settings_changed():
            self._invalidate_decimation_cache()
            return False
        
        # Only check data processing filters, not display options
        # For now, let's be conservative and not check filter changes
        # This prevents cache invalidation on cosmetic changes
        # if self._check_filter_settings_changed():
        #     self._invalidate_decimation_cache()
        #     return False
        
        return True


class NewPopup(QtWidgets.QWidget): # new class for additional plots
    def __init__(self):
        QtWidgets.QWidget.__init__(self)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    main = MainWindow()
    main.show()

    sys.exit(app.exec())
