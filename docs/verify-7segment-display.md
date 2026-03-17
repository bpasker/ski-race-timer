# Verify 7-Segment Display over I2C

This guide verifies that the Adafruit 1.2" 4-Digit 7-Segment Display (HT16K33 backpack, ID:1269) is wired correctly and can be driven from Python over I2C. It covers basic operation, display formatting for race times, and troubleshooting.

## Prerequisites

- Blinka and CircuitPython libraries installed (see [setup-blinka-circuitpython.md](setup-blinka-circuitpython.md))
- I2C enabled (`/dev/i2c-1` exists)
- 7-segment display connected to I2C (SDA → GPIO 2, SCL → GPIO 3, VCC → 3.3V or 5V, GND → GND)
- SSH access to the station

## Wiring

The 7-segment display backpack has four connections:

| Backpack Pin | Pi Pin | Notes |
|---|---|---|
| SDA | GPIO 2 (SDA) | Shared I2C bus with OLED |
| SCL | GPIO 3 (SCL) | Shared I2C bus with OLED |
| VCC | 5V or 3.3V | 5V recommended for full brightness |
| GND | GND | |

The HT16K33 default I2C address is **0x70**. The OLED on the LoRa bonnet uses **0x3c**, so there is no conflict.

## Step 1: Detect the Display on the I2C Bus

Scan the I2C bus to confirm the display is detected:

```bash
sudo i2cdetect -y 1
```

Expected output should show `70` in the grid:

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
...
30: -- -- -- -- -- -- -- -- -- -- -- -- 3c -- -- --
...
70: 70 -- -- -- -- -- -- --
```

- `3c` = OLED on LoRa bonnet
- `70` = 7-segment display (HT16K33)

If `70` does not appear, see [Troubleshooting](#troubleshooting) below.

## Step 2: Basic Display Test

Activate the venv and run a quick test:

```bash
cd ~/ski-race-timer
source venv/bin/activate
python3 -c "
import board
import busio
from adafruit_ht16k33.segments import Seg7x4

i2c = busio.I2C(board.SCL, board.SDA)
display = Seg7x4(i2c)
display.brightness = 0.5
display.print('0.00')
print('Display should show 0.00')
"
```

The display should light up showing `0.00`. If this works, basic I2C communication is confirmed.

## Step 3: Test All Digits and Segments

Cycle through each digit position to verify all segments work:

```bash
python3 -c "
import time
import board
import busio
from adafruit_ht16k33.segments import Seg7x4

i2c = busio.I2C(board.SCL, board.SDA)
display = Seg7x4(i2c)
display.brightness = 0.5

# Test each digit 0-9 in all positions
for digit in range(10):
    display.fill(0)
    display.print(str(digit) * 4)
    print(f'Showing: {digit}{digit}{digit}{digit}')
    time.sleep(0.5)

# Fill all segments (shows 8888)
display.fill(1)
print('All segments on (8888)')
time.sleep(1)

# Clear
display.fill(0)
print('Display cleared')
"
```

Watch the display cycle through `0000`, `1111`, ..., `9999`, then all segments lit (`8888`), then blank. Any missing or flickering segments indicate a hardware issue.

## Step 4: Test Decimal Points and Colon

The HT16K33 Seg7x4 supports decimal points after each digit and a center colon. These are essential for race time formatting.

```bash
python3 -c "
import time
import board
import busio
from adafruit_ht16k33.segments import Seg7x4

i2c = busio.I2C(board.SCL, board.SDA)
display = Seg7x4(i2c)
display.brightness = 0.5

# Decimal point after digit 1 (position index 1)
display.fill(0)
display.print('12.34')
print('Showing: 12.34 (decimal after digit 2)')
time.sleep(2)

# Colon between digits 2 and 3
display.fill(0)
display.print('12:34')
print('Showing: 12:34 (colon on)')
time.sleep(2)

# Colon + decimal: M:SS.t format
display.fill(0)
display[0] = '1'
display[1] = '2'
display[2] = '3'
display[3] = '4'
display.colon = True
# Set decimal on digit index 2 (third digit)
display.set_decimal(2, True)
print('Showing: 1:23.4 (colon + decimal after digit 3)')
time.sleep(2)

display.fill(0)
print('Display cleared')
"
```

## Step 5: Test Race Display Formats

The ski timer uses three display formats depending on elapsed time:

| Time Range | Format | Example |
|---|---|---|
| 0 – 59.99s | `SS.hh` | `12.34` |
| 1:00 – 9:59.9 | `M:SS.t` | `1:23.4` |
| 10:00+ | `MM:SS` | `12:34` |

Test each format:

```bash
python3 -c "
import time
import board
import busio
from adafruit_ht16k33.segments import Seg7x4

i2c = busio.I2C(board.SCL, board.SDA)
display = Seg7x4(i2c)
display.brightness = 0.5

