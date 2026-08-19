# JoyProxy Tester

A lightweight, powerful desktop proxy testing and batch validation tool designed for HTTP/HTTPS, SOCKS5 TCP, and SOCKS5 UDP proxies.

![JoyProxy Tester](web/style.css)

## Features

- **Single Proxy Testing**:
  - Test connectivity and response times for **HTTP / TCP**, **SOCKS5 / TCP**, and **SOCKS5 / UDP** protocols.
  - Proxy authentication support (Username & Password).
  - Quick paste parsing (`host:port`, `user:pass@host:port`, or full proxy URLs).
  - Optional Windows system proxy synchronization.

- **IP & Geo Location Verification**:
  - Built-in multi-channel IP+Geo detection (`ipinfo.io`, `ipwhois.app`, `ip-api.com`, `api.myip.com`).
  - Custom target URL support for specialized endpoints.
  - Detailed response viewing with JSON formatting.

- **Batch Testing & API Extraction**:
  - Extract proxy endpoints dynamically via API URLs using regex patterns.
  - Automated sequential testing with real-time success rate, average latency metrics, and live logs.
  - Interval-based testing and manual single-switch mode.

- **SOCKS5 UDP Forwarding Verification**:
  - Built-in UDP ASSOCIATE test sending standard UDP DNS queries through the proxy.

## Tech Stack

- **Backend**: Python 3.10+ (pywebview, requests, PySocks, Flask for headless mode)
- **Frontend**: Modern Vanilla HTML5 / CSS3 / JavaScript
- **Packaging**: PyInstaller for standalone portable executable

## Getting Started

### Prerequisites

- Python 3.10 or higher

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/joyproxy/joyproxy-tester.git
   cd joyproxy-tester
   ```

2. Set up virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python app.py
   ```

### Building Portable Executable (Windows)

To build a standalone `.exe`:
```bash
python build_pc.py
```
The generated executable will be placed in `dist/`.

## License

MIT License
