/*
 * MG iSMART India dashboard cards.
 *
 * Ready-made cards, one per section of a car view:
 *   custom:mg-car-summary-card    compact: battery, range, doors, A/C and a Sync button
 *   custom:mg-car-overview-card   battery gauge, range, energy, charger and charging
 *   custom:mg-car-controls-card   cloud sync, sync details, lock, air conditioning, find my car, refresh
 *   custom:mg-car-status-card     doors, windows, boot, bonnet, cabin and outside temperature
 *   custom:mg-car-health-card     tyre pressures, 12 V battery, odometer
 *   custom:mg-car-location-card   map of the car's last GPS fix
 *
 * Each card finds its own entities through the integration (renamed entity IDs keep
 * working) and is built from Home Assistant's own cards, so it follows your theme.
 * Pick them from "Add card" -> "MG car ..."; no YAML needed.
 */

const VERSION = "1.6.0";
const DOMAIN = "mg_ismart_india";
const DOCS = "https://github.com/sariyamon/mg-windsor-ha#dashboard-cards";

/* ---------- finding the car's entities ---------- */

let devicesPromise = null;

function loadDevices(hass, refresh = false) {
  if (!devicesPromise || refresh) {
    devicesPromise = hass
      .callWS({ type: `${DOMAIN}/devices` })
      .then((r) => r.devices || [])
      .catch((err) => {
        devicesPromise = null;
        throw err;
      });
  }
  return devicesPromise;
}

async function findDevice(hass, deviceId) {
  const pick = (list) =>
    (deviceId ? list.find((d) => d.device_id === deviceId) : list.find((d) => Object.keys(d.entities).length)) ||
    null;
  let device = pick(await loadDevices(hass));
  if (!device) device = pick(await loadDevices(hass, true)); // added since the page loaded
  return device;
}

/* ---------- small builders ---------- */

const tile = (entity, name, icon, color, extra = {}) => ({
  type: "tile",
  entity,
  ...(name ? { name } : {}),
  ...(icon ? { icon } : {}),
  ...(color ? { color } : {}),
  ...extra,
});

const heading = (text, icon, badges) => ({
  type: "heading",
  heading: text,
  heading_style: "title",
  icon,
  ...(badges && badges.length ? { badges } : {}),
});

const grid = (columns, cards) => ({ type: "grid", columns, square: false, cards });

const when = (entity, on, card) => ({
  type: "conditional",
  conditions: [on ? { condition: "state", entity, state: "on" } : { condition: "state", entity, state_not: "on" }],
  card,
});

/** Tiles that exist on this car, in order: [key, name, icon, color, extra]. */
function tiles(e, rows) {
  return rows.filter(([key]) => e[key]).map(([key, name, icon, color, extra]) => tile(e[key], name, icon, color, extra));
}

/* ---------- the cards ---------- */

const press = (entity, confirm) => ({
  action: "perform-action",
  perform_action: "button.press",
  target: { entity_id: entity },
  ...(confirm ? { confirmation: { text: confirm } } : {}),
});

const half = { grid_options: { columns: 6 } };

/**
 * One Sync button for both states of cloud sync:
 * running -> asks the car for fresh status now;
 * paused  -> syncs this one time (asks first: it logs the MG phone app out) and
 *            leaves cloud sync off afterwards.
 */
function syncTiles(e, name = "Sync") {
  if (!e.refresh) return [];
  const info = { action: "more-info", entity: e.sync_status || e.refresh };
  const running = tile(e.sync_status || e.refresh, name, "mdi:sync", "blue", { tap_action: press(e.refresh), hold_action: info });
  if (!e.cloud_sync) return [running];
  const once = tile(e.sync_status || e.refresh, name, "mdi:cloud-download-outline", "grey", {
    tap_action: press(
      e.refresh,
      "Sync once now? Cloud sync stays off afterwards. MG allows one login, so this logs the phone app out."
    ),
    hold_action: info,
  });
  return [when(e.cloud_sync, false, once), when(e.cloud_sync, true, running)];
}