def show_race_time(elapsed_seconds):
    '''Format and display a race time on the 7-segment display.'''
    display.fill(0)
    display.colon = False

    if elapsed_seconds < 60:
        # SS.hh format: e.g., 12.34
        hundredths = int(elapsed_seconds * 100) % 100
        secs = int(elapsed_seconds) % 60
        text = f'{secs:02d}.{hundredths:02d}'
        display.print(text)
    elif elapsed_seconds < 600:
        # M:SS.t format: e.g., 1:23.4
        mins = int(elapsed_seconds) // 60
        secs = int(elapsed_seconds) % 60
        tenths = int(elapsed_seconds * 10) % 10
        display[0] = str(mins)
        display[1] = str(secs // 10)
        display[2] = str(secs % 10)
        display[3] = str(tenths)
        display.colon = True
        display.set_decimal(2, True)
    else:
        # MM:SS format: e.g., 12:34
        mins = int(elapsed_seconds) // 60
        secs = int(elapsed_seconds) % 60
        display.print(f'{mins:02d}{secs:02d}')
        display.colon = True

    return text if elapsed_seconds < 60 else ''

# Test SS.hh format
print('--- SS.hh format (under 60s) ---')
for t in [0.00, 5.55, 12.34, 45.67, 59.99]:
    show_race_time(t)
    print(f'  {t:.2f}s')
    time.sleep(1.5)

# Test M:SS.t format
print('--- M:SS.t format (1:00 - 9:59.9) ---')
for t in [60.0, 83.4, 123.4, 599.9]:
    show_race_time(t)
    mins = int(t) // 60
    secs = int(t) % 60
    tenths = int(t * 10) % 10
    print(f'  {t:.1f}s → {mins}:{secs:02d}.{tenths}')
    time.sleep(1.5)

# Test MM:SS format
print('--- MM:SS format (10:00+) ---')
for t in [600, 754, 1234]:
    show_race_time(t)
    mins = int(t) // 60
    secs = int(t) % 60
    print(f'  {t}s → {mins}:{secs:02d}')
    time.sleep(1.5)

# Show dashes (SYNCING state)
display.fill(0)
display.print('----')
print('Showing: ---- (syncing/not ready)')
time.sleep(1.5)

# Show 0.00 (READY state)
display.fill(0)
display.print('0.00')
print('Showing: 0.00 (ready)')
"
```

## Step 6: Test Brightness Control

The HT16K33 supports 16 brightness levels (0.0 to 1.0, mapped to 0–15 internally):

```bash
python3 -c "
import time
import board
import busio
from adafruit_ht16k33.segments import Seg7x4

i2c = busio.I2C(board.SCL, board.SDA)
display = Seg7x4(i2c)
display.print('8888')

# Ramp brightness up
for level in range(16):
    display.brightness = level / 15.0
    print(f'Brightness: {level}/15')
    time.sleep(0.3)

# Ramp back down
for level in range(15, -1, -1):
    display.brightness = level / 15.0
    time.sleep(0.3)

# Set to operating brightness
display.brightness = 0.5
display.print('0.00')
print('Set to 0.5 brightness')
"
```

Full brightness (`1.0`) is recommended for outdoor use in daylight. Lower values (`0.3–0.5`) are fine for indoor testing.

## Step 7: Run on Both Stations

Repeat Steps 1–6 on both stations:

```bash
# Station 1 (Start)
ssh brandon@192.168.1.204

# Station 2 (Finish)
ssh brandon@192.168.1.76
```

Both displays should behave identically.

## Troubleshooting

### Display not detected at 0x70

If `i2cdetect -y 1` does not show `70`:

1. **Check wiring**: Verify SDA, SCL, VCC, and GND are connected correctly. The backpack has labeled pins.
2. **Check power**: The HT16K33 needs 3.3V or 5V. Try both if unsure.
3. **Check for solder bridges**: The I2C address is set by solder jumpers on the backpack (A0, A1, A2). All open = `0x70`. If any are bridged, the address shifts:

   | A0 | A1 | A2 | Address |
   |---|---|---|---|
   | open | open | open | 0x70 |
   | closed | open | open | 0x71 |
   | open | closed | open | 0x72 |
   | closed | closed | open | 0x73 |

4. **I2C bus contention**: Disconnect all other I2C devices and test the display alone.
5. **Try bus 2**: Some Pi configurations expose a second I2C bus. Check `ls /dev/i2c*` and try `sudo i2cdetect -y 2`.
6. **Pull-up resistors**: The HT16K33 backpack has built-in pull-ups. If you have other I2C devices with pull-ups on the same bus, excessive pull-up current can cause issues (unlikely with just the OLED).

### Display detected but shows nothing

- Confirm `display.brightness` is not `0.0`.
- Try `display.fill(1)` to turn on all segments — if nothing lights, the LED module may not be seated in the backpack socket.
- Check that the LED display is inserted in the correct orientation on the backpack.

### Garbled or wrong segments

- Verify you're using `Seg7x4` (not `BigSeg7x4` or another variant).
- The Adafruit 1.2" display (ID:1269) uses the standard `Seg7x4` class.

### `OSError: [Errno 121] Remote I/O error`

- The I2C device stopped responding. Power cycle the display (unplug and replug VCC).
- Check for loose wires or intermittent connections.
- Reduce I2C bus speed if using long wires (add `dtparam=i2c_arm_baudrate=50000` to `/boot/config.txt`).
