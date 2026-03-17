# Ski Race Timer — Project Plan

## Core Concept

Two stations (Start and Finish) connected wirelessly via LoRa. The system times a single skier's run from top to bottom of the hill.

---

## Technology Stack

**Language: Python 3 (CPython on Raspberry Pi OS)**

Python is the right choice for this project because:

- All Adafruit hardware (LoRa bonnet, 7-segment display, OLED) has first-party CircuitPython libraries with Blinka compatibility for Raspberry Pi. No other language has this level of support.
- GPIO edge-detection callbacks fire on hardware interrupts, so beam-break timestamps captured via `time.monotonic_ns()` are precise to well within our < 2 ms sync target.
- Rapid iteration over SSH — critical when debugging a two-station wireless system outdoors.

### Libraries

| Layer | Library | Purpose |
|---|---|---|
| LoRa radio (SPI) | `adafruit-circuitpython-rfm9x` | Send/receive packets via RFM95W |
| 7-segment display (I2C) | `adafruit-circuitpython-ht16k33` | Drive HT16K33 4-digit display |
| OLED display (I2C) | `adafruit-circuitpython-ssd1306` | Drive 128x32 OLED on LoRa bonnet |
| GPIO (buttons, beams) | `RPi.GPIO` or `gpiozero` | Edge-detect callbacks, button reads, LED control |
| Blinka compatibility | `adafruit-blinka` | CircuitPython API on CPython/RPi |
| CRC-16 | `crcmod` or `binascii` | Message integrity checksums |
| Audio (future) | `pygame.mixer` or `pyttsx3` | Sound playback / text-to-speech |

### Python Version

- Target **Python 3.9+** (ships with Raspberry Pi OS Bullseye/Bookworm).
- Use `venv` for dependency isolation on each Pi.
- Pin library versions in `requirements.txt` for reproducibility.

### GPIO Pin Map

Both stations use identical wiring. The LoRa bonnet claims several pins; remaining GPIO is assigned to external components.

| GPIO | Function | Direction | Notes |
|---|---|---|---|
| 2 (SDA) | I2C data | bidir | Shared: OLED + 7-segment (different I2C addresses) |
| 3 (SCL) | I2C clock | bidir | Shared: OLED + 7-segment |
| 5 | Bonnet Button A | input | Pull-up on bonnet. Reserved — do not reassign. |
| 6 | Bonnet Button B | input | Pull-up on bonnet. Reserved — do not reassign. |
| 7 (CE1) | LoRa SPI CS | output | Active low chip select for RFM95W |
| 9 (MISO) | SPI data in | input | LoRa bonnet SPI0 |
| 10 (MOSI) | SPI data out | output | LoRa bonnet SPI0 |
| 11 (SCLK) | SPI clock | output | LoRa bonnet SPI0 |
| 12 | Bonnet Button C | input | Pull-up on bonnet. Reserved — do not reassign. |
| 13 | Red button | input | Pull-up, edge-detect |
| 16 | Blue button | input | Pull-up, edge-detect |
| 17 | IR beam sensor | input | Pull-up, edge-detect callback (falling = beam broken) |
| 19 | Red button LED | output | Via transistor/resistor |
| 22 | LoRa IRQ (DIO0) | input | Interrupt from RFM95W on packet ready |
| 23 | Green button | input | Pull-up, edge-detect |
| 24 | Green button LED | output | Via transistor/resistor |
| 25 | LoRa RST | output | Reset pin for RFM95W |
| 26 | Blue button LED | output | Via transistor/resistor |
| 27 | Laser diode | output | Via MOSFET — laser draws too much for direct GPIO |

**Notes**: Pin assignments are preliminary and may shift during wiring. GPIO 4, 14, 15, 18, 20, 21 remain available as spares (GPIO 14/15 are UART TX/RX — reserve for debug console). Confirm bonnet button GPIOs against your specific bonnet revision before soldering.

### Software Architecture

The system runs a **single-threaded async event loop** using Python's `asyncio`:

- **Main loop** (`asyncio.run`): Drives the state machine, schedules periodic tasks (heartbeats, sync, display refresh), and processes incoming LoRa packets.
- **GPIO callbacks**: `RPi.GPIO` edge-detect callbacks fire on interrupt threads. These callbacks do minimal work — capture `time.monotonic_ns()` and set an `asyncio.Event` or push a timestamp into a `queue.SimpleQueue` (thread-safe). The main loop awaits the event and processes the state transition.
- **LoRa send/receive**: Polled from the main loop. `rfm9x` does not support true async, so `receive()` is called with a short timeout (~50 ms) in a polling loop, yielding control between checks via `await asyncio.sleep(0)`.
- **Display updates**: 7-segment display updated at ~10 Hz via a periodic `asyncio` task. OLED updated at 1–2 Hz via a separate periodic task.
- **Scheduled tasks**: Heartbeat (every 5s), sync rounds (every 30s in READY), beam health check (every 2s in READY) — all as `asyncio` coroutines.
- **Shared state**: A single `StationState` object holds current state, timestamps, sync offset, race number, etc. No locks needed since only the main thread mutates it; GPIO callbacks only enqueue events.

