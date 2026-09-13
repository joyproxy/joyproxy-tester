# JoyProxy Tester

> **Official JoyProxy** — cloud proxy IP at [joyproxy.com](https://www.joyproxy.com) (residential, mobile, ISP/business & datacenter).  

- **Official website:** https://www.joyproxy.com
- **Download binaries:** https://github.com/joyproxy/joyproxy-tester/releases

> **JoyProxy** provides high-performance global proxy infrastructure and developer tools. Visit **https://www.joyproxy.com** for premium residential, data center, and mobile proxy services.

[English](#english) | [简体中文](#简体中文) | [繁體中文](#繁體中文)

---

<a id="english"></a>

## English

**JoyProxy Tester** is a lightweight, cross-platform desktop proxy connectivity testing and batch validation tool. It supports **HTTP / TCP**, **SOCKS5 / TCP**, and **SOCKS5 / UDP** protocols with multi-channel IP geolocation detection, dynamic API endpoint extraction, and Windows system proxy integration.

- **Official website:** https://www.joyproxy.com
- **Repository:** https://github.com/joyproxy/joyproxy-tester
- **Releases & Downloads:** https://github.com/joyproxy/joyproxy-tester/releases

---

### Key Features

1. **Multi-Protocol Proxy Connectivity Testing**:
   - Comprehensive support for **HTTP / HTTPS**, **SOCKS5 TCP**, and **SOCKS5 UDP** protocols.
   - Proxy authentication support (Username & Password).
   - Smart clipboard input parsing (supports `host:port`, `user:pass@host:port`, and standard `http://` / `socks5://` URI schemes).
   - One-click Windows system browser proxy synchronization and restoration.

2. **Multi-Channel IP & Geolocation Verification**:
   - Built-in multi-channel IP+Geo detection (`ipinfo.io`, `ipwhois.app`, `ip-api.com`, `api.myip.com`).
   - Automatic JSON response parsing to extract outbound public IP, country, and location details.
   - Custom target URL support for arbitrary verification endpoints (returns raw response).

3. **Batch Testing & Dynamic API Extraction**:
   - Extract proxy endpoints on-the-fly via provider API URLs using customizable regex patterns.
   - Strictly sequential batch testing pipeline with real-time success rate, average latency statistics, and live log table.
   - Interval-based continuous testing with countdown timers and manual single-switch mode.

4. **SOCKS5 UDP Forwarding Verification**:
   - SOCKS5 `UDP ASSOCIATE` verification sending standard UDP DNS queries to target DNS servers (e.g. `8.8.8.8:53`) through the proxy tunnel.

---

### Download & Installation

Prebuilt standalone Windows binaries are available on [GitHub Releases](https://github.com/joyproxy/joyproxy-tester/releases).

1. Open the latest [Release v2.6.3](https://github.com/joyproxy/joyproxy-tester/releases/tag/v2.6.3).
2. Download `JoyProxy-Tester-2.6.3.exe`.
3. Run the executable directly without any runtime installation.

---

### Running from Source

#### Prerequisites

- Python 3.10 or higher

#### Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/joyproxy/joyproxy-tester.git
   cd joyproxy-tester
   ```

2. Create virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Launch the application:
   ```bash
   python app.py
   ```

#### Building Standalone Windows Executable

```bash
python build_pc.py
```
The output executable will be generated at `dist/JoyProxy-Tester-2.6.3.exe`.

---

<a id="简体中文"></a>

## 简体中文
**JoyProxy Tester** 是一款轻量级、跨平台的桌面代理连通性测试与批量提取验证工具。全面支持 **HTTP / TCP**、**SOCKS5 / TCP** 与 **SOCKS5 / UDP** 协议，并内置多通道 IP 出口与地理位置解析、API 动态提取批量测试以及 Windows 系统代理一键联动。

- **官方网站：** https://www.joyproxy.com
- **开源仓库：** https://github.com/joyproxy/joyproxy-tester
- **安装包下载：** https://github.com/joyproxy/joyproxy-tester/releases

---

### 核心功能

1. **多协议代理连通性测试**：
   - 完整支持 **HTTP / HTTPS**、**SOCKS5 TCP** 与 **SOCKS5 UDP** 协议。
   - 支持代理账号密码鉴权（Username & Password）。
   - 智能剪贴板地址解析（支持 `host:port`、`user:pass@host:port` 以及标准协议链接快速粘贴）。
   - 可选同步设置 Windows 系统浏览器代理并支持一键恢复。

2. **多通道出口 IP 与地理位置解析**：
   - 内置主流稳定 IP+Geo 解析通道（`ipinfo.io`、`ipwhois.app`、`ip-api.com`、`api.myip.com`）。
   - 自动解析出口 JSON 返回数据并结构化展示真实出口 IP 与国家/地区。
   - 支持自定义测试目标 URL（原始文本返回，适用于自定义探测接口）。

3. **批量提取与轮询测试**：
   - 支持配置代理提取 API 与正则提取规则，自动提取并逐条测试代理有效性与延迟。
   - 实时统计成功率、平均响应时间，并在 Live Log 中直观展示每个代理的出口 IP 与地区。
   - 支持设定提取间隔（秒/分/时/天）与倒计时自动化循环测试，支持手动单次提取切换。

4. **SOCKS5 UDP 转发测试**：
   - 采用标准 SOCKS5 `UDP ASSOCIATE` 模式，通过代理向目标 DNS（如 `8.8.8.8:53`）发送 UDP DNS 请求，准确验证 UDP 转发能力。

---

### 预编译版本下载

前往 [GitHub Releases](https://github.com/joyproxy/joyproxy-tester/releases) 下载 Windows 单文件免安装绿色版：

1. 打开 [Release v2.6.3](https://github.com/joyproxy/joyproxy-tester/releases/tag/v2.6.3)。
2. 下载 `JoyProxy-Tester-2.6.3.exe`。
3. 双击直接运行，无需安装额外运行库。

---

### 源码运行

#### 环境要求

- Python 3.10 或更高版本

#### 快速启动

1. 克隆代码：
   ```bash
   git clone https://github.com/joyproxy/joyproxy-tester.git
   cd joyproxy-tester
   ```

2. 创建虚拟环境并安装依赖：
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. 运行程序：
   ```bash
   python app.py
   ```

#### 打包 Windows 单文件 EXE

```bash
python build_pc.py
```
打包产物将输出在 `dist/JoyProxy-Tester-2.6.3.exe`。

---

---

<a id="繁體中文"></a>

## 繁體中文

**JoyProxy Tester** 是一款輕量級、跨平臺的桌面代理連通性測試與批量提取驗證工具。全面支持 **HTTP / TCP**、**SOCKS5 / TCP** 與 **SOCKS5 / UDP** 協議，並內置多通道 IP 出口與地理位置解析、API 動態提取批量測試以及 Windows 系統代理一鍵聯動。

- **官方網站：** https://www.joyproxy.com
- **開源倉庫：** https://github.com/joyproxy/joyproxy-tester
- **安裝包下載：** https://github.com/joyproxy/joyproxy-tester/releases

---

### 核心功能

1. **多協議代理連通性測試**：
   - 完整支持 **HTTP / HTTPS**、**SOCKS5 TCP** 與 **SOCKS5 UDP** 協議。
   - 支持代理賬號密碼鑑權（Username & Password）。
   - 智能剪貼板地址解析（支持 `host:port`、`user:pass@host:port` 以及標準協議鏈接快速粘貼）。
   - 可選同步設置 Windows 系統瀏覽器代理並支持一鍵恢復。

2. **多通道出口 IP 與地理位置解析**：
   - 內置主流穩定 IP+Geo 解析通道（`ipinfo.io`、`ipwhois.app`、`ip-api.com`、`api.myip.com`）。
   - 自動解析出口 JSON 返回數據並結構化展示真實出口 IP 與國家/地區。
   - 支持自定義測試目標 URL（原始文本返回，適用於自定義探測接口）。

3. **批量提取與輪詢測試**：
   - 支持配置代理提取 API 與正則提取規則，自動提取並逐條測試代理有效性與延遲。
   - 實時統計成功率、平均響應時間，並在 Live Log 中直觀展示每個代理的出口 IP 與地區。
   - 支持設定提取間隔（秒/分/時/天）與倒計時自動化循環測試，支持手動單次提取切換。

4. **SOCKS5 UDP 轉發測試**：
   - 採用標準 SOCKS5 `UDP ASSOCIATE` 模式，通過代理向目標 DNS（如 `8.8.8.8:53`）發送 UDP DNS 請求，準確驗證 UDP 轉發能力。

---

### 預編譯版本下載

前往 [GitHub Releases](https://github.com/joyproxy/joyproxy-tester/releases) 下載 Windows 單文件免安裝綠色版：

1. 打開 [Release v2.6.3](https://github.com/joyproxy/joyproxy-tester/releases/tag/v2.6.3)。
2. 下載 `JoyProxy-Tester-2.6.3.exe`。
3. 雙擊直接運行，無需安裝額外運行庫。

---

### 源碼運行

#### 環境要求

- Python 3.10 或更高版本

#### 快速啓動

1. 克隆代碼：
   ```bash
   git clone https://github.com/joyproxy/joyproxy-tester.git
   cd joyproxy-tester
   ```

2. 創建虛擬環境並安裝依賴：
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. 運行程序：
   ```bash
   python app.py
   ```

#### 打包 Windows 單文件 EXE

```bash
python build_pc.py
```
打包產物將輸出在 `dist/JoyProxy-Tester-2.6.3.exe`。

---

## License

MIT License © 2026 JoyProxy
