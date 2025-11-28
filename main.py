from gevent import monkey
monkey.patch_all(thread=False)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import json
import os
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request
from PIL import Image, ImageGrab, ImageTk
import cv2
from gevent.pywsgi import WSGIServer

class ScreenShareConfig:
    """Configuration class for screen sharing settings"""
    def __init__(self):
        self.fps = 8
        self.x_res = 400
        self.y_res = 225
        self.compressed_colors = False
        self.frame_groups = 1
        self.frame_skip = 0
        self.frame_start = 0
        self.video_streaming = False
        self.video_path = ""
        self.speed_multiplier = 1
        self.port = 5000
        
    def to_dict(self):
        return {
            "fps": self.fps,
            "x_res": self.x_res,
            "y_res": self.y_res,
            "compressed_colors": self.compressed_colors,
            "frame_groups": self.frame_groups,
            "frame_skip": self.frame_skip,
            "frame_start": self.frame_start,
            "video_streaming": self.video_streaming,
            "video_path": self.video_path,
            "speed_multiplier": self.speed_multiplier,
            "port": self.port
        }
    
    def from_dict(self, data):
        self.fps = data.get("fps", 8)
        self.x_res = data.get("x_res", 400)
        self.y_res = data.get("y_res", 225)
        self.compressed_colors = data.get("compressed_colors", False)
        self.frame_groups = data.get("frame_groups", 1)
        self.frame_skip = data.get("frame_skip", 0)
        self.frame_start = data.get("frame_start", 0)
        self.video_streaming = data.get("video_streaming", False)
        self.video_path = data.get("video_path", "")
        self.speed_multiplier = data.get("speed_multiplier", 1)
        self.port = data.get("port", 5000)


