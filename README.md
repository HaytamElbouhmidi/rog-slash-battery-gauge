# ROG Slash Battery Gauge

A battery indicator for the ASUS ROG Zephyrus G16 Slash Lighting bar on Linux.

I use the seven white LEDs on the back of the display as a battery gauge. The bar fills **from bottom to top**, and the illuminated segments gradually get brighter as battery capacity increases. At 100%, all seven segments are on at the maximum output of 255/255.

The controller sends a steady, custom LED frame every 10 seconds. There are no blinking warnings, charging animations, online services, or third-party Python dependencies.

## Features

- Bottom-to-top battery fill with seven independently controlled LED segments
- Gamma-corrected brightness, with maximum brightness at 100%
- Same battery-level indication when charging and discharging
- Automatic controller detection over Linux `hidraw`
- Background systemd service with a sleep/resume recovery hook
- Simulated previews that do not access the hardware
- Physical fill and brightness diagnostics
- Configurable brightness curve, fill direction, and refresh interval
- Unit tests that run without an ASUS laptop

## Requirements

### Hardware

| Component | Requirement |
| --- | --- |
| Laptop | Tested on ASUS ROG Zephyrus G16 **GU605MY** (GU605 family, 2024 Intel model) |
| Slash Lighting | Seven-segment white LED bar on the back of the display |
| USB HID controller | Vendor ID `0b05`, product ID `193b` |
| HID protocol | Feature report ID `0x5E`, 128-byte report, custom per-segment frame support |
| Battery | Capacity exposed at `/sys/class/power_supply/BAT1/capacity` |

**Compatibility scope:** This is a seven-LED implementation for the `0b05:193b` controller. It has not been validated on other ASUS models. Controllers using `0b05:19b6`, report ID `0x5D`, or a 35-LED layout are not supported by the current device detection and packet settings.

### Software

| Component | Requirement |
| --- | --- |
| Operating system | Linux, tested on CachyOS (Arch-based) |
| Python | Python 3.10 or newer |
| Init system | systemd for automatic operation |
| Kernel interface | Working Linux `hidraw` devices in `/dev` and `/sys/class/hidraw` |
| Device permissions | Root access with `sudo` for the standard installation |
| Install script | Bash and standard system tools (`systemctl`, `install`, `cp`) |
| Python packages | None beyond the standard library |
| Optional utilities | `usbutils` for `lsusb`, `git` for cloning, `unzip` for ZIP downloads |

There is no GPU requirement. The project does not require `pyusb`, `hidapi`, `pip`, an internet connection, or a graphical desktop.

`asusctl` and `asusd` are **not required to send custom frames**. If already installed, they can coexist, but any software changing Slash Lighting settings may override the custom LED mode. Do not disable `asusd` unless you have identified a specific conflict, as it manages other ASUS laptop functions.

On CachyOS or Arch Linux, install any missing convenience tools with:

```bash
sudo pacman -S --needed python git unzip usbutils
```

### Firmware and BIOS

The controller firmware must accept custom Slash Lighting HID frames on report `0x5E`, including the custom mode configuration and `D3` frame writes. This has been confirmed on my GU605MY through physical fill and brightness tests.

- **Minimum BIOS version:** Not established.
- **Minimum embedded-controller or Slash firmware version:** Not established.
- **Firmware update required:** None known for a device that already passes the hardware tests.
- **Firmware flashing:** Not included. This program does not install or replace BIOS or controller firmware.

The custom-mode initialization does persist a configuration record to the Slash controller's flash memory. It happens when the controller is opened or reconnected, **not every 10-second update**. Avoid deliberately restarting the service or hardware tests in a tight loop.

Custom LED frames require the operating system to be running. Sleep, boot, and shutdown lighting are controlled by the laptop's firmware and are outside this program's live battery gauge.

## Confirm compatibility before installation

First, check that the battery reports a capacity:

```bash
cat /sys/class/power_supply/BAT1/capacity
```