const CARDS = {
  "mg-car-summary-card": {
    name: "MG car summary",
    description: "Compact: battery, range, doors, A/C and a Sync button, with lock and charging badges.",
    schema: [
      { name: "title", selector: { text: {} } },
      { name: "navigation_path", selector: { text: {} } },
    ],
    build(config, e, device) {
      const go = config.navigation_path ? { action: "navigate", navigation_path: config.navigation_path } : null;
      const badges = [];
      if (e.cloud_sync)
        badges.push({
          type: "entity", entity: e.cloud_sync, name: "Sync paused", show_name: true, show_state: false, show_icon: true, color: "grey",
          visibility: [{ condition: "state", entity: e.cloud_sync, state: "off" }],
        });
      if (e.door_lock) badges.push({ type: "entity", entity: e.door_lock, show_state: true, show_icon: true });
      if (e.charging)
        badges.push({
          type: "entity", entity: e.charging, show_state: true, show_icon: true, color: "green",
          visibility: [{ condition: "state", entity: e.charging, state: "on" }],
        });
      const head = heading(config.title || device.name, "mdi:car-electric", badges);
      if (go) head.tap_action = go;
      const nav = go ? { tap_action: go } : {};
      return [
        head,
        grid(2, [
          ...tiles(e, [
            ["battery", "Battery", null, "green", { ...nav, features: [{ type: "bar-gauge", min: 0, max: 100 }] }],
            ["range", "Range", null, null, nav],
            ["door_lock", "Doors", null, null, { features: [{ type: "lock-commands" }] }],
            ["climate", "A/C", null, null, { features: [{ type: "toggle" }] }],
          ]),
          ...syncTiles(e),
        ]),
      ];
    },
  },

  "mg-car-overview-card": {
    name: "MG car overview",
    description: "Battery gauge, range, energy in the pack, charger and charging details.",
    schema: [{ name: "title", selector: { text: {} } }],
    build(config, e, device) {
      const badges = [];
      if (e.sync_status) badges.push({ type: "entity", entity: e.sync_status, show_state: true, show_icon: true });
      if (e.last_update) badges.push({ type: "entity", entity: e.last_update, show_state: true, show_icon: true, icon: "mdi:update" });
      const cards = [heading(config.title || device.name, "mdi:car-electric", badges)];
      if (e.battery) {
        cards.push({
          type: "conditional",
          conditions: [{ condition: "numeric_state", entity: e.battery, above: -1 }],
          card: { type: "gauge", entity: e.battery, name: "Battery", min: 0, max: 100, needle: true, severity: { green: 50, yellow: 20, red: 0 } },
        });
        cards.push({
          type: "conditional",
          conditions: [{ condition: "state", entity: e.battery, state: ["unknown", "unavailable"] }],
          card: tile(e.battery, "Battery", "mdi:battery-sync-outline", "grey"),
        });
      }
      cards.push(grid(2, tiles(e, [
        ["range", "Range", "mdi:map-marker-distance"],
        ["battery_energy", "Energy in pack"],
        ["plugged_in", "Charger"],
        ["charging", "Charging", null, "green"],
      ])));
      const charging = tiles(e, [
        ["charging_power", "Charging power", null, "green"],
        ["charge_finish", "Full at"],
      ]);
      if (charging.length) cards.push(e.charging ? when(e.charging, true, grid(2, charging)) : grid(2, charging));
      return cards;
    },
  },

  "mg-car-controls-card": {
    name: "MG car controls",
    description: "Cloud sync switch and details, door lock, air conditioning, find my car and refresh.",
    schema: [
      { name: "title", selector: { text: {} } },
      { name: "show_details", selector: { boolean: {} } },
    ],
    build(config, e) {
      const cards = [heading(config.title || "Controls", "mdi:remote")];
      cards.push(grid(2, [...cloudSyncTiles(e), ...tiles(e, [["sync_status", "Sync status"]])]));
      if (e.sync_status && config.show_details !== false) {
        const row = (attribute, name, icon, format) => ({ type: "attribute", entity: e.sync_status, attribute, name, icon, ...(format ? { format } : {}) });
        cards.push({
          type: "entities",
          state_color: true,
          entities: [
            row("message", "Details", "mdi:message-alert-outline"),
            // Times are blank while paused (and before the first sync); a blank time would read "56 years ago".
            {
              type: "conditional",
              conditions: [{ condition: "state", entity: e.sync_status, state_not: "paused" }],
              row: row("last_success", "Last successful sync", "mdi:check-circle-outline", "relative"),
            },
            {
              type: "conditional",
              conditions: [{ condition: "state", entity: e.sync_status, state_not: "paused" }],
              row: row("next_refresh", "Next refresh", "mdi:clock-outline", "relative"),
            },
          ],
        });
      }
      cards.push(grid(2, tiles(e, [
        ["door_lock", "Doors", null, null, { features: [{ type: "lock-commands" }] }],
        ["climate", "Air conditioning", null, null, { features: [{ type: "toggle" }] }],
      ])));
      const buttons = [
        ["find_my_car", "Find my car", "mdi:car-search", "Flash the lights and sound the horn?"],
        ["tailgate", "Open boot", "mdi:car-back", "Open the boot?"],
        ["windows_close", "Close windows", "mdi:car-door", null],
      ].filter(([k]) => e[k]).map(([k, name, icon, confirm]) => tile(e[k], name, icon, null, { hide_state: true, tap_action: press(e[k], confirm) }));
      buttons.push(...syncTiles(e, "Sync now"));
      if (buttons.length) cards.push(grid(2, buttons));
      return cards;
    },
  },

  "mg-car-status-card": {
    name: "MG car status",
    description: "Doors, windows, boot, bonnet, lights, cabin and outside temperature.",
    schema: [{ name: "title", selector: { text: {} } }],
    build(config, e) {
      return [
        heading(config.title || "Status", "mdi:car-info"),
        grid(2, tiles(e, [
          ["doors", "Doors"],
          ["windows", "Windows"],
          ["boot", "Boot"],
          ["bonnet", "Bonnet"],
          ["lights", "Lights"],
          ["interior_temperature", "Cabin"],
          ["exterior_temperature", "Outside"],
        ])),
      ];
    },
  },

  "mg-car-health-card": {
    name: "MG car health",
    description: "Tyre pressures, 12 V battery and odometer.",
    schema: [{ name: "title", selector: { text: {} } }],
    build(config, e) {
      return [
        heading(config.title || "Health", "mdi:car-wrench"),
        grid(2, tiles(e, [
          ["tyre_front_left", "Front left", "mdi:tire"],
          ["tyre_front_right", "Front right", "mdi:tire"],
          ["tyre_rear_left", "Rear left", "mdi:tire"],
          ["tyre_rear_right", "Rear right", "mdi:tire"],
          ["aux_battery_voltage", "12 V battery"],
          ["odometer", "Odometer"],
        ])),
      ];
    },
  },

  "mg-car-location-card": {
    name: "MG car location",
    description: "Map of where the car last reported its position.",
    schema: [
      { name: "title", selector: { text: {} } },
      { name: "default_zoom", selector: { number: { min: 5, max: 20, mode: "box" } } },
    ],
    build(config, e) {
      const cards = [heading(config.title || "Location", "mdi:map-marker")];
      if (e.location) cards.push({ type: "map", entities: [e.location], default_zoom: Number(config.default_zoom) || 15, aspect_ratio: "16:10" });
      return cards;
    },
  },
};

