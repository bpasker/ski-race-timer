# Install Blinka and CircuitPython Libraries

This guide installs Adafruit Blinka (the CircuitPython compatibility layer for Raspberry Pi) and all CircuitPython libraries required by the ski race timer: LoRa radio, 7-segment display, OLED display, and supporting packages.

## Background

Adafruit hardware libraries are written for CircuitPython, but the Raspberry Pi runs CPython. **Blinka** bridges the gap — it implements the CircuitPython `board`, `busio`, `digitalio`, and `microcontroller` APIs on top of CPython, so Adafruit libraries work on the Pi without modification.

Blinka requires:
- SPI enabled (for the LoRa radio bonnet)
- I2C enabled (for the 7-segment display and OLED)
- Python 3.9+ with `pip` and `venv`

## Prerequisites

- Raspberry Pi Zero 2 W running Raspberry Pi OS Bullseye or Bookworm (Lite recommended)
- SSH access to the Pi
- Internet access on the Pi (WiFi configured)
- If the read-only overlay is enabled, disable it first (see [setup-readonly-filesystem.md](setup-readonly-filesystem.md#temporarily-disabling-the-overlay-for-system-updates))

## Step 1: Enable SPI and I2C

The LoRa bonnet uses SPI; the 7-segment display and OLED use I2C. Both must be enabled in the Pi's configuration.

```bash
sudo raspi-config
```

Navigate to: **Interface Options** → **SPI** → **Yes** (enable)

Then: **Interface Options** → **I2C** → **Yes** (enable)

Reboot to apply:

```bash
sudo reboot
```

### Verify After Reboot

```bash
# SPI devices should appear
ls /dev/spidev*
# Expected: /dev/spidev0.0  /dev/spidev0.1

# I2C bus should appear
ls /dev/i2c*
# Expected: /dev/i2c-1

# Check that the kernel modules are loaded
lsmod | grep -E 'spi|i2c'
# Should see spi_bcm2835, i2c_bcm2835, i2c_dev, etc.
```

## Step 2: Install System Dependencies

Blinka and some Python libraries require native C extensions. Install the build tools and headers:

```bash
sudo apt update
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    libgpiod2 \
    i2c-tools
```

### Verify I2C Wiring (Optional)

If the LoRa bonnet and/or 7-segment display are already connected, scan the I2C bus to confirm they're detected:

```bash
sudo i2cdetect -y 1
```

Expected addresses:
- `0x3c` — OLED display (SSD1306 on the LoRa bonnet)
- `0x70` — 7-segment display (HT16K33 backpack, default address)

Both may appear once the hardware is wired. If nothing shows, check wiring and confirm I2C is enabled.

## Step 3: Create a Python Virtual Environment

All project dependencies are installed in an isolated venv to avoid conflicts with system packages.

```bash
# Create the project directory (if it doesn't exist)
mkdir -p ~/ski-race-timer
cd ~/ski-race-timer

# Create the venv
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip inside the venv
pip install --upgrade pip setuptools
```

The venv lives at `~/ski-race-timer/venv/`. It resides on the root filesystem, so if the read-only overlay is enabled, it will be lost on reboot. This is by design — the venv is recreated on deploy (see [Deployment Notes](#deployment-notes)).

## Step 4: Install Blinka

```bash
# Ensure the venv is activated
source ~/ski-race-timer/venv/bin/activate

pip install adafruit-blinka
```

This pulls in the core dependencies:
- `Adafruit-PlatformDetect` — identifies the Pi model
- `Adafruit-PureIO` — I2C interface
- `RPi.GPIO` — GPIO access (installed as a dependency)
- `spidev` — SPI interface

### Verify Blinka Installation

```bash
python3 -c "
import board
import busio
import digitalio
print('board ID:', board.board_id)
print('SPI pins:', board.SCK, board.MOSI, board.MISO)
print('I2C pins:', board.SCL, board.SDA)
print('Blinka is working!')
"
```

Expected output (Raspberry Pi Zero 2 W):

```
board ID: RASPBERRY_PI_ZERO_2W
SPI pins: SCK MOSI MISO
I2C pins: SCL SDA
Blinka is working!
```

If you get `RuntimeError: Not running on a known board`, ensure you're on a supported Raspberry Pi OS and that SPI/I2C are enabled.

## Step 5: Install CircuitPython Libraries

Install all Adafruit CircuitPython libraries used by the project:

```bash
# Ensure the venv is activated
source ~/ski-race-timer/venv/bin/activate

# LoRa radio (RFM95W on the LoRa bonnet, SPI)
pip install adafruit-circuitpython-rfm9x

# 7-segment display (HT16K33 backpack, I2C)
pip install adafruit-circuitpython-ht16k33

# OLED display (SSD1306 on the LoRa bonnet, I2C)
pip install adafruit-circuitpython-ssd1306
```

## Step 6: Install Additional Python Dependencies

These are not CircuitPython libraries but are needed by the application:

```bash
# CRC-16 for LoRa message integrity
pip install crcmod
```

`RPi.GPIO` is already installed as a Blinka dependency. If you prefer `gpiozero`:

```bash
# Optional — gpiozero as an alternative GPIO library
pip install gpiozero
```

## Step 7: Freeze Requirements

Pin all installed package versions for reproducible deployments:

```bash
pip freeze > ~/ski-race-timer/requirements.txt
```

This file is committed to the repo. On a fresh Pi, restore the exact environment with:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Step 8: Verify Each Hardware Library

Run these quick tests to confirm each library loads and can communicate with its hardware. The LoRa bonnet and 7-segment display must be connected.

### LoRa Radio (RFM95W)

```bash
python3 -c "
import board
import busio
import digitalio
import adafruit_rfm9x

spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
cs = digitalio.DigitalInOut(board.CE1)     # GPIO 7
reset = digitalio.DigitalInOut(board.D25)  # GPIO 25

rfm9x = adafruit_rfm9x.RFM9x(spi, cs, reset, 915.0)
print('LoRa radio initialized')
print('Frequency: 915.0 MHz')
print('TX power:', rfm9x.tx_power, 'dBm')
"
```

If this fails with a `RuntimeError`, check that the LoRa bonnet is seated properly and SPI is enabled.

### 7-Segment Display (HT16K33)

```bash
python3 -c "
import board
import busio
from adafruit_ht16k33.segments import Seg7x4

i2c = busio.I2C(board.SCL, board.SDA)
display = Seg7x4(i2c)
display.brightness = 0.5
display.print('0.00')
print('7-segment display initialized — should show 0.00')
"
```

### OLED Display (SSD1306)

```bash
python3 -c "
import board
import busio
import adafruit_ssd1306

i2c = busio.I2C(board.SCL, board.SDA)
oled = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
oled.fill(0)
oled.text('Ski Timer', 0, 0, 1)
oled.text('Ready', 0, 12, 1)
oled.show()
print('OLED initialized — should show text')
"
```

## Step 9: Re-enable Read-Only Overlay

If you disabled the overlay in the prerequisites, re-enable it now:

```bash
sudo raspi-config
# Performance Options → Overlay File System → Enable
# Boot partition write-protected → Yes
sudo reboot
```

After reboot, the venv and installed packages are baked into the overlay's base image. They will persist until the overlay is reset.

## Summary of Installed Packages

| Package | PyPI Name | Purpose |
|---|---|---|
| Blinka | `adafruit-blinka` | CircuitPython compatibility layer for CPython on Raspberry Pi |
| RFM9x | `adafruit-circuitpython-rfm9x` | LoRa radio driver (SPI, RFM95W at 915 MHz) |
| HT16K33 | `adafruit-circuitpython-ht16k33` | 7-segment display driver (I2C) |
| SSD1306 | `adafruit-circuitpython-ssd1306` | OLED display driver (I2C, 128x32) |
| crcmod | `crcmod` | CRC-16/CCITT for LoRa message integrity |
| RPi.GPIO | `RPi.GPIO` | GPIO access (installed as Blinka dependency) |

## Deployment Notes

Since the root filesystem is read-only (overlayfs), the venv on the root partition is immutable at runtime. Two strategies for keeping it in sync:

### Strategy A: Rebuild on Deploy (Simple)

The `deploy.sh` script disables the overlay, rsyncs code, recreates the venv from `requirements.txt`, and re-enables the overlay. Best for infrequent deploys where a reboot is acceptable.

### Strategy B: Deploy to /data (No Reboot)

Place the venv on the writable `/data` partition so it survives reboots and can be updated without toggling the overlay:

```bash
# On the Pi
python3 -m venv /data/app/venv
source /data/app/venv/bin/activate
pip install -r /data/app/requirements.txt
```

Update the systemd service `ExecStart` to use `/data/app/venv/bin/python`. See [setup-readonly-filesystem.md](setup-readonly-filesystem.md#deploying-application-code) for details.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'board'` | Blinka not installed, or venv not activated | Run `source venv/bin/activate` and verify `pip list \| grep Blinka` |
| `RuntimeError: Not running on a known board` | Platform detection failed | Ensure you're on Raspberry Pi OS (not a desktop Linux PC). Check `cat /proc/device-tree/model` |
| `PermissionError` on `/dev/spidev0.0` or `/dev/i2c-1` | User not in `spi`/`i2c`/`gpio` groups | Run `sudo usermod -aG spi,i2c,gpio $USER` and re-login |
| `ValueError: No I2C device at address 0x70` | 7-segment display not detected | Check I2C wiring (SDA→GPIO2, SCL→GPIO3). Run `sudo i2cdetect -y 1` |
| `RuntimeError: RFM9x not found` | LoRa bonnet not detected on SPI | Check bonnet is seated. Verify SPI enabled. Check CS pin (CE1/GPIO7) and reset pin (GPIO25) |
| `pip install` fails with build errors | Missing system headers | Run `sudo apt install python3-dev libgpiod2` |
| OLED shows nothing | Wrong I2C address or dimensions | Confirm address is `0x3c` with `i2cdetect`. Ensure dimensions are `128, 32` (not 128x64) |
