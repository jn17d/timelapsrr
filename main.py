#!/usr/bin/env python3
"""
Timelapse Maker GUI - A user-friendly interface for creating timelapse videos.
Handles corrupt files gracefully and supports FPS and resolution customization.
Features: Drag & Drop, Time Filtering, Hardware Acceleration
Built with CustomTkinter for modern cross-platform GUI.
"""

import customtkinter as ctk
from tkinter import filedialog, scrolledtext
import threading
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from datetime import datetime, time
import json
import platform

try:
    from PIL import Image, ExifTags, UnidentifiedImageError
except ImportError:
    print("Error: Pillow is required. Install with: pip install pillow")
    exit(1)

try:
    import ffmpeg
except ImportError:
    print("Error: ffmpeg-python is required. Install with: pip install ffmpeg-python")
    exit(1)

# Resolution presets
RESOLUTION_PRESETS = {
    'actual': None,
    '4k': (3840, 2160),
    '1440p': (2560, 1440),
    '1080p': (1920, 1080),
    '720p': (1280, 720),
    '480p': (854, 480),
}

# Hardware acceleration presets
HW_ACCEL_PRESETS = {
    'None': (None, None),
    'NVIDIA NVENC': ('h264_nvenc', 'cuda'),
    'Intel Quick Sync': ('h264_qsv', 'qsv'),
    'AMD VCE': ('h264_amf', 'd3d11va' if platform.system() == 'Windows' else 'vaapi'),
    'VideoToolbox (macOS)': ('h264_videotoolbox', None),
}