This avoids threading complexity while keeping the system responsive. The 50 ms LoRa poll introduces at most 50 ms latency on packet reception, which is acceptable since beam-break timestamps are captured at interrupt time, not at processing time.

### LoRa RF Configuration

| Parameter | Value | Rationale |
|---|---|---|
| Frequency | 915 MHz | ISM band (US). Legal for unlicensed use. |
| Spreading Factor | SF7 | Fastest airtime. ~66 ms for a 30-byte packet. Required to fit within 200 ms ACK timeout. |
| Bandwidth | 125 kHz | Standard pairing with SF7. Good balance of range and speed. |
| Coding Rate | 4/5 | Minimal FEC overhead. CRC-16 in the application layer provides integrity. |
| TX Power | +20 dBm (100 mW) | Maximum legal power at 915 MHz. Ensures reliable link across a ski hill (~500m–2km). |
| Preamble Length | 8 symbols | Default. Sufficient for receiver sync. |
| Packet size | ≤ 128 bytes | Fits all message types comfortably (longest is ~40 bytes). |

At SF7/125kHz, a 30-byte packet has ~66 ms airtime. With 200 ms ACK timeout, there is room for the outbound packet (~66 ms) + processing (~5 ms) + ACK packet (~30 ms) with margin. If range proves insufficient, SF can be increased to SF8 or SF9, but ACK timeout must be increased proportionally.

---

## Race Flow

1. **System boots** — Both stations power on, establish LoRa link, and perform time synchronization.
2. **Time sync complete** — Stations enter READY state once clocks are aligned within acceptable tolerance.
3. **Beam alignment check** — Each station verifies its IR break beam sensor is aligned (receiver detects the IR emitter). Laser diodes turn on to provide a visible alignment aid. Each station sends its beam status (`BEAM_STATUS:OK` or `BEAM_STATUS:FAIL`) to the other via LoRa. The OLED on each station shows both beams: e.g., `start: OK  finish: --`. The system will not enter READY until both stations report `OK`. If a beam is knocked out of alignment during READY state, the affected station sends `BEAM_STATUS:FAIL`, both OLEDs identify which beam needs fixing (e.g., `! FINISH BEAM BLOCKED !`), and the system blocks new races until it's resolved. Lasers turn off once both beams are confirmed aligned.
4. **"Go" announcement** — Start station speaker tells the skier they can go.
5. **Skier crosses start beam** — IR break beam triggers at the top. Start station records a synchronized timestamp and sends `START:<sync_timestamp>` via LoRa. Both displays begin counting up.
6. **Skier crosses finish beam** — IR break beam triggers at the bottom. Finish station records its own synchronized timestamp and computes elapsed time locally: `elapsed = finish_sync_time - start_sync_time`. Sends `FINISH:<elapsed_ms>` back to start.
7. **Time announced** — Finish station speaker announces the race time aloud.
8. **Time displayed** — Both stations show the final time on their 7-segment displays for a short hold period (default 3 seconds).
9. **Auto-reset** — After the hold period, both stations return to READY state together (states stay in sync).
10. **Finish display hold** — When the next race starts, the finish station's 7-segment display continues showing the previous skier's time for a configurable display hold period (default 15 seconds), giving the skier time to stop and read it. Once the display hold expires, the finish display switches to the live running timer for the current race. The finish station is in RUNNING state the whole time — only the display content is delayed.

---

## Station Roles

### Start Station (Top of Hill)

| Component | Role |
|---|---|
| IR break beam | Detects skier crossing the start line |
| Laser diode (650nm red) | Visible alignment aid — shows where the IR beam path is |
| 7-segment display | Shows elapsed time / final time |
| LoRa radio | Sends START timestamp, receives FINISH message |
| OLED (on bonnet) | Status info (link quality, state, etc.) |
| Green button | Manual reset |
| Red button | TBD (future use) |
| Blue button | TBD (future use) |
| Speaker (future) | "Go!" announcement when system is ready |

### Finish Station (Bottom of Hill)

| Component | Role |
|---|---|
| IR break beam | Detects skier crossing the finish line |
| Laser diode (650nm red) | Visible alignment aid — shows where the IR beam path is |
| 7-segment display | Shows elapsed time / final time |
| LoRa radio | Receives START message, sends FINISH timestamp |
| OLED (on bonnet) | Status info (link quality, state, etc.) |
| Green button | Manual reset |
| Red button | TBD (future use) |
| Blue button | TBD (future use) |
| Speaker (future) | Announces race time aloud |

### Button LED Behavior