The result should be an integer from `0` to `100`. If the file is missing, the script will not work without changing its hardcoded battery path.

Then check for the USB controller:

```bash
lsusb -d 0b05:193b
```

`lsusb` is only a convenience check. The program also verifies the matching Linux HID collection and feature report before sending commands, because a single USB device can expose more than one HID interface. The `/dev/hidraw` device number can change between boots.

## Installation

### Step 1. Get the source

Clone the repository:

```bash
git clone https://github.com/<YOUR_GITHUB_USERNAME>/rog-slash-battery-gauge.git
cd rog-slash-battery-gauge
```

Or download the repository as a ZIP from GitHub, extract it, and open a terminal in the extracted folder.

### Step 2. Preview the mapping without accessing the LEDs

```bash
python3 slash-battery.py --preview 30
```

Expected output:

```text
Battery: 30%
Brightness: 25/255
Fill: bottom-up
LEDs: [0, 0, 0, 0, 0, 25, 25]
```

`--preview` only prints calculated LED values. It does not modify the hardware. LED arrays are listed from the **physical top** to the **physical bottom** of the bar.

### Step 3. Stop any older Slash Battery Gauge installation

If an earlier version is running, stop it before testing the new controller:

```bash
sudo systemctl stop slash-battery.service
```

The installation script in the next step also disables the old one-minute `slash-battery.timer`, if present. It leaves any previous Bash script in place and creates timestamped backups of existing files before replacing them.

### Step 4. Install the controller and systemd files

Run the installer from the repository folder:

```bash
sudo bash scripts/install.sh
```

The script installs:

| Repository file | Installed location |
| --- | --- |
| `slash-battery.py` | `/usr/local/bin/slash-battery.py` |
| `systemd/slash-battery.service` | `/etc/systemd/system/slash-battery.service` |
| `systemd/slash-battery-resume` | `/etc/systemd/system-sleep/slash-battery` |

It reloads systemd but **does not start the service**. This leaves the lighting controller available for the next two hardware checks without background updates interfering.

If you prefer manual installation, the commands are:

```bash
sudo systemctl stop slash-battery.service
sudo systemctl disable --now slash-battery.timer 2>/dev/null || true
sudo install -D -m 755 slash-battery.py /usr/local/bin/slash-battery.py
sudo install -D -m 644 systemd/slash-battery.service /etc/systemd/system/slash-battery.service
sudo install -D -m 755 systemd/slash-battery-resume /etc/systemd/system-sleep/slash-battery
sudo systemctl daemon-reload
```

The manual commands do not create backups. Use the installer if an existing installation needs to be preserved.

### Step 5. Test the bottom-to-top fill on the physical bar

```bash
sudo python3 /usr/local/bin/slash-battery.py --test 30 --hold 10
```

The **bottom two segments** should light for 10 seconds while the remaining five stay off. The controller then restores the actual battery level.

To verify the entire range:

```bash
sudo python3 /usr/local/bin/slash-battery.py --diagnose --hold 10
```

This displays the 0%, 30%, and 100% patterns in sequence, holding each one for 10 seconds, then restores the actual battery level.

### Step 6. Test brightness independently of fill

```bash
sudo python3 /usr/local/bin/slash-battery.py --brightness-test --hold 10
```

All seven segments remain illuminated during this test. Their PWM values change through **8/255**, **64/255**, and **255/255**. Each stage lasts 10 seconds. Only brightness should change, not the filled length.

If the segments do not dim during this test, do not enable the background service yet. Check the troubleshooting section first.

### Step 7. Enable automatic monitoring

After both hardware tests succeed:

```bash
sudo systemctl enable --now slash-battery.service
```

Verify that the service is running:

```bash
systemctl status slash-battery.service --no-pager
```

View live output:

```bash
journalctl -u slash-battery.service -f
```

The script reads `BAT1` and sends a steady LED frame every 10 seconds. It logs the current battery percentage and LED values whenever the percentage changes.

### Step 8. Verify recovery after sleep