class ScreenShareServer:
    """Flask server for screen sharing"""
    def __init__(self, config, log_queue=None):
        self.config = config
        self.log_queue = log_queue
        self.app = Flask(__name__)
        self.server = None
        self.running = False
        self.server_list = {}
        self.last_frame = []
        self.frame_count = 1
        self.cap = None
        self.request_count = 0
        self.last_request_time = None
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        self._setup_routes()
    
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] {message}"
        if self.log_queue:
            self.log_queue.put(log_msg)
        print(log_msg)
    
    def _setup_routes(self):
        @self.app.route('/', methods=['GET'])
        def health_check():
            return jsonify(status="running", resolution=f"{self.config.x_res}x{self.config.y_res}", fps=self.config.fps)
        
        @self.app.route('/', methods=['POST'])
        def return_frame():
            try:
                self.request_count += 1
                self.last_request_time = time.time()
                
                method = request.headers.get("R", "0")
                server_id = request.headers.get("I", "default")
                skip_frame = request.headers.get("F", "0")
                
                if server_id not in self.server_list:
                    self.server_list[server_id] = self.config.frame_start
                    self.log(f"New client connected: {server_id}")
                
                frames = []
                for _ in range(self.config.frame_groups):
                    start = time.time()
                    frames.append(self._encode_frame(method, server_id, skip_frame))
                    wait_offset = time.time() - start
                    sleep_time = max(0, 1/self.config.fps - wait_offset)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                
                return jsonify(
                    Fr=frames,
                    F=self.config.fps,
                    X=self.config.x_res,
                    Y=self.config.y_res,
                    G=self.config.frame_groups
                )
            except Exception as e:
                self.log(f"Error processing request: {str(e)}", "ERROR")
                return jsonify(error=str(e)), 500
    
    def _rgb_to_comp_hex(self, rgb):
        """Convert RGB to compressed hex format"""
        return f"{(rgb[0] >> 4):X}{(rgb[1] >> 4):X}{(rgb[2] >> 4):X}"
    
    def _grab_screen(self):
        """Capture screen in a separate thread to avoid blocking gevent"""
        return ImageGrab.grab()
    
    def _encode_frame(self, first_time, server_id, skip_frame):
        """Encode a frame for transmission"""
        if self.config.video_streaming and skip_frame == "1":
            self.server_list[server_id] += self.config.speed_multiplier
            if self.cap:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.server_list[server_id])
        
        if first_time == "1":
            self.last_frame = []
        
        try:
            if not self.config.video_streaming:
                future = self.executor.submit(self._grab_screen)
                screen = future.result(timeout=5)
                pic = screen.resize(
                    (self.config.x_res, self.config.y_res),
                    Image.Resampling.BILINEAR
                )
            else:
                if self.cap is None:
                    raise Exception("Video capture not initialized")
                
                playing, frame = self.cap.read()
                if not playing:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.server_list[server_id] = 0
                    _, frame = self.cap.read()
                
                pic = Image.fromarray(
                    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                ).resize((self.config.x_res, self.config.y_res), Image.Resampling.BILINEAR)
            
            if self.config.compressed_colors:
                pixels = [((pixel[0] >> 4) / 15, (pixel[1] >> 4) / 15, (pixel[2] >> 4) / 15, 1) for pixel in pic.getdata()][::-1]
                current_frame = [value for pixel in pixels for value in pixel]
            else:
                pixels = [(pixel[0]/255, pixel[1]/255, pixel[2]/255, 1) for pixel in pic.getdata()][::-1]
                current_frame = [value for pixel in pixels for value in pixel]
            
            return current_frame
            
        except Exception as e:
            self.log(f"Frame encoding error: {str(e)}", "ERROR")
            return []
    
    def start(self):
        """Start the server in a new thread"""
        if self.running:
            return False
        
        if self.config.video_streaming and self.config.video_path:
            self.cap = cv2.VideoCapture(self.config.video_path)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.config.frame_start)
            if not self.cap.isOpened():
                self.log(f"Failed to open video: {self.config.video_path}", "ERROR")
                return False
        
        try:
            self.server = WSGIServer(('0.0.0.0', self.config.port), self.app, log=None)
            self.running = True
            
            def run_server():
                self.log(f"Server started on port {self.config.port}")
                self.log(f"Resolution: {self.config.x_res}x{self.config.y_res} | FPS: {self.config.fps}")
                try:
                    self.server.serve_forever()
                except Exception as e:
                    self.log(f"Server error: {str(e)}", "ERROR")
                finally:
                    self.running = False
            
            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            return True
        except Exception as e:
            self.log(f"Failed to start server: {str(e)}", "ERROR")
            return False
    
    def stop(self):
        """Stop the server"""
        if self.server and self.running:
            self.server.stop()
            self.running = False
            if self.cap:
                self.cap.release()
                self.cap = None
            if self.executor:
                self.executor.shutdown(wait=False)
            self.log("Server stopped")
            return True
        return False