Each arcade button has a built-in LED. LEDs provide visual feedback of system state without looking at the OLED:

| Button | LED State | Meaning |
|---|---|---|
| Green | Off | System not ready (BOOT / SYNCING) |
| Green | Slow blink (1 Hz) | ALIGNING — beams need adjustment |
| Green | Solid on | READY — waiting for skier |
| Green | Fast blink (4 Hz) | RUNNING — race in progress |
| Green | Solid on | FINISHED — hold period |
| Red | Off | Normal operation |
| Red | Solid on | Error condition (NO LINK, BEAM BLOCKED, SYNC POOR) |
| Red | Slow blink | TIMEOUT — race exceeded max duration |
| Blue | Off | Normal operation |
| Blue | Solid on | TBD (future use — e.g., scrolling past results) |

### LoRa Bonnet Onboard Buttons

The Adafruit LoRa Radio Bonnet (ID:4074) has three tactile buttons (A, B, C) wired to GPIO 5, 6, and 12. These are separate from the external arcade buttons.

| Button | Function |
|---|---|
| A (GPIO 5) | Cycle OLED display pages (status → recent results → config → back) |
| B (GPIO 6) | Force re-sync (hold 2s in READY state to trigger immediate sync round) |
| C (GPIO 12) | Enter/exit alignment mode manually (turn lasers on, show beam status) |

These buttons are small and recessed — intended for operator use only, not skier-facing.

---

## System States

```
BOOT ──▶ SYNCING ──▶ ALIGNING ──▶ READY ──▶ RUNNING ──▶ FINISHED ──▶ READY
                                    ▲                        │
                                    │  (auto-reset / hold)   │
                                    │                        ▼
                                    └──── RESET (green button) ◄──┘
```

| State | Description |
|---|---|
| **BOOT** | Hardware initialization. I2C, SPI, GPIO setup. Display shows firmware version briefly. Transitions to SYNCING once LoRa radio is initialized and first heartbeat exchange confirms the other station is alive. If the other station is not detected within 30 seconds, display "NO PARTNER" warning and keep retrying. |
| **SYNCING** | Running NTP-like clock sync rounds. OLED shows sync progress (round count, offset, stddev). 7-segment display shows `----`. Transitions to ALIGNING once sync quality meets threshold (stddev < 2 ms). A RESET during SYNCING restarts the sync process. |
| **ALIGNING** | Both beams must report OK. Lasers are ON. OLED shows per-station beam status. 7-segment display shows `----`. Transitions to READY once both stations report `BEAM_STATUS:OK`. A RESET during ALIGNING has no effect (already pre-race). If sync degrades below threshold during ALIGNING, transitions back to SYNCING. |
| **READY** | Waiting for skier. Display shows `0.00`. Start speaker says "Go!" Periodic re-sync continues in background. If a beam becomes blocked, transitions back to ALIGNING. |
| **RUNNING** | Timer counting up on both displays. Triggered by start beam break. No re-sync during this state. |
| **FINISHED** | Final time shown on both displays. Both stations hold for ~3 seconds. The finish station initiates the transition: after the hold period expires, it sends a `RESET` message to coordinate both stations returning to READY simultaneously. If the RESET is not ACKed, heartbeat-based state reconciliation will catch the mismatch within 5 seconds. |
| **RESET** | Green button pressed — immediately returns to READY from RUNNING or FINISHED. From READY, it's a no-op (system is already ready). The reset does NOT increment the race number — only a completed race (FINISHED) increments it. |

---

## LoRa Time Synchronization

Both stations maintain a shared time reference using an NTP-like sync protocol over LoRa. This allows each station to independently record precise beam-break moments and compute elapsed race time without LoRa transmission latency affecting accuracy.

### Sync Protocol

Uses a four-timestamp round-trip exchange (like NTP Simplified):

```
Start Station                          Finish Station
     │                                       │
     │──── SYNC_REQ  { t1 } ───────────────▶│
     │                                  t2 = local time on receive
     │                                  t3 = local time on send
     │◀─── SYNC_RESP { t1, t2, t3 } ────────│
     │  t4 = local time on receive           │
     │                                       │
     │  round_trip = (t4 - t1) - (t3 - t2)  │
     │  offset = ((t2 - t1) + (t3 - t4)) / 2│
     │                                       │
```

- **Offset**: difference between the two clocks. Applied to convert local time → synchronized time.
- **Round-trip time**: measures link latency; if too high, discard the sample.
- **Multiple rounds**: run N sync exchanges (e.g., 10), discard outliers, average the offset for stability.
- **Periodic re-sync**: repeat every ~30 seconds during idle (READY state) to compensate for clock drift. Do NOT re-sync during a race (RUNNING state).
- **Sync quality**: track standard deviation of offset samples. Display sync status on OLED. Only enter READY when offset is stable (e.g., std dev < 2 ms).

### Synchronized Timestamps