Suspend the laptop normally, resume it, and check the bar. The installed systemd sleep hook restarts the active service after resume so that it can reacquire the USB controller.

```bash
systemctl status slash-battery.service --no-pager
journalctl -u slash-battery.service -n 25 --no-pager
```

## Battery fill and brightness

A segment is either off or set to the current battery-scaled brightness. The fill is quantized into seven full segments rather than using a partially filled LED, so the seventh segment does not illuminate until 100%.

The default brightness curve is:

```text
brightness = round(8 + (255 - 8) * (capacity / 100) ** 2.2)
```

At 0%, brightness is forced to 0. At any positive capacity, at least one segment stays active. The 8/255 minimum keeps low-charge indications visible. The curve is applied equally on AC and battery power.

| Battery | Filled segments | Brightness per active segment | LED values, top to bottom |
| ---: | ---: | ---: | --- |
| 0% | 0 / 7 | 0 / 255 | `[0, 0, 0, 0, 0, 0, 0]` |
| 10% | 1 / 7 | 10 / 255 | `[0, 0, 0, 0, 0, 0, 10]` |
| 30% | 2 / 7 | 25 / 255 | `[0, 0, 0, 0, 0, 25, 25]` |
| 50% | 3 / 7 | 62 / 255 | `[0, 0, 0, 0, 62, 62, 62]` |
| 70% | 4 / 7 | 121 / 255 | `[0, 0, 0, 121, 121, 121, 121]` |
| 90% | 6 / 7 | 204 / 255 | `[0, 204, 204, 204, 204, 204, 204]` |
| 100% | 7 / 7 | 255 / 255 | `[255, 255, 255, 255, 255, 255, 255]` |

## Configuration

The default settings are a 10-second interval, bottom-to-top fill, and gamma `2.2`.

| Option | Behavior |
| --- | --- |
| `--preview 30` | Calculate a simulated 30% LED frame without hardware access |
| `--test 30 --hold 10` | Show 30% on the physical LEDs for 10 seconds |
| `--diagnose --hold 10` | Show physical 0%, 30%, and 100% test frames |
| `--brightness-test --hold 10` | Show fixed PWM levels of 8, 64, and 255 on all LEDs |
| `--once` | Apply the actual battery level one time |
| `--interval 10` | Poll and write a frame every 10 seconds during normal operation |
| `--gamma 3.0` | Keep the LEDs dimmer at mid-charge levels |
| `--top-down` | Reverse the fill direction to top-to-bottom |
| `--reverse` | Legacy alias for bottom-to-top, which is already the default |
| `--device /dev/hidraw3` | Select one matching HID interface instead of autodetection |

A lower gamma value makes the bar brighter earlier in the battery range. A higher value keeps it dimmer. Supported gamma values are `0.5` through `4.0`.

For a permanent change, create a systemd override:

```bash
sudo systemctl edit slash-battery.service
```

