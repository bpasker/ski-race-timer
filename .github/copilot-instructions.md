# Ski Race Timer - Copilot Instructions

## Project Overview

This project is a ski race timing system built with two Raspberry Pi Zero 2 W units communicating wirelessly via LoRa radio. One unit is placed at the start line and the other at the finish line. IR break beam sensors detect when a skier crosses each line, and elapsed time is displayed on 7-segment displays.

## Hardware

### Compute

- **2 x Raspberry Pi Zero 2 W with Header** — Main controllers for start and finish stations

### Communication

- **2 x Adafruit LoRa Radio Bonnet with OLED - RFM95W @ 915MHz (RadioFruit)** [ID:4074] — Wireless communication between start and finish stations via LoRa at 915 MHz. Includes a built-in 128x32 OLED display.

### Display

- **2 x Adafruit 1.2" 4-Digit 7-Segment Display w/I2C Backpack - Yellow** [ID:1269] — I2C-driven displays for showing race times at each station

### Controls

- **2 x Arcade Button with LED - 30mm Translucent Green** [ID:3487] — Primary action buttons (e.g., start/reset)
- **2 x Mini LED Arcade Button - 24mm Translucent Red** [ID:3430] — Secondary function buttons
- **2 x Mini LED Arcade Button - 24mm Translucent Blue** [ID:3432] — Secondary function buttons

### Sensing

- **2 x Sets IR Break Beam Sensor 5mm LEDs** — Counting module with split through-beam photoelectric switch for detecting skiers crossing start/finish lines
- **2 x Laser Diode Module 650nm 5mW Red (Dot)** — Visible alignment aids for positioning sensors

## Technical Notes

- The Raspberry Pi Zero 2 W runs Linux and supports Python (CircuitPython/Blinka) for Adafruit hardware.
- The LoRa Radio Bonnet connects via SPI and uses the RFM95W transceiver at 915 MHz.
- The 7-segment displays communicate over I2C using the HT16K33 backpack driver.
- Buttons and IR break beam sensors connect via GPIO pins.
- Prefer Python with the Adafruit CircuitPython libraries (adafruit-circuitpython-rfm9x, adafruit-circuitpython-ht16k33, etc.) and the Blinka compatibility layer for Raspberry Pi.

## Language & Libraries

- **Language**: Python 3.9+ (CPython on Raspberry Pi OS)
- **LoRa radio**: `adafruit-circuitpython-rfm9x` (SPI)
- **7-segment display**: `adafruit-circuitpython-ht16k33` (I2C)
- **OLED display**: `adafruit-circuitpython-ssd1306` (I2C)
- **GPIO**: `RPi.GPIO` or `gpiozero` (edge-detect callbacks for buttons and beam sensors)
- **Blinka**: `adafruit-blinka` (CircuitPython compatibility on Raspberry Pi)
- **CRC**: `crcmod` or `binascii` (LoRa message integrity)
- **Audio (future)**: `pygame.mixer` or `pyttsx3`
- Use `venv` for dependency isolation and `requirements.txt` for pinned versions.