The **finish station's clock is the reference**. The start station computes `offset_ns` = the correction needed to translate its own `monotonic_ns()` into the finish station's time frame. Concretely: `offset_ns ≈ finish_clock - start_clock`, so `start_monotonic_ns() + offset_ns ≈ finish_monotonic_ns()` at the same real-world instant.

Each station computes synchronized time as:

```
sync_time = time.monotonic_ns() + offset_ns
```

- On the **start station**, `offset_ns` is the computed NTP offset (nonzero). `start_sync_time = start_monotonic_ns() + offset_ns`.
- On the **finish station**, `offset_ns = 0` (it IS the reference). `finish_sync_time = finish_monotonic_ns()`.
- The start station sends `start_sync_time` in the START message.
- The finish station computes `elapsed = finish_sync_time - start_sync_time`. Both timestamps are in the finish station's time frame.
- This is precise because LoRa latency does NOT affect the elapsed calculation — both timestamps are in the same synchronized time base.
- **Integer arithmetic only**: All timestamps and offsets are in nanoseconds as Python `int`. Never convert to `float` — this preserves full precision and avoids floating-point truncation.

---

## LoRa Message Protocol

### Message Frame Format

Every message uses a structured frame to ensure integrity and enable retries:

```
<seq>|<type>:<payload>|<crc16>
```

- **seq**: 8-bit sequence number (0–255, wraps). Used to detect duplicates and match ACKs.
- **type**: message type string (see table below).
- **payload**: type-specific data, colon-separated fields.
- **crc16**: CRC-16/CCITT of everything before the final `|`. Reject messages with mismatched CRC.

Example: `42|START:1709876543210|A3F7`

### Message Types

| Message | Direction | Payload | Purpose |
|---|---|---|---|
| `SYNC_REQ` | Start → Finish | `<t1>` | Initiate clock sync exchange |
| `SYNC_RESP` | Finish → Start | `<t1>:<t2>:<t3>` | Complete sync exchange |
| `START` | Start → Finish | `<sync_timestamp_ns>:<race_number>` | Race has begun — **critical, requires ACK** |
| `START_ACK` | Finish → Start | `<seq>` | Confirms START received |
| `FINISH` | Finish → Start | `<elapsed_ms>` | Race ended — **critical, requires ACK** |
| `FINISH_ACK` | Start → Finish | `<seq>` | Confirms FINISH received |
| `RESET` | Either → Either | (none) | Manual reset — **sent 3x redundantly** |
| `RESET_ACK` | Either → Either | `<seq>` | Confirms RESET received |
| `BEAM_STATUS` | Both | `<OK\|FAIL>` | Report local beam alignment to other station — **best-effort** |
| `HEARTBEAT` | Both | `<state>:<sync_quality_ms>:<beam_ok>:<race_number>` | Connection health, state reconciliation, beam status |

### Reliability Rules

1. **Critical messages (START, FINISH, RESET) use ACK + retry**:
   - After sending, wait up to 200 ms for an ACK.
   - If no ACK, retransmit. Up to 5 retries (total 6 attempts, ~1.2s).
   - Receiver uses sequence number to de-duplicate (ignore if already processed same seq).

2. **RESET uses triple-send as backup**: Send the RESET message 3 times in rapid succession (50 ms apart) in addition to ACK/retry. This ensures it gets through even in poor conditions, since a stuck state is the worst user experience.

3. **SYNC messages are best-effort**: No ACK needed. If one is lost, the next sync round will cover it. Many rounds are run, so individual losses don't matter.

4. **BEAM_STATUS is best-effort**: Sent on beam state change (aligned → blocked or vice versa). No ACK. The current beam status is also included in every HEARTBEAT as a fallback, so even if a BEAM_STATUS message is lost, the next heartbeat will convey the correct state.

5. **HEARTBEAT is best-effort**: Sent every 5 seconds. No ACK. Used for link monitoring, state reconciliation, and beam status propagation (see below).

6. **CRC validation**: Any message with a bad CRC is silently dropped. Logged for diagnostics.

7. **Sequence number wrapping**: 0–255, wraps around. Receiver tracks last-seen seq per message type to de-duplicate within a window of 16.

8. **Half-duplex collision avoidance**: LoRa is half-duplex — simultaneous transmissions from both stations corrupt both packets. Mitigations:
   - **Suppress heartbeats while awaiting ACK**: If a station has sent a critical message (START, FINISH, RESET) and is waiting for an ACK, it defers any scheduled heartbeat or sync transmission until the ACK exchange completes or times out.
   - **Randomized heartbeat jitter**: Each heartbeat interval is 5s ± random(0–1s) to avoid persistent collision patterns between the two stations.
   - **Sync is master/slave**: Only the start station initiates SYNC_REQ. The finish station only responds. No collision possible in the sync exchange itself.
   - **Listen-before-talk is not needed**: At SF7/125kHz the duty cycle is very low (< 1%). Collisions are rare and tolerable for best-effort messages. The ACK/retry mechanism handles the critical path.