Example override for gamma `3.0` and a 15-second interval:

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /usr/local/bin/slash-battery.py --interval 15 --gamma 3.0
```

Apply the change:

```bash
sudo systemctl daemon-reload
sudo systemctl restart slash-battery.service
```

To return to the repository defaults, remove the override with `sudo systemctl revert slash-battery.service`, then reload and restart the service.

## Updating an existing installation

When updating from an older version, download or clone the latest repository contents, then run:

```bash
sudo bash scripts/install.sh
```

The installer stops the service, disables the old timer if one exists, and backs up the previous controller, service, and resume hook with timestamped suffixes. Run the hardware tests again, then re-enable the service.

Note that a custom systemd override created with `systemctl edit` is not removed by the installer. Check it with:

```bash
systemctl cat slash-battery.service
```

## Troubleshooting

### The bar stays fully illuminated

Confirm that the preview is not being confused with the physical test:

```bash
python3 /usr/local/bin/slash-battery.py --preview 30
sudo systemctl stop slash-battery.service
sudo python3 /usr/local/bin/slash-battery.py --test 30 --hold 10
```

`--preview` cannot change the physical LEDs. Also confirm that another program is not applying a preset animation after the custom frame is sent.

### The bar fills in the wrong direction

Bottom-to-top is the default. Remove `--top-down` from any service override, then restart the service. The 30% test should illuminate the bottom two segments.

### Brightness does not change

Stop the background service and run:

```bash
sudo python3 /usr/local/bin/slash-battery.py --brightness-test --hold 10
```

All seven segments should stay on while getting brighter through 8, 64, and 255. If they do not, check for competing Slash settings and confirm the firmware accepts custom per-segment values.

### The controller is not found

```bash
lsusb -d 0b05:193b
ls -l /dev/hidraw*
sudo python3 /usr/local/bin/slash-battery.py --once
```

Make sure the machine has the expected `0b05:193b` USB controller. Other hardware IDs and different report IDs are not covered by this implementation. Do not assume that a specific `/dev/hidrawN` number will remain the same after a reboot.

### Permission denied on `/dev/hidrawN`

Hardware tests and the system service need permission to open the HID interface for reading and writing. Use `sudo` for one-shot and diagnostic commands. The systemd service runs as root by default. Do not grant world-writable permissions to all `hidraw` devices.

### `BAT1` is missing

```bash
ls /sys/class/power_supply/
```

The current script expects `BAT1`, not `BAT0`. If the correct battery is exposed at a different name, update `BATTERY_PATH` in `slash-battery.py` and reinstall it.

### The bar resets after suspend or another utility changes it

```bash
systemctl status slash-battery.service --no-pager
journalctl -u slash-battery.service -n 50 --no-pager
```

Check that the resume hook is installed at `/etc/systemd/system-sleep/slash-battery`. Other applications, including `asusctl`/`asusd` settings changes, can take control of the same Slash firmware. Live custom frames cannot run while the laptop is suspended.

For additional ASUS diagnostics, if `asusctl` is installed:

```bash
asusctl slash get
```

## Uninstalling

From the repository folder:

```bash
sudo bash scripts/uninstall.sh
```

This disables the service and removes the installed Python controller, service unit, and resume hook. Existing timestamped backups, previous Bash scripts, and older timer units are not deleted. The installer does not modify BIOS firmware, and uninstalling does not automatically restore the controller's previous stored Slash animation.

If `asusctl` is installed, select a firmware-controlled mode after uninstalling:

```bash
asusctl slash set --enable --mode Static
```

The exact lighting behavior after uninstalling depends on the saved firmware settings.

## Tests

Run the hardware-independent unit tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The tests verify brightness math, monotonic LED values, bottom-to-top and top-to-bottom fill, feature frame encoding, and restoration of the actual battery level after a physical test. GitHub Actions runs the test suite against multiple Python versions.

## Repository layout

```text
rog-slash-battery-gauge/
├── .github/workflows/tests.yml
├── .gitignore
├── LICENSE
├── README.md
├── scripts/
│   ├── install.sh
│   └── uninstall.sh
├── slash-battery.py
├── systemd/
│   ├── slash-battery-resume
│   └── slash-battery.service
└── tests/
    └── test_slash_battery.py
```

## Protocol references and credit

The HID protocol and custom frame format are based on published reverse-engineering work. I use that protocol to implement a Linux battery-level gauge for the seven-LED GU605 controller.

- [Slashlight protocol documentation](https://github.com/gouthamk16/slashlight/blob/main/docs/PROTOCOL.md)
- [G-Helper Slash Lighting implementation](https://github.com/seerge/g-helper/blob/main/app/AnimeMatrix/SlashDevice.cs)
- [asusctl Slash Lighting controls](https://github.com/OpenGamingCollective/asusctl/blob/main/docs/usage/asusctl.md)
- [Linux kernel hidraw interface documentation](https://docs.kernel.org/hid/hidraw.html)

This project is independent of ASUS, Slashlight, G-Helper, and asusctl.

## License

MIT. See [LICENSE](LICENSE).
