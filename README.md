# ESPionage

A Pi-hole-style DNS ad blocker that runs on a cheap **ESP32-C3** dev board (4 MB flash),
plus a web flasher that installs it from your browser.

**Flash it:** [c3adblocker.pplx.app](https://c3adblocker.pplx.app) (desktop Chrome or Edge)

Point your network's DNS at the board. Domains on the blocklist get `0.0.0.0` / `::`, and
everything else is forwarded upstream (Quad9, `9.9.9.9`). The blocklist is stored as sorted
40-bit hashes in flash with a Bloom filter in RAM, so 112,000+ domains fit in about 0.7 MB
and lookups stay under a millisecond.

Based on [9M2PJU's ESP32-C3 AdBlocker](https://github.com/9m2pju/9M2PJU-ESP32-C3-AdBlocker) (MIT).

## Features

- DNS over UDP and TCP on port 53, with async upstream forwarding
- About 112k blocked domains (StevenBlack hosts + Hagezi Light), with parent-domain matching
- Custom block list of up to 200 domains, managed from the dashboard
- Per-client stats and per-IP banning
- Captive-portal Wi-Fi setup over a WPA2 setup AP
- Web dashboard at `http://c3adblock.local` (Basic Auth, CSRF token)
- Over-the-air firmware and blocklist updates, plus scheduled remote blocklist fetch
  over HTTPS with certificate verification (embedded Mozilla root bundle)
- Optional DHCP server that hands out the board as the DNS server

## Quick start

1. Open the [web flasher](https://c3adblocker.pplx.app), plug the board in over USB, and
   click **Connect → Install**. If no port shows up, hold **BOOT** while plugging in.
2. Open the flasher's console and press RST. Copy the line
   `[cfg] dashboard password: XXXXXXXXXX`.
3. Join the `C3AdBlock-Setup` Wi-Fi network using that same password, then open
   `http://192.168.4.1` and enter your home Wi-Fi.
4. Log in at `http://c3adblock.local` with user `admin` and the same password.
5. Reserve an IP for the board in your router, then set the router's DHCP DNS to that IP.
   Leave the secondary DNS empty, or clients will go around the filter.

Check it from any machine on the network:

```bash
nslookup doubleclick.net c3adblock.local   # -> 0.0.0.0 (blocked)
nslookup github.com c3adblock.local        # -> real IP (forwarded)
```

## Suggested custom domains

These aren't in the built-in lists. Add them from the dashboard. Subdomains are blocked too.

| Category | Domains |
| --- | --- |
| Windows telemetry | `vortex.data.microsoft.com`, `vortex-win.data.microsoft.com`, `settings-win.data.microsoft.com`, `oca.telemetry.microsoft.com`, `mobile.events.data.microsoft.com`, `us.tcv.telemetry.microsoft.com`, `cdn.aria.microsoft.com` |
| Roku | `track.sr.roku.com`, `amarillo.sb.roku.com`, `ravm.tv`, `roku.adsmeasurement.com` |
| Samsung / LG TV | `tvpnlogopus.samsungcloud.tv`, `lgad.cjpowercast.com.edgesuite.net` |
| Fire TV | `unagi-na.amazon.com`, `unagi-na-origin.amazon.com` |
| Vizio ACR | `api.inscape.tv` |

Re-flashing from the web flasher erases the chip, which clears the custom list.
Firmware updates through the dashboard keep it.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/main.cpp` | Firmware (DNS sinkhole, dashboard, captive portal, DHCP, OTA) |
| `src/dashboard_html.h` | Dashboard and captive-portal pages |
| `src/crt_bundle.bin` | Mozilla root CA bundle, embedded for HTTPS blocklist fetches |
| `tools/build_blocklist.py` | Downloads the source lists and builds the hashed blocklist blob |
| `tools/build_crt_bundle.py` | Builds the CA bundle from `cacert.pem` |
| `web-flasher/` | Static ESP Web Tools site (manifest + versioned binaries) |
| `release/` | Prebuilt binaries, including `full-flash.bin` (merged 4 MB image) |

## Building from source

```bash
pip install platformio
cp src/secrets.example.h src/secrets.h                 # optional: pre-fill Wi-Fi
mkdir -p data
python3 tools/build_blocklist.py data/blocklist.bin    # ~112k domains
python3 -m platformio run -t upload
python3 -m platformio run -t uploadfs
```

To refresh the CA bundle:

```bash
curl -sL https://curl.se/ca/cacert.pem -o /tmp/cacert.pem
python3 tools/build_crt_bundle.py /tmp/cacert.pem src/crt_bundle.bin
```

### Flashing from the command line

```bash
esptool.py --chip esp32c3 --port /dev/ttyACM0 --baud 460800 \
  write_flash 0x0 release/full-flash.bin
```

### Rebuilding the web flasher

The flasher files carry a revision suffix (e.g. `-r5`) so browsers can never flash a
cached old build. Bump the suffix on every release and update `manifest-rN.json` and
`index.html` to match.

```bash
R=r6
cd web-flasher && rm -f *-r*.bin manifest-r*.json
for f in bootloader partitions boot_app0 firmware; do cp ../.pio/build/c3/$f.bin $f-$R.bin; done
cp ../.pio/build/c3/littlefs.bin blocklist-fs-$R.bin
ESPTOOL=$(find ~/.platformio/packages -name esptool.py -path '*tool-esptoolpy*' | head -1)
python3 "$ESPTOOL" --chip esp32c3 merge_bin -o full-flash-$R.bin \
  --flash_mode dio --flash_size 4MB \
  0x0 bootloader-$R.bin 0x8000 partitions-$R.bin 0xe000 boot_app0-$R.bin \
  0x10000 firmware-$R.bin 0x2b0000 blocklist-fs-$R.bin
```

Flash layout (matches `partitions.csv`):

| Part | Offset |
| --- | --- |
| Bootloader | `0x0` |
| Partition table | `0x8000` |
| OTA data init (`boot_app0`) | `0xe000` |
| Firmware (app0, 1.3 MB slot) | `0x10000` |
| LittleFS blocklist | `0x2b0000` |

## Changes from upstream

- Fixed the web flasher. The upstream manifest was YAML with an `images:` key, but ESP Web
  Tools needs JSON with `builds[].parts[]`.
- Custom domains are always checked. Before, they were skipped whenever the Bloom filter missed.
- Blocking works even when no built-in blocklist is loaded.
- Fixed the hash-table offset when the Bloom filter can't be allocated.
- Blocklist updates check the new file's header before replacing the running list, so a
  bad file or URL leaves filtering on.
- HTTPS blocklist fetch works. This core's `WiFiClientSecure` refuses to connect with no
  CA set, so a root bundle is now embedded.
- DHCP replies keep the client MAC address.
- The setup AP uses WPA2, and the console logs a Wi-Fi scan as a receive check.
- Logs go to both native USB and UART0, so boards with a USB-serial bridge chip show them too.

## Troubleshooting

- **No port in the flasher:** use a data-capable USB cable, then hold BOOT while plugging in.
- **Setup AP never appears:** look for the `Wi-Fi scan: N networks visible` line in the
  console. If the board sees networks but no device can see `C3AdBlock-Setup`, the board's
  transmit side is faulty. This happens on cheap C3 boards, and a different board fixes it.
- **Linux permission denied:** add
  `SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", MODE="0666"` to `/etc/udev/rules.d/99-esp.rules`.

## License

MIT, same as upstream. See [LICENSE](LICENSE).