---

## Reliability & Failure Handling

### Beam Sensor Robustness

- **Debounce**: Ignore beam breaks within 500 ms of a previous break on the same sensor. A skier takes at least a second to pass; anything faster is noise (snow, wind, debris).
- **RUNNING state lockout**: Once in RUNNING state, the start beam is ignored (prevents a second skier or wind from "restarting" the race). Only the finish beam or a manual RESET can end the RUNNING state.
- **READY gate**: Beam breaks are only acted on in READY state (start beam) or RUNNING state (finish beam). Breaks in FINISHED state are ignored.
- **Beam health monitoring**: Periodically check that the beam is unbroken during READY state. If the beam appears continuously broken (blocked by snow/ice), show a warning on the OLED.

### Beam Alignment & Laser Diodes

The IR break beam sensors use invisible infrared light (5mm LEDs). The 650nm red laser diodes provide a visible dot so you can physically aim the emitter and receiver at each other during setup.

- **Mounting**: Mount each laser diode parallel to (or co-located with) the IR emitter, pointed in the same direction. The red dot shows exactly where the IR beam is aimed.
- **Alignment mode**: On boot or triggered by a button, the system enters alignment mode:
  - Laser turns ON.
  - The OLED shows both beam statuses: local and remote. E.g., `start: OK  finish: --` (waiting) or `start: OK  finish: OK`.
  - Each station sends `BEAM_STATUS:OK` or `BEAM_STATUS:FAIL` to the other via LoRa whenever its local beam state changes.
  - Adjust the emitter/receiver positions until the red dot hits the receiver and the OLED confirms both beams `OK`.
  - The system will not transition to READY until both stations report their beam as aligned.
- **Auto-off**: Once both beams are confirmed aligned and the system enters READY state, both lasers turn OFF to save power and avoid distracting skiers.
- **Misalignment warning**: If a beam becomes continuously broken during READY state (e.g., something knocked the sensor), the affected station sends `BEAM_STATUS:FAIL` to the other. Both OLEDs show which beam is blocked (e.g., `! START BEAM BLOCKED !` or `! FINISH BEAM BLOCKED !`). The affected station's laser turns back ON so the operator can see the beam path and re-align. The system blocks new races until the beam is restored and both stations report `OK` again.
- **GPIO control**: Each laser diode is driven by a GPIO pin (HIGH = on, LOW = off) through a transistor or MOSFET since the laser draws more current than a GPIO pin should source directly.

### State Reconciliation

- **Heartbeats carry state**: Each heartbeat includes the sender's current state. If the other station detects a mismatch that shouldn't exist (e.g., one is RUNNING, the other is READY for > 3 seconds), display a warning on the OLED.
- **Finish without START**: If the finish station beam breaks but it's in READY state (never received a START), it ignores the break. It does NOT start a race on its own.
- **START without FINISH (timeout)**: If the race has been RUNNING for longer than a configurable maximum (e.g., 5 minutes), auto-reset with a "TIMEOUT" warning. The skier likely fell, took a different path, or the finish beam failed.
- **Lost ACK recovery**: If the start station sends START but never gets START_ACK after all retries, it shows a "NO LINK" warning on the OLED but continues running the timer locally. The finish station may still have received the START. When the finish station eventually sends FINISH, the start station can reconcile.

### LoRa Link Failure

- **Link quality tracking**: Track RSSI and success rate from heartbeats. Display on OLED as signal bars or a number.
- **Link lost detection**: If no heartbeat received for 15 seconds, display "NO LINK" warning. System continues to function locally — the timer still runs on each station independently.
- **Graceful degradation**: Even with total LoRa failure, each station can operate stand-alone:
  - Start station: records start time, shows running timer, but cannot display final time (shows "----" until link restored or manual reset).
  - Finish station: if it received the START before link died, it can still compute and display the final time. If it never got START, it shows "NO START" on beam break.

### Race Result Integrity

- **Authoritative time**: The finish station's computed elapsed time (`finish_sync_time - start_sync_time`) is the official result. The start station displays whatever the finish station reports.
- **Local backup**: Both stations log all beam-break timestamps (local and synced) to a local file. Even if LoRa fails, race times can be reconstructed after the fact by examining logs from both stations.
- **Race log**: Each completed race is appended to a CSV log file with: race number, start sync time, finish sync time, elapsed time, sync quality at race start, RSSI, and any warnings.
- **Log rotation**: Race CSV logs use one file per day (`races_YYYY-MM-DD.csv`). Debug logs (beam-break timestamps, LoRa packet dumps) rotate at 10 MB using Python's `RotatingFileHandler`. On a typical day of racing (< 200 runs), the CSV file is a few KB. SD card usage is not a concern for race logs, but debug logs can grow fast — capped at 50 MB total (5 × 10 MB files).

