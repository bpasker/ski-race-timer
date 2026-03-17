"""Beam-break timer for 7-segment display.

Uses gpiod (Linux GPIO character device) for interrupt-based edge detection.
No polling — the kernel wakes us on falling edges, giving sub-millisecond
latency and zero CPU usage while idle.

States:
  READY    → display shows 0.00, waiting for beam break to start
  RUNNING  → timer counting up, beam break stops it
  FINISHED → final time displayed, beam break resets to READY
"""

import time
from datetime import timedelta

import board
import busio
import gpiod
from gpiod.line import Direction, Bias, Edge
from adafruit_ht16k33.segments import Seg7x4

# --- Config ---
GPIOCHIP = "/dev/gpiochip0"
BEAM_GPIO = 17
DEBOUNCE_S = 0
DISPLAY_HZ = 20  # display refresh rate during RUNNING

# --- Hardware init ---
i2c = busio.I2C(board.SCL, board.SDA)
display = Seg7x4(i2c)
display.brightness = 0.8

beam_request = gpiod.request_lines(
    GPIOCHIP,
    consumer="beam-timer",
    config={
        BEAM_GPIO: gpiod.LineSettings(
            direction=Direction.INPUT,
            bias=Bias.PULL_UP,
            edge_detection=Edge.FALLING,
            debounce_period=timedelta(microseconds=5000),
        )
    },
)

# --- State ---
state = "READY"        # READY | RUNNING | FINISHED
start_time = 0.0
final_elapsed = 0.0
last_break_time = 0.0

# How long to block waiting for edge events (controls display refresh rate)
POLL_TIMEOUT = timedelta(milliseconds=1000 // DISPLAY_HZ)


def format_display(elapsed):
    """Update 7-segment display with elapsed time."""
    try:
        if elapsed < 60:
            display.colon = False
            display.print("{:5.2f}".format(elapsed))
        else:
            m = int(elapsed) // 60
            s = int(elapsed) % 60
            display.print("{:02d}:{:02d}".format(m, s))
    except OSError:
        pass


def handle_beam_break():
    """Process a debounced beam break event. Returns new state."""
    global state, start_time, final_elapsed, last_break_time

    now = time.monotonic()
    if (now - last_break_time) < DEBOUNCE_S:
        return
    last_break_time = now

    if state == "READY":
        start_time = now
        state = "RUNNING"
        print("STARTED")
    elif state == "RUNNING":
        final_elapsed = now - start_time
        state = "FINISHED"
        print("FINISHED: {:.2f}s".format(final_elapsed))
    elif state == "FINISHED":
        state = "READY"
        print("RESET")


# --- Main loop ---
print("Beam timer ready (gpiod edge-detect). Break beam to start.")
try:
    format_display(0.0)

    while True:
        # Block until edge event OR timeout (for display refresh)
        if beam_request.wait_edge_events(POLL_TIMEOUT):
            events = beam_request.read_edge_events()
            for _ in events:
                handle_beam_break()

        # Update display
        if state == "READY":
            format_display(0.0)
        elif state == "RUNNING":
            format_display(time.monotonic() - start_time)
        elif state == "FINISHED":
            format_display(final_elapsed)

except KeyboardInterrupt:
    pass
finally:
    display.fill(0)
    beam_request.release()
