#!/usr/bin/env python3
"""Display BAT1 charge level on the GU605 Slash Lighting bar."""

import argparse
import fcntl
import logging
import math
import os
from pathlib import Path
import signal
import time

BATTERY_PATH = Path("/sys/class/power_supply/BAT1")
HIDRAW_PATH = Path("/sys/class/hidraw")
USB_VENDOR_ID = 0x0B05
USB_PRODUCT_ID = 0x193B
REPORT_ID = 0x5E
REPORT_SIZE = 128
SEGMENTS = 7
POLL_SECONDS = 10
DEFAULT_GAMMA = 2.2
MIN_ACTIVE_BRIGHTNESS = 8

# Feature report ioctls for a 128-byte Linux hidraw buffer.
HIDIOCSFEATURE = 0xC0000000 | (REPORT_SIZE << 16) | (ord("H") << 8) | 0x06
HIDIOCGFEATURE = 0xC0000000 | (REPORT_SIZE << 16) | (ord("H") << 8) | 0x07

LOG = logging.getLogger("slash-battery")
RUNNING = True


def battery_capacity():
    capacity = int((BATTERY_PATH / "capacity").read_text().strip())
    if not 0 <= capacity <= 100:
        raise ValueError(f"Battery capacity out of range: {capacity}")
    return capacity


def battery_brightness(capacity, gamma=DEFAULT_GAMMA):
    """Convert battery level to gamma-corrected LED brightness."""
    if not 0 <= capacity <= 100:
        raise ValueError("Capacity must be between 0 and 100")
    if not math.isfinite(gamma) or gamma <= 0:
        raise ValueError("Gamma must be a finite, positive number")
    if capacity == 0:
        return 0

    level = (capacity / 100) ** gamma
    return round(MIN_ACTIVE_BRIGHTNESS + (255 - MIN_ACTIVE_BRIGHTNESS) * level)


def segment_values(capacity, bottom_up=True, gamma=DEFAULT_GAMMA):
    """Fill the physical bar upward with whole LEDs at battery-scaled brightness."""
    brightness = battery_brightness(capacity, gamma)
    lit_count = capacity * SEGMENTS // 100
    if capacity > 0:
        lit_count = max(1, lit_count)

    values = [brightness] * lit_count + [0] * (SEGMENTS - lit_count)
    return values[::-1] if bottom_up else values


def matches_controller(hidraw_entry):
    try:
        properties = (hidraw_entry / "device" / "uevent").read_text().splitlines()
        hid_id = next(line.split("=", 1)[1] for line in properties if line.startswith("HID_ID="))
        _, vendor, product = hid_id.split(":")
        return int(vendor, 16) == USB_VENDOR_ID and int(product, 16) == USB_PRODUCT_ID
    except (OSError, StopIteration, ValueError):
        return False


def open_controller(device_override=None):
    if device_override:
        path = Path(device_override)
        entry = HIDRAW_PATH / path.name
        if not path.name.startswith("hidraw") or not matches_controller(entry):
            raise RuntimeError("Selected HID device does not match USB 0b05:193b")
        entries = [entry]
    else:
        entries = sorted(HIDRAW_PATH.glob("hidraw*"))

    found = False
    for entry in entries:
        if not matches_controller(entry):
            continue
        found = True
        path = Path("/dev") / entry.name
        try:
            fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        except OSError as error:
            LOG.warning("Cannot open %s: %s", path, error)
            continue

        try:
            probe = bytearray(REPORT_SIZE)
            probe[0] = REPORT_ID
            result = fcntl.ioctl(fd, HIDIOCGFEATURE, probe, True)
            if result > 0 and probe[0] == REPORT_ID:
                LOG.info("Slash controller found at %s", path)
                return fd
        except OSError as error:
            LOG.debug("%s does not accept feature report 0x5e: %s", path, error)

        os.close(fd)

    if found:
        raise RuntimeError("Found USB 0b05:193b, but no HID interface accepted feature report 0x5e")
    raise RuntimeError("Slash Lighting USB controller 0b05:193b not found")


def feature_write(fd, payload):
    if len(payload) >= REPORT_SIZE:
        raise ValueError("Slash payload is larger than the feature report")

    packet = bytearray(REPORT_SIZE)
    packet[0] = REPORT_ID
    packet[1:1 + len(payload)] = payload
    written = fcntl.ioctl(fd, HIDIOCSFEATURE, packet, True)
    if written != REPORT_SIZE:
        raise OSError(f"Incomplete Slash HID feature write: {written}/{REPORT_SIZE}")


def initialize_custom_mode(fd):
    """Select custom LED mode once for each controller connection."""
    feature_write(fd, bytes((0xD8, 0x02, 0x00, 0x01, 0x00)))
    feature_write(fd, bytes((0xD8, 0x01, 0x00, 0x01, 0x00)))
    feature_write(fd, bytes((0xD2, 0x02, 0x01, 0x08, 0xAC)))
    feature_write(fd, bytes((0xD3, 0x03, 0x01, 0x08, 0xAC, 0xFF, 0xFF, 0x01, 0x05, 0xFF, 0xFF)))
    # D4 persists the custom-mode setting. Do not send it on every update.
    feature_write(fd, bytes((0xD4, 0x00, 0x00, 0x01, 0xAC)))