### SD Card Protection & Safe Shutdown

The root filesystem is vulnerable to corruption on sudden power loss (dead battery, unplugged cable). Mitigations:

- **Read-only root filesystem**: Use `overlayfs` (Raspberry Pi OS supports `raspi-config` → Overlay FS). The root partition is mounted read-only with a RAM overlay. All writes go to RAM and are lost on reboot — this makes the OS immune to SD corruption.
- **Writable data partition**: A separate `/data` partition (ext4 with `sync` mount option) stores race logs and configuration. Writes are small and infrequent (one CSV row per race, config changes).
- **fsync after log writes**: Every CSV row write is followed by `file.flush()` + `os.fsync(fd)` to ensure the data hits the SD card before the next race.
- **Graceful shutdown**: Holding the green + red buttons simultaneously for 3 seconds triggers `sudo shutdown -h now`. The OLED shows "SHUTTING DOWN..." and the 7-segment display shows `OFF`. This is safer than pulling the power cable.

### Process Supervision & Watchdog

- **systemd service**: The timer application runs as a `systemd` service (`ski-timer.service`) with `Restart=always` and `RestartSec=3`. If the Python process crashes, it auto-restarts within 3 seconds.
- **Hardware watchdog**: Enable the BCM2835 hardware watchdog (`dtparam=watchdog=on` in `config.txt`). The Python process pets the watchdog via `/dev/watchdog` every 5 seconds. If the process hangs (not just crashes), the Pi reboots automatically after 15 seconds.
- **Auto-start on boot**: The systemd service is enabled (`systemctl enable ski-timer`), so the system is operational within ~15 seconds of power-on with no user intervention.

### Environmental Considerations

- **Cold weather**: Raspberry Pi operates down to 0°C officially, but typically works to about -10°C. Enclosures with hand warmers or insulation recommended for very cold days. Monitor CPU temperature via software.
- **Moisture**: Enclosures must be weather-sealed. Buttons and beam sensors need splash protection.
- **Battery**: If battery-powered, monitor voltage and warn on OLED when low. Cold temperatures reduce battery capacity significantly — plan for 2x the expected power draw.
- **Sunlight**: IR beam sensors can be affected by bright sunlight. The break beam modules have matched receiver filters, but aim to shade the receiver from direct sun if possible.

---

## Build Phases

### Phase 1 — Hardware Bring-Up
- [x] Set up Raspberry Pi OS on both Pi Zero 2 W units
- [ ] Configure read-only root filesystem (overlayfs) + writable /data partition
- [x] Install Blinka and CircuitPython libraries
- [x] Verify LoRa bonnet: send/receive test messages between units
- [ ] Verify 7-segment display: write numbers over I2C
- [ ] Verify IR break beam sensors: detect beam interruption via GPIO
- [ ] Verify buttons: read GPIO input with LED control (including button LEDs)
- [ ] Verify OLED on LoRa bonnet: display text
- [ ] Verify bonnet buttons (A, B, C) via GPIO
- [ ] Verify laser diode control via GPIO + MOSFET
- [ ] Create systemd service + enable hardware watchdog
- [ ] Create deploy.sh script for rsync-based deployment

### Phase 2 — LoRa Message Layer
- [ ] Implement message frame format (seq, type, payload, CRC-16)
- [ ] Implement CRC-16/CCITT calculation and validation
- [ ] Implement ACK/retry logic for critical messages (START, FINISH, RESET)
- [ ] Implement sequence number tracking and de-duplication
- [ ] Implement triple-send for RESET messages
- [ ] Implement heartbeat send/receive (every 5s)
- [ ] Track link quality (RSSI, heartbeat success rate)

### Phase 3 — Time Synchronization
- [ ] Implement SYNC_REQ / SYNC_RESP message exchange
- [ ] Calculate clock offset using four-timestamp NTP-like algorithm
- [ ] Run multiple sync rounds and average (discard outliers)
- [ ] Periodic re-sync during READY state (~30s interval)
- [ ] Display sync quality on OLED (offset, std dev, status)
- [ ] Gate READY state on sync quality threshold

### Phase 4 — Core Timer Logic
- [ ] Implement state machine (BOOT → SYNCING → ALIGNING → READY → RUNNING → FINISHED → READY)
- [ ] Start beam break records sync timestamp and sends START message
- [ ] Finish beam break records sync timestamp, computes elapsed time
- [ ] Beam debouncing (500 ms ignore window)
- [ ] Start beam lockout during RUNNING state
- [ ] Race timeout (auto-reset after configurable max, e.g., 5 min)
- [ ] Display elapsed time on 7-segment displays (both stations)
- [ ] Auto-reset after configurable hold period (~3s, finish station sends RESET)
- [ ] Finish display hold: show previous time for ~15s after new race starts, then switch to live timer
- [ ] Finish display hold edge case: new FINISHED overrides held previous time immediately
- [ ] Green button triggers manual reset at any time
- [ ] Race number tracking (start station owns, included in START message)
- [ ] Button LED state management per system state
- [ ] State reconciliation via heartbeat comparison
- [ ] Graceful degradation when LoRa link is lost
- [ ] Load configuration from config.yaml