class ScreenShareGUI:
    """Main GUI Application"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Roblox Screen Share Server")
        self.root.geometry("800x700")
        self.root.minsize(700, 600)
        
        self.config = ScreenShareConfig()
        self.server = None
        self.preview_running = False
        self.log_queue = queue.Queue()
        
        style = ttk.Style()
        style.theme_use('clam')
        
        self._create_widgets()
        self._load_config()
        self._process_log_queue()
    
    def _create_widgets(self):
        """Create all GUI widgets"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(main_frame, text="Roblox Screen Share Server", font=('Helvetica', 16, 'bold'))
        title_label.pack(pady=(0, 10))
        
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        settings_frame = ttk.Frame(notebook, padding="10")
        notebook.add(settings_frame, text="Settings")
        
        log_frame = ttk.Frame(notebook, padding="10")
        notebook.add(log_frame, text="Server Log")
        
        self._create_settings_tab(settings_frame)
        self._create_log_tab(log_frame)
        
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        self.status_var = tk.StringVar(value="Status: Stopped")
        self.status_label = ttk.Label(control_frame, textvariable=self.status_var, font=('Helvetica', 10, 'bold'))
        self.status_label.pack(side=tk.LEFT)
        
        self.stats_var = tk.StringVar(value="")
        self.stats_label = ttk.Label(control_frame, textvariable=self.stats_var)
        self.stats_label.pack(side=tk.LEFT, padx=20)
        
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        self.start_btn = ttk.Button(btn_frame, text="Start Server", command=self._start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="Stop Server", command=self._stop_server, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        save_btn = ttk.Button(btn_frame, text="Save Config", command=self._save_config)
        save_btn.pack(side=tk.LEFT, padx=5)
    
    def _create_settings_tab(self, parent):
        """Create settings tab content"""
        left_frame = ttk.LabelFrame(parent, text="General Settings", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        right_frame = ttk.LabelFrame(parent, text="Video Settings", padding="10")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        ttk.Label(left_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.IntVar(value=self.config.port)
        port_spin = ttk.Spinbox(left_frame, from_=1024, to=65535, textvariable=self.port_var, width=10)
        port_spin.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(left_frame, text="FPS:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.fps_var = tk.IntVar(value=self.config.fps)
        fps_spin = ttk.Spinbox(left_frame, from_=1, to=60, textvariable=self.fps_var, width=10)
        fps_spin.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(left_frame, text="X Resolution:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.xres_var = tk.IntVar(value=self.config.x_res)
        xres_spin = ttk.Spinbox(left_frame, from_=16, to=1920, textvariable=self.xres_var, width=10)
        xres_spin.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(left_frame, text="Y Resolution:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.yres_var = tk.IntVar(value=self.config.y_res)
        yres_spin = ttk.Spinbox(left_frame, from_=9, to=1080, textvariable=self.yres_var, width=10)
        yres_spin.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(left_frame, text="Frame Groups:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.frame_groups_var = tk.IntVar(value=self.config.frame_groups)
        fg_spin = ttk.Spinbox(left_frame, from_=1, to=10, textvariable=self.frame_groups_var, width=10)
        fg_spin.grid(row=4, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(left_frame, text="Frame Skip:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.frame_skip_var = tk.IntVar(value=self.config.frame_skip)
        fs_spin = ttk.Spinbox(left_frame, from_=0, to=10, textvariable=self.frame_skip_var, width=10)
        fs_spin.grid(row=5, column=1, sticky=tk.W, pady=5)
        
        self.compressed_var = tk.BooleanVar(value=self.config.compressed_colors)
        compressed_check = ttk.Checkbutton(left_frame, text="Compress Colors (12-bit)", variable=self.compressed_var)
        compressed_check.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=10)
        
        self.video_var = tk.BooleanVar(value=self.config.video_streaming)
        video_check = ttk.Checkbutton(right_frame, text="Stream Video File", variable=self.video_var, command=self._toggle_video_mode)
        video_check.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(right_frame, text="Video File:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.video_path_var = tk.StringVar(value=self.config.video_path)
        video_entry = ttk.Entry(right_frame, textvariable=self.video_path_var, width=25)
        video_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        browse_btn = ttk.Button(right_frame, text="Browse", command=self._browse_video)
        browse_btn.grid(row=1, column=2, padx=5, pady=5)
        
        ttk.Label(right_frame, text="Start Frame:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.frame_start_var = tk.IntVar(value=self.config.frame_start)
        fs_entry = ttk.Spinbox(right_frame, from_=0, to=999999, textvariable=self.frame_start_var, width=10)
        fs_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(right_frame, text="Speed Multiplier:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.speed_var = tk.IntVar(value=self.config.speed_multiplier)
        speed_spin = ttk.Spinbox(right_frame, from_=1, to=10, textvariable=self.speed_var, width=10)
        speed_spin.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        info_frame = ttk.LabelFrame(right_frame, text="Quick Info", padding="10")
        info_frame.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=20)
        
        info_text = """Tips:
- Max FPS = FrameGroups x 8 (Roblox limit)
- Lower resolution = better performance
- Compress colors reduces quality but faster
- Set port to match your Roblox script"""
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT)
        info_label.pack(anchor=tk.W)
    
    def _create_log_tab(self, parent):
        """Create log tab content"""
        self.log_text = scrolledtext.ScrolledText(parent, height=20, font=('Courier', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        clear_btn = ttk.Button(parent, text="Clear Log", command=self._clear_log)
        clear_btn.pack(pady=5)
    
    def _log(self, message):
        """Add message to log (thread-safe via queue)"""
        self.log_queue.put(message)
    
    def _process_log_queue(self):
        """Process log messages from the queue on the main thread"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self._process_log_queue)
    
    def _clear_log(self):
        """Clear the log"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _toggle_video_mode(self):
        """Toggle between screen capture and video streaming"""
        pass
    
    def _browse_video(self):
        """Open file dialog to select video"""
        filepath = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov *.wmv"), ("All files", "*.*")]
        )
        if filepath:
            self.video_path_var.set(filepath)
    
    def _update_config_from_gui(self):
        """Update config from GUI values"""
        self.config.port = self.port_var.get()
        self.config.fps = self.fps_var.get()
        self.config.x_res = self.xres_var.get()
        self.config.y_res = self.yres_var.get()
        self.config.frame_groups = self.frame_groups_var.get()
        self.config.frame_skip = self.frame_skip_var.get()
        self.config.compressed_colors = self.compressed_var.get()
        self.config.video_streaming = self.video_var.get()
        self.config.video_path = self.video_path_var.get()
        self.config.frame_start = self.frame_start_var.get()
        self.config.speed_multiplier = self.speed_var.get()
    
    def _start_server(self):
        """Start the streaming server"""
        self._update_config_from_gui()
        
        if self.config.video_streaming and not self.config.video_path:
            messagebox.showerror("Error", "Please select a video file for video streaming mode.")
            return
        
        self.server = ScreenShareServer(self.config, self.log_queue)
        
        if self.server.start():
            self.status_var.set(f"Status: Running on port {self.config.port}")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self._update_stats()
        else:
            messagebox.showerror("Error", "Failed to start server. Check log for details.")
    
    def _stop_server(self):
        """Stop the streaming server"""
        if self.server:
            self.server.stop()
            self.server = None
        
        self.status_var.set("Status: Stopped")
        self.stats_var.set("")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
    
    def _update_stats(self):
        """Update statistics display"""
        if self.server and self.server.running:
            stats = f"Requests: {self.server.request_count}"
            if self.server.last_request_time:
                elapsed = time.time() - self.server.last_request_time
                if elapsed < 60:
                    stats += f" | Last: {int(elapsed)}s ago"
            self.stats_var.set(stats)
            self.root.after(1000, self._update_stats)
    
    def _save_config(self):
        """Save configuration to file"""
        self._update_config_from_gui()
        config_path = "screen_share_config.json"
        try:
            with open(config_path, 'w') as f:
                json.dump(self.config.to_dict(), f, indent=2)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._log(f"[{timestamp}] [INFO] Configuration saved to {config_path}")
            messagebox.showinfo("Success", "Configuration saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {str(e)}")
    
    def _load_config(self):
        """Load configuration from file"""
        config_path = "screen_share_config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                self.config.from_dict(data)
                self._update_gui_from_config()
                timestamp = datetime.now().strftime("%H:%M:%S")
                self._log(f"[{timestamp}] [INFO] Configuration loaded from file")
            except Exception as e:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self._log(f"[{timestamp}] [ERROR] Failed to load config: {str(e)}")
    
    def _update_gui_from_config(self):
        """Update GUI from config values"""
        self.port_var.set(self.config.port)
        self.fps_var.set(self.config.fps)
        self.xres_var.set(self.config.x_res)
        self.yres_var.set(self.config.y_res)
        self.frame_groups_var.set(self.config.frame_groups)
        self.frame_skip_var.set(self.config.frame_skip)
        self.compressed_var.set(self.config.compressed_colors)
        self.video_var.set(self.config.video_streaming)
        self.video_path_var.set(self.config.video_path)
        self.frame_start_var.set(self.config.frame_start)
        self.speed_var.set(self.config.speed_multiplier)
    
    def run(self):
        """Start the GUI"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
    
    def _on_close(self):
        """Handle window close"""
        if self.server and self.server.running:
            self.server.stop()
        self.root.destroy()


def main():
    app = ScreenShareGUI()
    app.run()


if __name__ == "__main__":
    main()
