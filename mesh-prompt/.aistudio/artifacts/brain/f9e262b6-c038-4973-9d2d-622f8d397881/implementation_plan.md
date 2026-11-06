# Implementation Plan: Bluetooth Connection for Mesh Prompt

## Overview
Connect the Android app to the Windows laptop over Bluetooth while retaining full Wi-Fi support. The recommended and most reliable method is **Bluetooth PAN (Personal Area Network) / Bluetooth Tethering**, which enables seamless TCP/IP communication over Bluetooth without requiring unstable low-level native Bluetooth serial drivers on Windows.

---

## Why Bluetooth PAN (Tethering) is Recommended vs. RFCOMM

| Feature | Bluetooth PAN / Tethering (Recommended) | Direct Bluetooth RFCOMM (Serial) |
|---|---|---|
| **Setup Complexity** | Zero code changes to Python mesh server; standard Windows & Android feature | Requires native Windows Bluetooth socket C-extensions (often fails on Python 3.11+) |
| **Protocol Compatibility** | Full HTTP REST & WebSocket support; supports large prompt responses | Custom serial packet protocol required; prone to buffer overflows on long responses |
| **Wi-Fi Coexistence** | Seamlessly works over either Wi-Fi or Bluetooth by selecting the active IP | Separate protocol stack needed for Bluetooth vs Wi-Fi |
| **Reliability** | Native OS network driver handles reconnection and encryption | High packet loss on wireless noise |

---

## Proposed Changes

### 1. In-App Bluetooth Connection Assistant
Add a dedicated **Bluetooth Guide & Helper** in the app's Settings dialog:
- Step-by-step instructions for pairing Android and Windows via Bluetooth Tethering.
- **Quick-Fill IP Presets**:
  - Android Bluetooth tethering gateway: `http://192.168.44.1:8766`
  - Standard LAN Wi-Fi: `http://192.168.1.x:8766` or `http://192.168.9.x:8766`
- **Network Interface Indicator**: Shows whether the active connection is routing over Wi-Fi or Bluetooth.

### 2. Mesh Node Compatibility
- The existing laptop Mesh node (`config.py` / `get_local_ips()`) already detects Bluetooth PAN network adapters (`192.168.44.x` / Bluetooth PAN IP).
- Both REST (port 8766) and WebSocket (port 8765) will listen on `0.0.0.0` or the Bluetooth adapter IP.

### 3. Verification
- Verify build with `compile_applet` and local unit tests with `gradle :app:testDebugUnitTest`.

---

## User Confirmation
Click **Proceed** to implement the Bluetooth connection helper and quick-switch capabilities into the app.