### Phase 5 — Logging & Diagnostics
- [ ] Log all beam-break timestamps to local file on each station
- [ ] CSV race log (race number, times, sync quality, RSSI, warnings) — one file per day
- [ ] Debug log with rotation (RotatingFileHandler, 10 MB × 5 files)
- [ ] Beam health monitoring (detect blocked beam in READY state)
- [ ] OLED status display (link quality, sync status, state, warnings)
- [ ] fsync after each log write for SD card safety

### Phase 6 — Audio (Future)
- [ ] Select and integrate speaker/amplifier hardware
- [ ] Start station: "Go!" announcement on READY state
- [ ] Finish station: text-to-speech or pre-recorded time announcement
- [ ] Audio for countdown or other cues

### Phase 7 — Polish & Extras
- [ ] Configurable hold time, display brightness, audio volume (via config.yaml)
- [ ] Red/blue button functions (e.g., scroll through past times, settings)
- [ ] Bonnet button functions (OLED page cycling, force re-sync, manual alignment mode)
- [ ] CPU temperature monitoring and warnings
- [ ] Battery voltage monitoring (if battery-powered)
- [ ] Enclosure design considerations (weather sealing, insulation)
- [ ] Graceful shutdown via green + red button hold (3s)
- [ ] Unit tests for sync math, message parsing, CRC, state machine, display formatting

---

## Key Design Decisions

- **Time source**: Both stations use `time.monotonic_ns()` adjusted by a synchronized offset calculated via NTP-like LoRa exchanges. Each station records its own beam-break moment in synchronized time. Elapsed time = `finish_sync_time - start_sync_time`. LoRa transmission latency does NOT affect timing precision.
- **Sync precision target**: < 2 ms offset standard deviation across sync samples before allowing races.
- **Sync during race**: No re-syncing while in RUNNING state to avoid jitter. Offset is frozen from the last sync before the race started.
- **Display format**: `SS.hh` (seconds + hundredths) for times under 1 minute, `M:SS.h` (minutes, seconds, tenths) for times 1–9 minutes. The 4-digit display + colon gives enough resolution.
- **Live timer**: During RUNNING state, both displays count up in real-time using their local synced clocks. The start station knows the start time locally; the finish station receives it via LoRa and counts from that. Updates at ~10 Hz for smooth display.
- **Hold period**: Both stations hold FINISHED for ~3 seconds, then reset to READY together. The finish station sends a RESET after the hold expires to coordinate the transition.
- **Finish display hold**: When a new race starts, the finish station's 7-segment display continues showing the previous skier's time for ~15 seconds (configurable) before switching to the live running timer. This gives the skier at the bottom time to read their result without delaying the next racer at the top. The finish station is fully in RUNNING state during this period — only the display content is delayed. **Edge case**: If the current race finishes while the display hold is still active (race completed in < 15 seconds), the new final time immediately replaces the held time. The current race's result always takes priority over the previous one.
- **Reset**: Green button on either station resets both stations via LoRa broadcast.
- **Race number**: Owned by the start station. Starts at 1 on boot, increments on each FINISHED → READY transition (completed race). Included in the `START` message payload so the finish station stays in sync. A manual RESET does not increment the race number. The number is also included in heartbeats for reconciliation. Resets to 1 on reboot (persistent numbering across sessions is a future feature).
- **Display format boundary**: At 59.99 → 60.00 seconds, the format switches from `SS.hh` (hundredths) to `M:SS.t` (tenths). Precision drops. This is an inherent 4-digit display limitation and is acceptable for ski racing — runs over 60 seconds are less competitive and tenths-of-a-second resolution is sufficient.

### Configuration

All tunable parameters live in a single `config.yaml` file on the `/data` partition (survives the read-only overlay). The application reads it at startup. Changes require a restart (no live-reload needed).

```yaml
role: start  # or "finish"
hold_period_s: 3
display_hold_s: 15
race_timeout_s: 300
sync_interval_s: 30
heartbeat_interval_s: 5
beam_debounce_ms: 500
sync_threshold_stddev_ms: 2
link_lost_timeout_s: 15
display_brightness: 12  # 0–15 for HT16K33
ack_timeout_ms: 200
ack_retries: 5
lora_spreading_factor: 7
lora_tx_power: 20
log_dir: /data/logs
```

A single codebase runs on both stations. The `role` field determines start vs. finish behavior. This keeps both Pis running identical code — deploy once, configure per-station.

