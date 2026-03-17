# Read-Only Root Filesystem + Writable /data Partition

This guide configures the Raspberry Pi Zero 2 W with a read-only root filesystem using overlayfs and a dedicated writable `/data` partition for race logs and configuration. This protects the OS from SD card corruption on sudden power loss (dead battery, unplugged cable).

## How It Works

- The **root partition** is mounted read-only with a RAM-backed overlay (`overlayfs`). All OS writes go to RAM and are discarded on reboot. The SD card's root filesystem is never modified during normal operation.
- A separate **`/data` partition** (ext4, mounted with `sync`) stores everything that must persist: race logs, `config.yaml`, and debug logs.
- Writes to `/data` are small and infrequent (one CSV row per race, config changes). Each write is followed by `fsync` in the application code.

## Prerequisites

- Raspberry Pi OS Bullseye or Bookworm (Lite recommended) flashed to the SD card
- SSH access to the Pi
- The SD card has free unpartitioned space (or you're willing to shrink the root partition)

## Step 1: Create the /data Partition

Before enabling the read-only overlay, create a dedicated partition for persistent data.

### Option A: During Initial SD Card Setup (Recommended)

After flashing Raspberry Pi OS, the SD card typically has two partitions:
- Partition 1: `/boot/firmware` (FAT32, ~512 MB)
- Partition 2: `/` root (ext4, expands to fill the card)

Shrink the root partition and create a third partition:

```bash
# On the Pi (or from another Linux machine with the SD card inserted)
# First, check current layout
sudo lsblk
sudo fdisk -l /dev/mmcblk0
```

If the root partition has already expanded to fill the card, shrink it first:

```bash
# Resize the root filesystem (e.g., to 4 GB — adjust as needed)
# IMPORTANT: Do this from another machine or a USB-booted Pi, NOT while running from the SD card
sudo e2fsck -f /dev/mmcblk0p2
sudo resize2fs /dev/mmcblk0p2 4G
```

Then use `fdisk` or `parted` to delete and recreate partition 2 at the smaller size, and create partition 3 with the remaining space:

```bash
sudo fdisk /dev/mmcblk0
# d → 2 (delete root partition entry)
# n → p → 2 → (same start sector) → +4G (recreate at smaller size)
# n → p → 3 → (default start) → (default end, use remaining space)
# w (write and exit)

# Format the new data partition
sudo mkfs.ext4 -L data /dev/mmcblk0p3
```

### Option B: On a Running Pi (if free space exists)

If you reserved space during flashing or the root partition hasn't expanded:

```bash
# Create partition 3 in the free space
sudo fdisk /dev/mmcblk0
# n → p → 3 → (default start) → (default end)
# w

# Format it
sudo mkfs.ext4 -L data /dev/mmcblk0p3
```

## Step 2: Mount /data on Boot

Add the `/data` partition to `/etc/fstab`:

```bash
# Create the mount point
sudo mkdir -p /data

# Get the partition UUID
sudo blkid /dev/mmcblk0p3
# Note the UUID value, e.g., UUID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Add to fstab (use the UUID from above)
echo 'UUID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  /data  ext4  defaults,sync,noatime  0  2' | sudo tee -a /etc/fstab

# Mount it now
sudo mount /data
```

**Mount options explained:**
- `sync` — writes are committed to the SD card immediately (no write-back cache). Slower, but safer against power loss.
- `noatime` — don't update access timestamps on reads. Reduces unnecessary writes.

## Step 3: Set Up the /data Directory Structure

```bash
sudo mkdir -p /data/logs
sudo mkdir -p /data/config

# Set ownership so the application can write without root
sudo chown -R pi:pi /data

# Create a default config.yaml (adjust role per station)
cat > /data/config/config.yaml << 'EOF'
role: start  # Change to "finish" on the finish station
hold_period_s: 3
display_hold_s: 15
race_timeout_s: 300
sync_interval_s: 30
heartbeat_interval_s: 5
beam_debounce_ms: 500
sync_threshold_stddev_ms: 2
link_lost_timeout_s: 15
display_brightness: 12
ack_timeout_ms: 200
ack_retries: 5
lora_spreading_factor: 7
lora_tx_power: 20
log_dir: /data/logs
EOF
```

### Directory Layout

```
/data/
├── config/
│   └── config.yaml       # Station configuration (role, tuning parameters)
└── logs/
    ├── races_2026-03-10.csv   # Daily race results (one file per day)
    ├── debug.log              # Current debug log
    ├── debug.log.1            # Rotated debug logs (10 MB × 5 files max)
    ├── debug.log.2
    └── ...
```

## Step 4: Enable Read-Only Root Filesystem

Raspberry Pi OS has built-in overlayfs support via `raspi-config`.

### Using raspi-config

```bash
sudo raspi-config
```

Navigate to: **Performance Options** → **Overlay File System**

1. "Would you like the overlay file system to be enabled?" → **Yes**
2. "Would you like the boot partition to be write-protected?" → **Yes**

Reboot when prompted:

```bash
sudo reboot
```

### Verify After Reboot

```bash
# Root should show as an overlay
mount | grep ' / '
# Expected: overlay on / type overlay (...)

# /data should be writable ext4
mount | grep /data
# Expected: /dev/mmcblk0p3 on /data type ext4 (rw,sync,noatime)

# Test: writing to root should succeed (goes to RAM) but not persist
touch /tmp/test_file  # Works (RAM overlay)

# Test: writing to /data should persist across reboots
echo "test" > /data/test.txt
cat /data/test.txt  # Should show "test"
sudo reboot
# After reboot:
cat /data/test.txt  # Should still show "test"
```

## Step 5: Verify Application Paths

The application must read/write exclusively from `/data` for anything that needs to persist. Confirm these paths in `config.yaml`:

| What | Path | Persists? |
|---|---|---|
| Application code | `/home/pi/ski-race-timer/` (or wherever rsync deploys) | No — lives on read-only root, re-deployed via rsync |
| Configuration | `/data/config/config.yaml` | Yes |
| Race logs (CSV) | `/data/logs/races_YYYY-MM-DD.csv` | Yes |
| Debug logs | `/data/logs/debug.log` (+ rotated) | Yes |
| Python venv | `/home/pi/ski-race-timer/venv/` | No — recreated on deploy if needed |
| systemd service | `/etc/systemd/system/ski-timer.service` | No — baked into the OS image |

Since the root is read-only, installing packages or modifying system files requires temporarily disabling the overlay (see Maintenance section below).

## Maintenance

### Temporarily Disabling the Overlay (for system updates)

To install packages, update the OS, or modify system files:

```bash
sudo raspi-config
# Performance Options → Overlay File System → Disable
sudo reboot

# Now the root is writable — make your changes
sudo apt update && sudo apt upgrade -y
# Install any new packages, edit system files, etc.

# Re-enable the overlay when done
sudo raspi-config
# Performance Options → Overlay File System → Enable
sudo reboot
```

### Deploying Application Code

Application code lives on the read-only root, but `rsync` deployment works because the overlay accepts writes (they just go to RAM). To make deployed code persist across reboots:

1. Disable overlay → deploy → re-enable overlay, **or**
2. Deploy to `/data/app/` instead (always writable), and point the systemd service there.

**Option 2 is recommended** for field updates — it avoids toggling the overlay:

```bash
# On the development machine:
rsync -avz --delete ./src/ pi@<pi-ip>:/data/app/
ssh pi@<pi-ip> "sudo systemctl restart ski-timer"
```

### Checking Disk Usage

```bash
# /data partition usage
df -h /data

# Log directory size
du -sh /data/logs/
```

Debug logs are capped at 50 MB total (5 × 10 MB files via `RotatingFileHandler`). Race CSV files are a few KB per day. Disk usage should not be a concern.

### Recovering from Corruption

If the `/data` partition becomes corrupted (e.g., repeated hard power-offs at unlucky moments):

```bash
# Boot the Pi — root overlay will work fine regardless
# Check /data filesystem
sudo fsck /dev/mmcblk0p3

# If fsck can't repair, reformat (DESTROYS ALL DATA)
sudo umount /data
sudo mkfs.ext4 -L data /dev/mmcblk0p3
sudo mount /data
sudo mkdir -p /data/logs /data/config
sudo chown -R pi:pi /data
# Re-create config.yaml (see Step 3)
```

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `mount: /data: can't find in /etc/fstab` | fstab entry lost after overlay enabled | Disable overlay, add fstab entry, re-enable |
| `/data` is read-only after reboot | Wrong partition or mount options | Check `blkid`, verify UUID in fstab matches partition 3 |
| Overlay not active after reboot | `raspi-config` overlay setting didn't persist | Re-run `raspi-config` and enable again |
| `No space left on device` on /data | Logs filled the partition | Check `du -sh /data/logs/*`, delete old debug logs. Verify `RotatingFileHandler` is configured correctly in the application. |
| Can't SSH after enabling overlay | SSH host keys regenerate each boot (go to RAM) | Pre-generate keys before enabling overlay, or accept the new key each time |
| `apt install` fails | Root is read-only | Disable overlay, install, re-enable (see Maintenance) |
| WiFi won't connect | `wpa_supplicant.conf` changes don't persist | Configure WiFi before enabling overlay |

## Notes

- **Boot time**: Overlayfs adds negligible boot overhead. The system is operational within ~15 seconds of power-on.
- **RAM usage**: The overlay consumes RAM for writes. On a Pi Zero 2 W (512 MB RAM), the typical overhead is minimal since the system doesn't write much to root during operation.
- **Graceful shutdown**: The application supports a clean shutdown via holding the green + red buttons for 3 seconds, which triggers `sudo shutdown -h now`. Always prefer this over pulling power, especially to protect the `/data` partition.