const LABELS = {
  device: "Car",
  title: "Title",
  show_details: "Show sync details",
  navigation_path: "Open this view when tapped (e.g. /lovelace/car)",
  default_zoom: "Map zoom",
};

/* ---------- shared card element ---------- */

let helpersPromise = null;
const cardHelpers = () => (helpersPromise ||= window.loadCardHelpers());

class MgCarCard extends HTMLElement {
  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = { ...config };
    this._built = false;
    if (this._hass) this._build();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._child) this._child.hass = hass;
    if (!this._built && this._config) this._build();
  }

  get hass() {
    return this._hass;
  }

  async _build() {
    this._built = true;
    const token = (this._token = {});
    const spec = CARDS[this.localName];
    let config;
    try {
      const device = await findDevice(this._hass, this._config.device);
      if (token !== this._token) return;
      if (!device) {
        this._message(
          this._config.device
            ? "This car is no longer set up in MG iSMART India. Pick another one in the card settings."
            : "No MG iSMART India car found. Add one under Settings → Devices & services."
        );
        return;
      }
      config = { type: "vertical-stack", cards: spec.build(this._config, device.entities, device, this._hass) };
    } catch (err) {
      if (token !== this._token) return;
      this._message(`MG iSMART India is not loaded yet (${err.message || err}).`, true);
      return;
    }
    const helpers = await cardHelpers();
    if (token !== this._token) return;
    const child = helpers.createCardElement(config);
    child.hass = this._hass;
    this._child = child;
    this.replaceChildren(child);
  }

  _message(text, retry = false) {
    this._child = null;
    const card = document.createElement("ha-card");
    const div = document.createElement("div");
    div.style.padding = "16px";
    div.textContent = text;
    card.appendChild(div);
    this.replaceChildren(card);
    if (retry) setTimeout(() => { this._built = false; if (this._hass) this._build(); }, 10000);
  }

  getCardSize() {
    return this._child?.getCardSize ? this._child.getCardSize() : 4;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }
}

for (const [tag, spec] of Object.entries(CARDS)) {
  if (customElements.get(tag)) continue;
  customElements.define(
    tag,
    class extends MgCarCard {
      static getStubConfig() {
        return {};
      }

      static getConfigForm() {
        return {
          schema: [{ name: "device", selector: { device: { integration: DOMAIN } } }, ...spec.schema],
          computeLabel: (s) => LABELS[s.name] || s.name,
        };
      }
    }
  );
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === tag)) {
    window.customCards.push({ type: tag, name: spec.name, description: spec.description, preview: true, documentationURL: DOCS });
  }
}

console.info(`%c MG ISMART INDIA %c cards ${VERSION} `, "background:#16a34a;color:#fff;font-weight:600", "background:#333;color:#fff");