### Deployment

- **Code delivery**: `rsync` from a development machine to both Pis over SSH. A simple `deploy.sh` script pushes the code directory and restarts the systemd service.
- **No git on the Pi**: The Pis don't need git installed. The development machine holds the repo; `rsync --delete` ensures a clean copy.
- **Field updates**: SSH over the Pis' WiFi (both are Pi Zero 2 W with onboard WiFi). For remote hills without WiFi, prepare an SD card image or use a phone hotspot.

### Testing Strategy

- **Unit tests**: The sync math (offset calculation, outlier filtering), message parsing/serialization, CRC-16, display formatting, and state machine transitions are all testable without hardware. Use `pytest` with mocked GPIO/SPI/I2C.
- **Integration tests**: End-to-end message exchange tests using two rfm9x instances (or mock). Verify ACK/retry, de-duplication, and state reconciliation.
- **Hardware-in-the-loop**: Manual testing with actual Pis, buttons, and beam sensors. No automated framework needed — this is a two-station system where physical interaction is the test.

## Display Formatting

The 4-digit 7-segment display with colon/decimal points supports these layouts:

| Time Range | Format | Example | Notes |
|---|---|---|---|
| 0 – 59.99s | `SS.hh` | `12.34` | Seconds + hundredths. Decimal after digit 2. |
| 1:00 – 9:59.9 | `M:SS.t` | `1:23.4` | Colon after digit 1, decimal after digit 3. Minutes + seconds + tenths. |
| 10:00+ | `MM:SS` | `12:34` | Colon between digits 2–3. Minutes + seconds (no fractional). |

- During RUNNING: display updates at ~10 Hz.
- During FINISHED: display shows final time, held steady.

## OLED Display Layout

The LoRa bonnet's built-in 128x32 OLED serves as the operator status dashboard on each station. The 128x32 resolution supports approximately 21 characters × 4 lines at a 6x8 pixel font, or 2 lines of larger text.

### Layout by State

**BOOT / SYNCING**
```
┌──────────────────────┐
│ SYNCING...     5/10  │  Sync round progress
│ offset: +1.2ms       │  Current calculated offset
│ stddev: 3.4ms        │  Not yet stable
│ ████████░░  RSSI:-45 │  Link quality bar + RSSI
└──────────────────────┘
```

**READY**
```
┌──────────────────────┐
│ ● READY        #012  │  State + race number
│ sync: 0.8ms  ▓▓▓▓▓  │  Sync quality + link bars
│ beam: S:OK F:OK      │  Both beam statuses (S=start, F=finish)
│ 12:34:56    CPU:42°  │  Clock + CPU temp
└──────────────────────┘
```

**RUNNING**
```
┌──────────────────────┐
│ ▶ RUNNING      #012  │  State + race number
│ 00:23.45             │  Elapsed time (text backup)
│ sync: 0.8ms  ▓▓▓▓▓  │  Sync quality + link bars
│ start: 12:34:56      │  Race start wall clock
└──────────────────────┘
```

**FINISHED**
```
┌──────────────────────┐
│ ■ FINISHED     #012  │  State + race number
│ >> 00:34.57 <<       │  Final time (prominent)
│ hold: 2s remaining   │  Auto-reset countdown (both stations, ~3s)
│ sync: 0.8ms  ▓▓▓▓▓  │  Sync quality + link bars
└──────────────────────┘
```

### Warning Overlays

Warnings replace the bottom line(s) when active, flashing to draw attention:

| Warning | Trigger | Display |
|---|---|---|
| `! NO LINK !` | No heartbeat for 15s | Flashing, replaces bottom line |
| `! START BEAM BLOCKED !` | Start station beam broken in READY | Replaces beam status line, shown on both stations |
| `! FINISH BEAM BLOCKED !` | Finish station beam broken in READY | Replaces beam status line, shown on both stations |
| `! SYNC POOR !` | Offset stddev > 2 ms | Replaces sync line, blocks READY |
| `! TIMEOUT !` | Race exceeded max duration | Replaces elapsed time line |
| `! NO START !` | Finish beam broke without START received | Full-screen warning |
| `! LOW BATTERY !` | Voltage below threshold (future) | Flashing, bottom line |
| `! CPU HOT !` | CPU temp > 75°C | Replaces CPU temp field |

### Design Notes

- **Font**: Use the default 6x8 Adafruit framebuf font for 4-line layout. Use a larger font (e.g., 12x16) for the final time in FINISHED state to make it more prominent.
- **Refresh rate**: Update OLED at ~2 Hz during RUNNING (enough for status; the 7-segment handles the fast timer). Update at ~1 Hz in other states.
- **Contrast**: OLED is readable in bright sunlight. No backlight concerns.
- **Burn-in**: OLED pixels can degrade with static content. Shift the display position by 1 pixel periodically, or blank the screen after extended idle.
