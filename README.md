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

## One login per account, and pausing sync

MG iSMART India allows **only one active login per account**. While this integration is syncing, the MG phone app on the same account gets logged out (and logging back in on the phone ends the integration's session).

- **Best setup:** in the MG app, share the car with a **secondary user** (a different mobile number) and connect Home Assistant with that account. Your phone keeps the owner login. MG may not send charging details (power, time remaining) or allow remote commands for secondary users; battery %, range, lock state, doors, tyres and location still work.
- **Cloud sync switch:** turn **Cloud sync** off (on the device page, or **Configure → Pause cloud sync**) to stop all contact with MG – no refresh, no login, no commands. The last known values stay on the dashboard, and the pause survives restarts. Turn it back on to resume with a fresh update.

## Sync status

The **Sync status** sensor shows what the integration is doing: *Paused*, *Scheduled*, *Connecting*, *Waiting for car*, *Sending command*, *Up to date*, *Car not responding*, *Timed out*, *Rejected by MG*, *Login failed* or *Error*. Its attributes show the last attempt, last success, next refresh, refresh interval and a **message** in plain words: what is happening now, or why the last sync failed.

- While a sync or command is running, the lock, A/C and command buttons are disabled so requests are not repeated; **Cloud sync** stays usable so you can always pause.
- Every sync and command stops after the **sync timeout** (default 180 s, Configure → 60–300 s).
- If MG refuses a request outright, the integration waits 60 minutes before trying again.
- When a refresh fails, the last known values stay on the dashboard instead of turning unavailable.

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

## Dashboard cards

The integration comes with ready-made cards: a compact summary for a home dashboard, plus one card for each section of a car view. They load automatically, with no extra download or resource to add.

**Edit dashboard → Add card → search "MG car"**, then pick the one you want:

| Card | Shows |
|---|---|
| **MG car summary** | Compact card for a home dashboard: battery bar, range, doors (lock / unlock), A/C and a **Sync** button, with lock, charging and "Sync paused" badges |
| **MG car overview** | Battery gauge, range, energy in the pack, charger and charging; charging power and "Full at" only while charging |
| **MG car controls** | Cloud sync switch, sync status and details, door lock, air conditioning, Find my car (asks first) and Sync now |
| **MG car status** | Doors, windows, boot, bonnet, cabin and outside temperature |
| **MG car health** | Tyre pressures, 12 V battery, odometer |
| **MG car location** | Map of the car's last GPS position |

Each card finds the car's entities by itself, so there are no entity IDs to fill in, and it keeps working if you rename entities. Buttons and controls your car doesn't support are left out. The cards are made from Home Assistant's own tile, gauge, map and entities cards, so they follow your theme.

| Option | Card | Default |
|---|---|---|
| `device` | all | the first car |
| `title` | all | the car's name, Controls, Status, Health, Location |
| `show_details` | controls | on (the Details, Last successful sync and Next refresh rows) |
| `default_zoom` | location | 15 |
| `navigation_path` | summary | none; e.g. `/lovelace/car` opens your car view when the heading, battery or range is tapped |

**The Sync button.** While cloud sync is on, it asks the car for fresh status straight away (the same as *Refresh status*). While sync is paused, it shows a cloud-off icon. Tapping it then asks before turning cloud sync back on and syncing, because MG allows one login per account and syncing logs the phone app out. Hold the button for the sync details.

A whole Car view made of these cards: [examples/car-cards.yaml](examples/car-cards.yaml).

## Disclaimer

Unofficial and not affiliated with MG Motor India or SAIC. Remote commands are sent at your own risk; a command the car does not confirm is reported as an error and the status is re-read shortly after.

## License

MIT. The protocol library is © John Lazarus (MIT).