def write_frame(fd, values):
    if len(values) != SEGMENTS or any(not 0 <= value <= 255 for value in values):
        raise ValueError("Slash frames require seven brightness values from 0 to 255")
    feature_write(fd, bytes((0xD3, 0x00, 0x00, SEGMENTS, *values)))


def hardware_test(stages, hold, bottom_up, gamma, device_override):
    """Display physical test frames, then restore the current battery indication."""
    fd = open_controller(device_override)
    try:
        initialize_custom_mode(fd)
        try:
            for label, values in stages:
                LOG.info("HARDWARE TEST %s | segments %s | hold %ds", label, values, hold)
                write_frame(fd, values)
                time.sleep(hold)
        finally:
            actual = battery_capacity()
            values = segment_values(actual, bottom_up, gamma)
            write_frame(fd, values)
            LOG.info("Restored BAT1 %d%% | segments %s", actual, values)
    finally:
        os.close(fd)


def shutdown_signal(_signum, _frame):
    global RUNNING
    RUNNING = False


def controller_loop(interval, bottom_up, gamma, once, device_override):
    fd = None
    last_capacity = None

    try:
        while RUNNING:
            try:
                if fd is None:
                    fd = open_controller(device_override)
                    initialize_custom_mode(fd)
                    last_capacity = None

                capacity = battery_capacity()
                values = segment_values(capacity, bottom_up, gamma)
                write_frame(fd, values)

                if last_capacity != capacity:
                    LOG.info("BAT1 %d%% | brightness %d/255 | segments %s", capacity,
                             battery_brightness(capacity, gamma), values)
                    last_capacity = capacity
                if once:
                    return
            except (OSError, ValueError, RuntimeError) as error:
                LOG.error("Cannot update Slash Lighting: %s", error)
                if fd is not None:
                    os.close(fd)
                    fd = None
                if once:
                    raise

            time.sleep(interval)
    finally:
        if fd is not None:
            os.close(fd)


def main():
    parser = argparse.ArgumentParser(description="GU605 Slash Lighting battery gauge")
    parser.add_argument("--interval", type=int, default=POLL_SECONDS, help="Battery polling interval in seconds")
    parser.add_argument("--gamma", type=float, default=DEFAULT_GAMMA,
                        help="Brightness curve (default: 2.2, larger means dimmer at partial charge)")
    direction = parser.add_mutually_exclusive_group()
    direction.add_argument("--top-down", action="store_true", help="Light from the top instead of the bottom")
    direction.add_argument("--reverse", action="store_true", help="Bottom-up fill (old flag, now the default)")
    parser.add_argument("--device", help="Override automatic /dev/hidraw device selection")
    parser.add_argument("--once", action="store_true", help="Apply the actual BAT1 level to the physical bar once")
    parser.add_argument("--hold", type=int, default=10, help="Seconds to show each hardware test frame")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--preview", type=int, metavar="PCT", help="Print simulated values without touching hardware")
    actions.add_argument("--test", type=int, metavar="PCT", help="Temporarily show a simulated level on the bar")
    actions.add_argument("--diagnose", action="store_true", help="Show physical 0%%, 30%%, and 100%% battery frames")
    actions.add_argument("--brightness-test", action="store_true",
                         help="Show all seven LEDs at 8, 64, and 255 PWM levels")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.interval < 1:
        parser.error("--interval must be at least 1 second")
    if not 1 <= args.hold <= 120:
        parser.error("--hold must be between 1 and 120 seconds")
    if not math.isfinite(args.gamma) or not 0.5 <= args.gamma <= 4.0:
        parser.error("--gamma must be between 0.5 and 4.0")
    if args.once and (args.preview is not None or args.test is not None
                      or args.diagnose or args.brightness_test):
        parser.error("--once cannot be combined with a preview or hardware test")

    for value in (args.preview, args.test):
        if value is not None and not 0 <= value <= 100:
            parser.error("Battery percentage must be between 0 and 100")

    bottom_up = not args.top_down
    if args.preview is not None:
        values = segment_values(args.preview, bottom_up, args.gamma)
        print(f"Battery: {args.preview}%")
        print(f"Brightness: {battery_brightness(args.preview, args.gamma)}/255")
        print(f"Fill: {'bottom-up' if bottom_up else 'top-down'}")
        print(f"LEDs: {values}")
        return

    signal.signal(signal.SIGTERM, shutdown_signal)
    signal.signal(signal.SIGINT, shutdown_signal)

    if args.test is not None:
        stages = [(f"BAT1 {args.test}%", segment_values(args.test, bottom_up, args.gamma))]
    elif args.diagnose:
        stages = [(f"BAT1 {pct}%", segment_values(pct, bottom_up, args.gamma))
                  for pct in (0, 30, 100)]
    elif args.brightness_test:
        stages = [(f"RAW PWM {level}/255", [level] * SEGMENTS) for level in (8, 64, 255)]
    else:
        controller_loop(args.interval, bottom_up, args.gamma, args.once, args.device)
        return

    hardware_test(stages, args.hold, bottom_up, args.gamma, args.device)


if __name__ == "__main__":
    main()
