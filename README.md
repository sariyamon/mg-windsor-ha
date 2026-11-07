# MG iSMART India for Home Assistant

Brings Indian-market MG cars (built and tested for the **MG Windsor EV**) into Home Assistant through the same MG iSMART India cloud service the official app uses.

The European MG / SAIC integrations do not work in India: MG India runs its own service with a different login (mobile number) and a binary data protocol. This integration is built on the open-source [`mg-ismart-india-client`](https://github.com/john-lazarus/mg-ismart-india-client) library (MIT), which speaks that protocol.

## What you get

| Type | Entities |
|---|---|
| Battery & charging | Battery %, range, charging (on/off), charger plugged in, charging power, time remaining, charging finishes at, battery energy (kWh), distance and energy since last charge |
| Car | Doors, windows, boot, bonnet, lights, air conditioning running, odometer, interior/exterior temperature, 12 V battery, four tyre pressures (PSI), last update time |
| Location | Device tracker from the car's GPS |
| Controls (need the app PIN) | Door lock, air conditioning switch, Find my car, Open tailgate, Close windows (when the car supports them), Refresh status |

## Install

1. In Home Assistant open **Settings → Marketplace** (HACS on 2026.10 and older) → **⋮ → Add from link** and paste this repository's URL, type **Integration**.
2. Install **MG iSMART India** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → MG iSMART India**.
4. Enter your MG app **mobile number** and **password**. Add your **4-digit app PIN** if you want the lock, air conditioning and other controls.

### Notes

- **Two-step login (OTP) must be off** on the MG account.
- MG India limits logins per day. The integration logs in once and reuses the session; a rejected password is never retried automatically — Home Assistant asks you to sign in again instead.
- Your PIN is never stored, only its hash (as the MG app does).
- See **Refresh interval and 12 V battery** below before changing the refresh settings.
- Charging details appear only when the car sends a charging frame (plugged in, or recently charged); otherwise battery % comes from the main status.
- Shared (secondary) MG accounts may not receive charging data — MG restricts it to the owner account.

## Refresh interval and 12 V battery

> **Please use the recommended intervals.** Every refresh makes MG's server wake the car's telematics unit (T-Box), which runs from the small **12 V battery**, not the main traction battery. Refreshing a parked car too often can drain the 12 V battery and leave the car unable to start.

| Car state | Recommended | Allowed |
|---|---|---|
| Parked | **30 min** (60 min if parked for days) | 15–240 min |
| Charging or A/C on | **10 min** | 5–60 min |

How the integration protects the battery automatically:

- **Adaptive refresh** – it refreshes quickly only while the car is charging or the A/C is running (the car is awake anyway), and slows down again once parked.
- **12 V battery saver** – if the 12 V battery reads below **12.2 V** while parked, refresh slows to **every 2 hours** until it recovers, and a warning is written to the log.
- **Safe minimums** – intervals below 15 min (parked) or 5 min (active) are not accepted.
- The **Refresh status** button asks for fresh data on demand, so there is no need for a short interval just to check the car occasionally.

Change the intervals under **Settings → Devices & services → MG iSMART India → Configure**.

## Disclaimer

Unofficial and not affiliated with MG Motor India or SAIC. Remote commands are sent at your own risk; a command the car does not confirm is reported as an error and the status is re-read shortly after.

## License

MIT. The protocol library is © John Lazarus (MIT).
