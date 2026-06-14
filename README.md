# RD2040-ETH Turnstile Access Control

[![CircuitPython](https://img.shields.io/badge/CircuitPython-9.x+-orange)](https://circuitpython.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Firmware for a **network‑connected turnstile** based on the Waveshare RD2040-ETH board (RP2040 + CH9120 Ethernet).  
It reads barcodes via a USB keyboard‑emulating scanner (USB host on GP0/GP1), validates tickets over HTTP, controls relays and an LED bar, and provides an admin interface for configuration.

## Features

- **Two operation modes**  
  - `WORK` – normal ticket validation.  
  - `WAIT_PASS` – 5‑second window to enter admin password.  
  - `ADMIN` – accept new configuration (JSON) or reboot command.

- **Hardware peripherals**  
  - RGB LED (indicates state: red‑idle, yellow‑processing, green‑granted, purple‑admin).  
  - Two relays (barrier open / admin feedback).  
  - Passage sensor (IR barrier) to detect physical entry.  
  - Barcode scanner (USB HID keyboard) connected via USB host (GP0, GP1).

- **Network**  
  - CH9120 Ethernet chip controlled via UART (GP20/GP21).  
  - DHCP or static IP.  
  - HTTP GET requests to a remote server; response must contain a JSON with an `"allowed"` boolean.

- **Administration**  
  - Scan admin login code → enter password → receive new settings via JSON payload.  
  - Hard MCU reboot after successful configuration update.

## Hardware Requirements

| Component | Connection |
|-----------|------------|
| **RD2040-ETH** (RP2040) | Main controller |
| **Barcode scanner** (USB HID) | GP0 (D+), GP1 (D-), 5V, GND |
| **CH9120 Ethernet** | UART: GP20 (TX), GP21 (RX), plus CFG (GP18) and RST (GP19) |
| **RGB LED** (common cathode) | PWM pins (defined in `peripherals.py`) |
| **Relay 1** (barrier) | GPIO (defined in `peripherals.py`) |
| **Relay 2** (auxiliary) | GPIO (defined in `peripherals.py`) |
| **Passage sensor** (digital input) | GPIO (defined in `passage_sensor.py`) |

## Software & Dependencies

- **CircuitPython** 9.0.0‑beta.3 or newer (with `usb_host` support).
- Required libraries (copy to `lib/` on the board):
  - `adafruit_bus_device`
  - `adafruit_ticks`
  - `neopixel` (if using NeoPixel LED)
  - Or use built‑in `pwmio` for simple RGB LED.
- No external USB‑host libraries – relies on built‑in `usb_host` and `usb.core`.

## Installation

1. **Install CircuitPython** on the RD2040-ETH (follow [Waveshare guide](https://www.waveshare.com/wiki/RD2040-ETH)).
2. **Clone this repository** and copy the following files to the **CIRCUITPY** drive:
  code.py (or main.py)
  config_manager.py
  peripherals.py
  scanner.py
  ch9120.py
  http_client.py
  response_parser.py
  passage_sensor.py
3. **Edit `settings.json`** (or the default config inside `config_manager.py`) to set:
```json
# Network
"target_ip:"192.168.100.70"
"target_port":80
"api_path":"/api/data"
"dhcp":1                # 1 = DHCP, 0 = static
"static_ip":"192.168.1.100"
"subnet_mask":"255.255.255.0"
"gateway":"192.168.1.1"

# UART for CH9120
"uart_tx":"GP20"
"uart_rx":"GP21"
"baudrate":115200

# Admin codes
"admin_code":"admin"
"admin_pass":"12345"
```

4. Connect the scanner to GP0/GP1 (D+ / D‑) and power.
5. Power the board – the system starts in WORK mode (solid red LED).

## Usage

### HTTP Request Format

When a barcode is scanned in **WORK** mode, the system sends an HTTP GET request to the remote server. The full URL is built from three configuration parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `target_ip` | IP address of the server | `192.168.100.70` |
| `target_port` | TCP port (usually 80) | `80` |
| `api_path` | API endpoint path | `/api/data` |

**Request construction**:
```http
GET {api_path}/{scanned_barcode} HTTP/1.1
Host: {target_ip}:{target_port}
Connection: close
```

**Example** – if you scan barcode `123456`, the request becomes:
```http
GET /api/data/123456 HTTP/1.1
Host: 192.168.100.70:80
Connection: close
```

**Where to change these settings**  
- Edit the `settings.json` file (or the default values in `config_manager.py`).
- Or update them remotely by scanning a valid JSON configuration in **ADMIN** mode (e.g.,  
  `{"target_ip":"10.0.0.5","api_path":"/v2/check"}`).

**Note**: The server must respond with a JSON object containing a boolean field `"allowed"`. Example:
```json
{"allowed": true}
```

**Normal operation (WORK)**
- Scan a barcode → yellow LED → HTTP request → server response.
- If `allowed: true` → green LED, open barrier (relay 1), wait for passage sensor, back to red.
- If `allowed: false` → red blink + double relay pulse (admin‑declined pattern), back to red.

**Admin access**
- Enter admin login – scan the barcode containing admin_code (default "admin").
- LED turns purple, system waits 5 seconds for password.
- Enter password – scan the barcode containing admin_pass (default "12345").
  - `Correct`: LED stays purple, relays perform a long single pulse (trigger_admin_approved).
  - `Wrong`: back to WORK, double short pulse (trigger_admin_declined).
- In ADMIN mode you can:
  - `Reboot` – scan the same admin_pass again → double short pulse → MCU resets.
  - `Update configuration` – scan a JSON payload (see below) → if valid, save, approve pulse, reboot.

Configuration JSON format
The scanner must output a single line containing a JSON object. Example:
```json
{"target_ip":"192.168.1.200","admin_pass":"new123"}
```
All keys defined in config_manager.py are supported. After validation and merge, the system reboots to apply new settings.

## Customisation

LED colours – edit peripherals.py methods:
  - set_led_closed() (red)
  - set_led_processing() (yellow)
  - set_led_open() (green)
  - set_led_admin() (purple).
- Relay patterns – modify trigger_admin_approved() (long pulse) and trigger_admin_declined() (double short).
- Timeout values – change 5.0 in _handle_password_timeout() or HTTP timeouts in http_client.py.

## Troubleshooting

| Problem | Likely cause |	Solution |
|---------|--------------|-----------|
|Scanner not working | USB host not initialised or wrong pins	| Check scanner.py uses board.GP0, board.GP1. Ensure CircuitPython ≥9.0.0 |
|No network |	CH9120 not configured | Verify UART pins, baudrate, and apply_network_settings() |
|Relays not triggering | GPIO numbers mismatch | Double‑check relay pins in peripherals.py |
|Config update fails | JSON syntax error or missing required keys | Use valid JSON; check keys against config_manager.get_all() |

## License

This project is **free to use, modify, and distribute** for any purpose, private or commercial.  
No warranty is provided – use at your own risk.  
Attribution is appreciated but not required.

## Acknowledgements

[CircuitPython](https://circuitpython.org/)

[Waveshare RD2040-ETH](https://www.waveshare.com/wiki/RD2040-ETH)
