# Roblox Screen Share Server

## Overview
A Python-based screen sharing application with a modern GUI that streams your computer screen (or video files) to Roblox games via HTTP. Built with Flask backend and Tkinter frontend.

## Features
- Modern GUI with tabbed interface (Settings, Server Log)
- Screen capture mode for live desktop streaming
- Video file streaming mode
- Configurable settings (FPS, resolution, compression, etc.)
- Real-time server logging and statistics
- Save/load configuration presets
- Client connection tracking

## Project Structure
```
/
├── main.py                     # Main application with GUI and server
├── attached_assets/            # Original uploaded script
│   └── ScreenNew_1764308103965.py
├── screen_share_config.json    # Configuration file (generated on save)
└── replit.md                   # This documentation
```

## How to Use
1. Run the application - a GUI window will open
2. Configure settings in the "Settings" tab:
   - **Port**: Server port (default: 5000)
   - **FPS**: Frames per second (max depends on Roblox HTTP limits)
   - **Resolution**: X and Y resolution for the stream
   - **Frame Groups**: Number of frames sent per request
   - **Compress Colors**: Enable 12-bit color for better performance
3. For video streaming:
   - Check "Stream Video File"
   - Browse and select a video file
   - Configure start frame and speed multiplier
4. Click "Start Server" to begin streaming
5. Monitor the "Server Log" tab for connections and status
6. Use "Save Config" to save your settings

## API Endpoint
- **POST /**: Returns frame data
  - Headers:
    - `R`: Refresh flag ("1" to refresh)
    - `I`: Server/Client ID
    - `F`: Frame skip flag
  - Response: JSON with `Fr` (frames), `F` (fps), `X` (width), `Y` (height), `G` (frame groups)
- **GET /**: Health check endpoint

## Configuration Options
| Setting | Description | Default |
|---------|-------------|---------|
| Port | Server port | 5000 |
| FPS | Frames per second | 8 |
| X Resolution | Horizontal resolution | 400 |
| Y Resolution | Vertical resolution | 225 |
| Frame Groups | Frames per request | 1 |
| Frame Skip | Skip interval | 0 |
| Compress Colors | Use 12-bit color | False |
| Video Streaming | Stream video instead of screen | False |

## Technical Notes
- Max FPS = Frame Groups x 8 (due to Roblox HTTP request limits)
- Lower resolution improves performance
- Server binds to 0.0.0.0 for external access
- Uses gevent WSGI server for production-ready performance

## Dependencies
- Flask (web server)
- Pillow (image processing)
- OpenCV (video handling)
- gevent (WSGI server)
- tkinter (GUI - included with Python)

## Recent Changes
- **2025-11-28**: Created improved GUI version with:
  - Modern Tkinter interface
  - Configuration save/load
  - Real-time logging
  - Error handling improvements
  - Server statistics display