def detect_available_encoders() -> Dict[str, Tuple]:
    """
    Detect available hardware encoders using ffmpeg -encoders.
    Returns a dictionary of available hardware acceleration options.
    """
    try:
        result = subprocess.run(
            ['ffmpeg', '-encoders'],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout.lower()
        
        available = {'None': (None, None)}  # Always available
        
        # Detect NVIDIA NVENC
        if 'h264_nvenc' in output:
            available['NVIDIA NVENC'] = ('h264_nvenc', 'cuda')
        
        # Detect Intel Quick Sync Video
        if 'h264_qsv' in output:
            available['Intel Quick Sync'] = ('h264_qsv', 'qsv')
        
        # Detect AMD VCE
        if 'h264_amf' in output:
            hw_device = 'd3d11va' if platform.system() == 'Windows' else 'vaapi'
            available['AMD VCE'] = ('h264_amf', hw_device)
        
        # Detect macOS VideoToolbox
        if 'h264_videotoolbox' in output:
            available['VideoToolbox (macOS)'] = ('h264_videotoolbox', None)
        
        return available
    except FileNotFoundError:
        # FFmpeg not found
        print("Warning: FFmpeg not found. Hardware acceleration disabled.")
        return {'None': (None, None)}
    except subprocess.TimeoutExpired:
        print("Warning: FFmpeg -encoders command timed out.")
        return {'None': (None, None)}
    except Exception as e:
        print(f"Warning: Error detecting hardware encoders: {e}")
        return {'None': (None, None)}


class TimelapseGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.title("Timelapse Maker")
        self.geometry("1200x700")
        
        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Variables
        self.input_folder = ctk.StringVar()
        self.output_file = ctk.StringVar()
        self.fps = ctk.IntVar(value=30)
        self.resolution = ctk.StringVar(value='1080p')
        self.crf = ctk.IntVar(value=23)
        self.hardware_accel = ctk.StringVar(value='None')
        self.time_filter_enabled = ctk.BooleanVar(value=False)
        self.start_time = ctk.StringVar(value='06:00')
        self.end_time = ctk.StringVar(value='18:00')
        self.sort_method = ctk.StringVar(value='exif_modified')
        
        self.is_processing = False
        self.processing_thread = None
        
        # Detect available hardware encoders
        self.available_encoders = detect_available_encoders()
        
        # Settings file for persistence
        self.settings_file = Path.home() / '.timelapse_maker_settings.json'
        self.load_settings()
        
        # Validate that saved hardware accel is still available
        if self.hardware_accel.get() not in self.available_encoders:
            self.hardware_accel.set('None')  # Fall back to software encoding
        
        # Create UI
        self.create_ui()
        
        # Log hardware detection results
        available_hw = [name for name in self.available_encoders.keys() if name != 'None']
        if available_hw:
            self.log_status(f"✓ Hardware acceleration available: {', '.join(available_hw)}")
        else:
            self.log_status("ℹ️  No hardware acceleration detected. Using software encoding.")
        self.log_status("Timelapse Maker ready.\nSelect an input folder to begin.")
    
    def create_ui(self):
        """Create all UI widgets."""
        # Main two-column layout
        main_container = ctk.CTkFrame(self)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Left column - Controls
        left_frame = ctk.CTkFrame(main_container)
        left_frame.pack(side="left", fill="both", expand=False, padx=(0, 10))
        
        # Scrollable frame for controls
        self.main_frame = ctk.CTkScrollableFrame(left_frame, width=400)
        self.main_frame.pack(fill="both", expand=True)
        
        # Input folder section
        input_label = ctk.CTkLabel(self.main_frame, text="Input Folder", font=("Roboto Medium", 14))
        input_label.pack(anchor="w", pady=(10, 5))
        
        input_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        input_row.pack(fill="x", pady=5)
        
        self.input_entry = ctk.CTkEntry(input_row, textvariable=self.input_folder, placeholder_text="Select input folder...")
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(
            input_row,
            text="Browse",
            command=self.browse_input_folder,
            width=80
        ).pack(side="left")
        
        # Output file section
        output_label = ctk.CTkLabel(self.main_frame, text="Output File", font=("Roboto Medium", 14))
        output_label.pack(anchor="w", pady=(10, 5))
        
        output_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        output_row.pack(fill="x", pady=5)
        
        self.output_entry = ctk.CTkEntry(output_row, textvariable=self.output_file, placeholder_text="Select output file...")
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(
            output_row,
            text="Browse",
            command=self.browse_output_file,
            width=80
        ).pack(side="left")
        
        # FPS section
        fps_label = ctk.CTkLabel(self.main_frame, text="FPS", font=("Roboto Medium", 14))
        fps_label.pack(anchor="w", pady=(15, 5))
        
        fps_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        fps_row.pack(fill="x", pady=5)
        
        self.fps_slider = ctk.CTkSlider(
            fps_row,
            from_=1,
            to=120,
            variable=self.fps,
            command=self.update_fps_label
        )
        self.fps_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.fps_label_widget = ctk.CTkLabel(fps_row, text="30 FPS", width=60)
        self.fps_label_widget.pack(side="left")
        
        fps_hint = ctk.CTkLabel(fps_row, text="(Higher = faster)", font=("Roboto", 10), text_color="gray")
        fps_hint.pack(side="left", padx=(5, 0))
        
        # Resolution section
        resolution_label = ctk.CTkLabel(self.main_frame, text="Resolution", font=("Roboto Medium", 14))
        resolution_label.pack(anchor="w", pady=(15, 5))
        
        resolution_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        resolution_row.pack(fill="x", pady=5)
        
        self.resolution_combo = ctk.CTkComboBox(
            resolution_row,
            values=['actual', '4k', '1440p', '1080p', '720p', '480p'],
            variable=self.resolution,
            width=100,
            command=self.save_settings
        )
        self.resolution_combo.pack(side="left", padx=(0, 10))
        
        resolution_hint = ctk.CTkLabel(resolution_row, text="Resize output video (optional)", font=("Roboto", 10), text_color="gray")
        resolution_hint.pack(side="left")
        
        # Quality section
        quality_label = ctk.CTkLabel(self.main_frame, text="Quality (CRF)", font=("Roboto Medium", 14))
        quality_label.pack(anchor="w", pady=(15, 5))
        
        quality_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        quality_row.pack(fill="x", pady=5)
        
        self.crf_slider = ctk.CTkSlider(
            quality_row,
            from_=0,
            to=51,
            variable=self.crf,
            command=self.update_crf_label
        )
        self.crf_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.crf_label_widget = ctk.CTkLabel(quality_row, text="CRF: 23", width=70)
        self.crf_label_widget.pack(side="left")
        
        quality_hint = ctk.CTkLabel(quality_row, text="(Lower = better)", font=("Roboto", 10), text_color="gray")
        quality_hint.pack(side="left", padx=(5, 0))
        
        # Hardware acceleration section
        hw_label = ctk.CTkLabel(self.main_frame, text="Hardware Acceleration", font=("Roboto Medium", 14))
        hw_label.pack(anchor="w", pady=(15, 5))
        
        hw_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        hw_row.pack(fill="x", pady=5)
        
        self.hw_combo = ctk.CTkComboBox(
            hw_row,
            values=list(self.available_encoders.keys()),
            variable=self.hardware_accel,
            width=200,
            command=self.save_settings
        )
        self.hw_combo.pack(side="left", padx=(0, 10))
        
        hw_hint = ctk.CTkLabel(hw_row, text="(Auto-detected)", font=("Roboto", 10), text_color="gray")
        hw_hint.pack(side="left")
        
        # Sort method section
        sort_label = ctk.CTkLabel(self.main_frame, text="Sort Method", font=("Roboto Medium", 14))
        sort_label.pack(anchor="w", pady=(15, 5))
        
        sort_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        sort_row.pack(fill="x", pady=5)
        
        self.sort_combo = ctk.CTkComboBox(
            sort_row,
            values=[
                'EXIF → Modified → Filename',
                'EXIF → Created → Filename',
                'Modified Date Only',
                'Created Date Only',
                'Filename Only'
            ],
            variable=self.sort_method,
            width=250,
            command=self.save_settings
        )
        self.sort_combo.pack(side="left", padx=(0, 10))
        
        sort_hint = ctk.CTkLabel(sort_row, text="(How to order images)", font=("Roboto", 10), text_color="gray")
        sort_hint.pack(side="left")
        
        # Time filter section
        time_frame = ctk.CTkFrame(self.main_frame)
        time_frame.pack(fill="x", pady=(10, 10))
        
        time_title = ctk.CTkLabel(time_frame, text="Time Filter", font=("Roboto Medium", 16))
        time_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        self.time_filter_check = ctk.CTkCheckBox(
            time_frame,
            text="Filter by time of day",
            variable=self.time_filter_enabled,
            command=self.save_settings
        )
        self.time_filter_check.pack(anchor="w", padx=15, pady=(0, 5))
        
        time_row = ctk.CTkFrame(time_frame, fg_color="transparent")
        time_row.pack(fill="x", padx=15, pady=(0, 10))
        
        ctk.CTkLabel(time_row, text="From:").pack(side="left")
        self.start_time_entry = ctk.CTkEntry(
            time_row,
            textvariable=self.start_time,
            width=70
        )
        self.start_time_entry.pack(side="left", padx=5)
        
        ctk.CTkLabel(time_row, text="to:").pack(side="left")
        self.end_time_entry = ctk.CTkEntry(
            time_row,
            textvariable=self.end_time,
            width=70
        )
        self.end_time_entry.pack(side="left", padx=5)
        
        # Buttons
        button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=20)
        
        self.create_button = ctk.CTkButton(
            button_frame,
            text="▶ Create Timelapse",
            command=self.start_creation,
            fg_color="green",
            hover_color="darkgreen"
        )
        self.create_button.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.cancel_button = ctk.CTkButton(
            button_frame,
            text="✕ Cancel",
            command=self.cancel_creation,
            state="disabled"
        )
        self.cancel_button.pack(side="left", fill="x", expand=True)
        
        # Progress bar
        self.progress = ctk.CTkProgressBar(self.main_frame)
        self.progress.pack(fill="x", pady=5)
        self.progress.pack_forget()  # Initially hidden
        
        # Right column - Status log (always visible)
        right_frame = ctk.CTkFrame(main_container)
        right_frame.pack(side="left", fill="both", expand=True)
        
        status_label = ctk.CTkLabel(right_frame, text="Status Log", font=("Roboto Medium", 16))
        status_label.pack(anchor="w", pady=(0, 10))
        
        self.status_log = ctk.CTkTextbox(right_frame, height=600)
        self.status_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Configure text tags for colored output
        self.status_log.tag_config('error', foreground='#ff6b6b')
        self.status_log.tag_config('success', foreground='#51cf66')
        self.status_log.tag_config('warning', foreground='#ffd43b')
        self.status_log.tag_config('info', foreground='#4dabf7')
    
    def update_fps_label(self, value):
        """Update FPS label"""
        self.fps_label_widget.configure(text=f"{int(float(value))} FPS")
        self.save_settings()
    
    def update_crf_label(self, value):
        """Update CRF label"""
        self.crf_label_widget.configure(text=f"CRF: {int(float(value))}")
        self.save_settings()
    
    def browse_input_folder(self):
        """Open folder picker for input"""
        folder = filedialog.askdirectory(title="Select Input Folder")
        if folder:
            self.input_folder.set(folder)
            # Auto-generate output filename
            if not self.output_file.get():
                folder_path = Path(folder)
                output_file = folder_path.parent / f"{folder_path.name}_timelapse.mp4"
                self.output_file.set(str(output_file))
            self.log_status(f"Selected input folder: {folder}")
            self.save_settings()
    
    def browse_output_file(self):
        """Open file picker for output"""
        file = filedialog.asksaveasfilename(
            title="Save Timelapse",
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")],
            initialfile="timelapse.mp4"
        )
        if file:
            self.output_file.set(file)
            self.log_status(f"Selected output file: {file}")
            self.save_settings()
    
    def log_status(self, message, tag=None):
        """Log a message to status text area (thread-safe) with timestamp"""
        def _update():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.status_log.insert("end", f"[{timestamp}] {message}\n", tag)
            self.status_log.see("end")
            self.status_log.update()
        
        # Schedule update on main thread
        if threading.current_thread() == threading.main_thread():
            _update()
        else:
            self.after(0, _update)
    
    def get_exif_datetime(self, image_path: Path, exif_cache: dict = None) -> Optional[datetime]:
        """Extract DateTimeOriginal from EXIF data with optional caching."""
        # Check cache first if provided
        if exif_cache is not None and str(image_path) in exif_cache:
            return exif_cache[str(image_path)]
        
        try:
            with Image.open(image_path) as img:
                exif_data = img._getexif()
                if exif_data:
                    exif = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif_data.items()}
                    datetime_str = exif.get('DateTimeOriginal') or exif.get('DateTime')
                    if datetime_str:
                        dt = datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
                        # Store in cache if provided
                        if exif_cache is not None:
                            exif_cache[str(image_path)] = dt
                        return dt
        except Exception:
            pass
        return None
    
    def passes_time_filter(self, image_path: Path, start_time: time, end_time: time, exif_cache: dict) -> bool:
        """Check if image's time falls within time range."""
        # Try EXIF first, then fall back to file modification time
        exif_dt = self.get_exif_datetime(image_path, exif_cache)
        
        if exif_dt:
            image_time = exif_dt.time()
        else:
            # Fall back to file modification time
            try:
                file_dt = datetime.fromtimestamp(image_path.stat().st_mtime)
                image_time = file_dt.time()
            except:
                return True  # If we can't get any time, include the image
        
        # Handle time ranges that span midnight
        if start_time <= end_time:
            return start_time <= image_time <= end_time
        else:
            # Range spans midnight (e.g., 22:00 to 06:00)
            return image_time >= start_time or image_time <= end_time
    
    def validate_and_sort_images(self, input_folder: Path) -> tuple:
        """Validate and sort images with optional time filtering."""
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}
        
        # Consolidated file globbing - single directory scan instead of 12
        all_files = [
            f for f in input_folder.glob('*')
            if f.suffix.lower() in image_extensions
        ]
        
        valid_images = []
        invalid_images = []
        filtered_count = 0
        
        # EXIF cache to avoid re-reading same files
        exif_cache = {}
        
        # Time filter settings - initialize defaults first
        start_time_obj = time(0, 0)  # 00:00 (all times)
        end_time_obj = time(23, 59)   # 23:59 (all times)
        
        if self.time_filter_enabled.get():
            try:
                start_str = self.start_time.get()
                parts = start_str.split(':')
                start_time_obj = time(int(parts[0]), int(parts[1]))
                
                end_str = self.end_time.get()
                parts = end_str.split(':')
                end_time_obj = time(int(parts[0]), int(parts[1]))
                
                self.log_status(f"Time filter enabled: {start_time_obj.strftime('%H:%M')} to {end_time_obj.strftime('%H:%M')}")
            except Exception as e:
                self.log_status(f"Warning: Invalid time format, using default 06:00-18:00", 'warning')
                start_time_obj = time(6, 0)
                end_time_obj = time(18, 0)
        
        self.log_status(f"Found {len(all_files)} image files. Validating...", 'info')
        
        total_images = len(all_files)
        processed = 0
        last_progress = 0
        
        for image_path in sorted(all_files):
            # Fast pre-filter: Skip files that are too small
            file_size = image_path.stat().st_size
            if file_size == 0:
                invalid_images.append(image_path)
                processed += 1
                continue
            if file_size < 1024:
                invalid_images.append(image_path)
                processed += 1
                continue
            
            # Read EXIF data and cache it for sorting (always do this, not just for time filter)
            self.get_exif_datetime(image_path, exif_cache)
            
            # Time filter check
            if self.time_filter_enabled.get():
                if not self.passes_time_filter(image_path, start_time_obj, end_time_obj, exif_cache):
                    filtered_count += 1
                    processed += 1
                    continue
            
            # Validate image
            try:
                with Image.open(image_path) as img:
                    img.load()
                valid_images.append(image_path)
            except (UnidentifiedImageError, IOError, Exception):
                invalid_images.append(image_path)
                self.log_status(f"  ⚠ Skipping corrupt file: {image_path.name}", 'warning')
            
            processed += 1
            
            # Show progress every 10% or every 50 images
            progress = int((processed / total_images) * 100)
            if progress - last_progress >= 10 or processed % 50 == 0 or processed == total_images:
                self.log_status(f"  Progress: {processed}/{total_images} images ({progress}%)")
                last_progress = progress
        
        # Define sort key function based on selected method
        sort_method = self.sort_method.get()
        
        if sort_method == 'exif_modified':
            # EXIF → Modified → Filename
            def get_sort_key(path):
                exif_date = self.get_exif_datetime(path, exif_cache)
                if exif_date:
                    return (0, exif_date)
                else:
                    try:
                        modified_time = datetime.fromtimestamp(path.stat().st_mtime)
                        return (1, modified_time)
                    except:
                        return (2, path.name)
        
        elif sort_method == 'exif_created':
            # EXIF → Created → Filename
            def get_sort_key(path):
                exif_date = self.get_exif_datetime(path, exif_cache)
                if exif_date:
                    return (0, exif_date)
                else:
                    try:
                        created_time = datetime.fromtimestamp(path.stat().st_ctime)
                        return (1, created_time)
                    except:
                        return (2, path.name)
        
        elif sort_method == 'Modified Date Only':
            # Modified Date Only
            def get_sort_key(path):
                try:
                    modified_time = datetime.fromtimestamp(path.stat().st_mtime)
                    return modified_time
                except:
                    return path.name
        
        elif sort_method == 'Created Date Only':
            # Created Date Only
            def get_sort_key(path):
                try:
                    created_time = datetime.fromtimestamp(path.stat().st_ctime)
                    return created_time
                except:
                    return path.name
        
        else:  # 'Filename Only'
            # Filename Only
            def get_sort_key(path):
                return path.name
        
        valid_images.sort(key=get_sort_key)
        
        # Log which sort method was used
        sort_names = {
            'exif_modified': 'EXIF → Modified → Filename',
            'exif_created': 'EXIF → Created → Filename',
            'Modified Date Only': 'Modified Date Only',
            'Created Date Only': 'Created Date Only',
            'Filename Only': 'Filename Only'
        }
        self.log_status(f"📊 Sorting by: {sort_names.get(sort_method, sort_method)}", 'info')
        
        self.log_status(f"✓ {len(valid_images)} valid images")
        if filtered_count > 0:
            self.log_status(f"⏱ {filtered_count} images filtered by time")
        if invalid_images:
            self.log_status(f"✗ {len(invalid_images)} corrupt/invalid images skipped")
        
        return valid_images, invalid_images
    
    def create_timelapse(self):
        """Create timelapse video (runs in background thread)."""
        try:
            input_folder = Path(self.input_folder.get())
            output_file = Path(self.output_file.get())
            fps = self.fps.get()
            resolution = self.resolution.get()
            crf = self.crf.get()
            hardware_accel = self.hardware_accel.get()
            
            # Validate inputs
            if not input_folder.exists():
                self.log_status("Error: Input folder does not exist!", 'error')
                self.finish_creation(False)
                return
            
            if not input_folder.is_dir():
                self.log_status("Error: Input path is not a folder!", 'error')
                self.finish_creation(False)
                return
            
            # Validate and sort images
            valid_images, invalid_images = self.validate_and_sort_images(input_folder)
            
            if not valid_images:
                self.log_status("Error: No valid images found!", 'error')
                self.finish_creation(False)
                return
            
            self.log_status(f"\n{'='*50}", 'info')
            self.log_status(f"Starting timelapse creation...", 'info')
            self.log_status(f"{'='*50}", 'info')
            self.log_status(f"Total images to process: {len(valid_images)}", 'info')
            settings_msg = f"Settings: FPS={fps}, Resolution={resolution}, Quality={crf}"
            if hardware_accel != 'None':
                settings_msg += f", HW Accel={hardware_accel}"
            self.log_status(settings_msg, 'info')
            
            # Create output directory if needed
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Get resolution dimensions
            width, height = RESOLUTION_PRESETS[resolution]
            
            # Create temporary image list
            self.log_status(f"\nPreparing image list...", 'info')
            temp_list = input_folder / 'image_list.txt'
            with open(temp_list, 'w') as f:
                for img in valid_images:
                    f.write(f"file '{img.absolute()}'\n")
            self.log_status(f"✓ Image list created", 'success')
            
            self.log_status(f"\n{'='*50}", 'info')
            self.log_status(f"Starting FFmpeg encoding...", 'info')
            self.log_status(f"{'='*50}", 'info')
            self.log_status(f"Output: {output_file}", 'info')
            self.log_status(f"⏳ Encoding in progress (please wait)...\n", 'info')
            
            # Build FFmpeg command
            input_args = {'r': fps}
            
            # Build video filter chain
            vf_filters = []
            if width and height:
                vf_filters.append(f'scale={width}:{height}')
            
            # Determine codec based on hardware acceleration
            codec, hw_device = self.available_encoders.get(hardware_accel, (None, None))
            
            output_args = {
                'pix_fmt': 'yuv420p',
                'crf': crf
            }
            
            if codec:
                output_args['c:v'] = codec
            else:
                output_args['c:v'] = 'libx264'
            
            if vf_filters:
                output_args['vf'] = ','.join(vf_filters)
            
            process = (
                ffmpeg
                .input(str(temp_list), format='concat', safe=0, **input_args)
                .output(str(output_file), **output_args)
                .overwrite_output()
            )
            
            # Execute
            self.log_status(f"Running FFmpeg command...", 'info')
            self.log_status(f"  Input: {temp_list}", 'info')
            self.log_status(f"  Codec: {codec or 'libx264'}", 'info')
            if width and height:
                self.log_status(f"  Resolution: {width}x{height}", 'info')
            self.log_status(f"  FPS: {fps}", 'info')
            self.log_status(f"  CRF: {crf}", 'info')
            if hardware_accel != 'None':
                self.log_status(f"  Hardware acceleration: {hardware_accel}", 'info')
            self.log_status("", 'info')
            
            process.run()
            
            # Clean up temp file
            temp_list.unlink()
            
            # Success
            self.log_status(f"\n{'='*50}", 'success')
            self.log_status(f"✓ TIMELAPSE CREATED SUCCESSFULLY!", 'success')
            self.log_status(f"{'='*50}", 'success')
            self.log_status(f"📁 Output file: {output_file}", 'info')
            self.log_status(f"📊 File size: {output_file.stat().st_size / (1024*1024):.2f} MB", 'info')
            self.log_status(f"🖼️  Images used: {len(valid_images)}", 'info')
            self.log_status(f"⏱️  Estimated duration: {len(valid_images) / fps:.1f} seconds @ {fps} FPS", 'info')
            if hardware_accel != 'None':
                self.log_status(f"⚡ Hardware acceleration: {hardware_accel}", 'info')
            self.log_status(f"{'='*50}", 'success')
            
            self.finish_creation(True)
            
        except ffmpeg.Error as e:
            self.log_status(f"\n✗ FFmpeg error occurred:", 'error')
            self.log_status(f"  {e.stderr.decode('utf8') if e.stderr else str(e)}", 'error')
            self.finish_creation(False)
        except Exception as e:
            self.log_status(f"\n✗ Error: {e}", 'error')
            self.finish_creation(False)
    
    def start_creation(self):
        """Start timelapse creation in background thread."""
        if not self.input_folder.get():
            self.log_status("Please select an input folder.", 'error')
            return
        
        if not self.output_file.get():
            self.log_status("Please select an output file.", 'error')
            return
        
        if self.is_processing:
            return
        
        # Validate time format
        self.validate_time_format()
        
        # Save settings before processing
        self.save_settings()
        
        self.is_processing = True
        self.create_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.pack(fill="x", pady=5)
        self.progress.start()
        
        # Clear status
        self.status_log.delete("1.0", "end")
        
        # Start processing thread
        self.processing_thread = threading.Thread(target=self.create_timelapse, daemon=True)
        self.processing_thread.start()
    
    def cancel_creation(self):
        """Cancel timelapse creation."""
        if self.is_processing:
            self.is_processing = False
            self.log_status("\n✗ Operation cancelled by user.", 'warning')
            self.finish_creation(False)
    
    def finish_creation(self, success):
        """Finish timelapse creation (cleanup UI)."""
        self.is_processing = False
        self.progress.stop()
        self.progress.pack_forget()
        self.create_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        
        if success:
            self.log_status("\n✅ All done! Ready for next timelapse.", 'success')
        else:
            self.log_status("\n❌ Process failed. Check errors above.", 'error')
    
    def validate_time_format(self):
        """Validate and format time fields"""
        try:
            start_str = self.start_time.get()
            parts = start_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            
            if hour < 0:
                hour = 0
            elif hour > 23:
                hour = 23
            
            if minute < 0:
                minute = 0
            elif minute > 59:
                minute = 59
            
            self.start_time.set(f"{hour:02d}:{minute:02d}")
        except:
            self.start_time.set("06:00")
        
        try:
            end_str = self.end_time.get()
            parts = end_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            
            if hour < 0:
                hour = 0
            elif hour > 23:
                hour = 23
            
            if minute < 0:
                minute = 0
            elif minute > 59:
                minute = 59
            
            self.end_time.set(f"{hour:02d}:{minute:02d}")
        except:
            self.end_time.set("18:00")
        
        self.save_settings()
    
    def save_settings(self, value=None):
        """Save current settings to file."""
        try:
            settings = {
                'fps': self.fps.get(),
                'resolution': self.resolution.get(),
                'crf': self.crf.get(),
                'hardware_accel': self.hardware_accel.get(),
                'time_filter_enabled': self.time_filter_enabled.get(),
                'start_time': self.start_time.get(),
                'end_time': self.end_time.get(),
                'sort_method': self.sort_method.get(),
                'last_input_folder': self.input_folder.get(),
                'last_output_file': self.output_file.get(),
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            pass  # Silently fail if saving doesn't work
    
    def load_settings(self):
        """Load settings from file."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    self.fps.set(settings.get('fps', 30))
                    self.resolution.set(settings.get('resolution', '1080p'))
                    self.crf.set(settings.get('crf', 23))
                    self.hardware_accel.set(settings.get('hardware_accel', 'None'))
                    self.time_filter_enabled.set(settings.get('time_filter_enabled', False))
                    self.start_time.set(settings.get('start_time', '06:00'))
                    self.end_time.set(settings.get('end_time', '18:00'))
                    self.sort_method.set(settings.get('sort_method', 'exif_modified'))
                    self.input_folder.set(settings.get('last_input_folder', ''))
                    self.output_file.set(settings.get('last_output_file', ''))
        except Exception as e:
            pass  # Silently fail if loading doesn't work


def main():
    app = TimelapseGUI()
    app.mainloop()


if __name__ == '__main__':
    main()