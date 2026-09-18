# Nutrislice School Menus for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/default)
[![Validate](https://img.shields.io/github/actions/workflow/status/The-Croz/ha-nutrislice/validate.yml?branch=main&label=Hassfest%20%26%20HACS&style=for-the-badge)](https://github.com/The-Croz/ha-nutrislice/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

School breakfast and lunch menus from **Nutrislice** in Home Assistant, as a calendar and as sensors for today's and the next school day's meals.

## Features

- **Calendar** of upcoming meals, with entrees, sides, and beverages.
- **Sensors** for today's and the next school day's entrees.
- **Calendar sync** (optional) into a Local, Google, or CalDAV calendar you already use.
- Works with any school on Nutrislice, for any meal type (lunch, breakfast, snacks, ...).

## Installation

**HACS:** In HACS, open the menu → **Custom repositories**, add `https://github.com/The-Croz/ha-nutrislice` as an **Integration**, then download **Nutrislice School Menus** and restart Home Assistant.

**Manual:** Copy `custom_components/nutrislice` from the latest release into `<config>/custom_components/`, then restart Home Assistant.

## Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration** → **Nutrislice**.
2. Paste a **link to your school's Nutrislice menu**, e.g. `https://my-district.nutrislice.com/menu/my-school/lunch`. Or search by district name instead.
3. Pick your school (skipped if your link already names it), then the menus to track.

**Finding your link:** open [Nutrislice Lookup](https://lookup.nutrislice.com), find your school, open its menu, and copy the address from your browser.

Name search works by guessing the district's web address, so it can't find districts whose address differs from their name (Pender County Schools, for example, is `greatschools`). The link always works.

## Entities

For each school and menu type, e.g. a school "My School" with a Lunch menu:

| Entity | State |
| :--- | :--- |
| `calendar.my_school_lunch` | One all-day event per school day. |
| `sensor.my_school_lunch_today` | Today's entrees, e.g. `Cheeseburger, Pizza`, or `No Menu Scheduled`. |
| `sensor.my_school_lunch_tomorrow` | Tomorrow's entrees. Over weekends and holidays, the next school day's (see Options). |
| `sensor.my_school_lunch_menu` | Today's date, with the raw Nutrislice `days` data in its attributes. |

The today and tomorrow sensors have `date`, `entrees`, `sides`, `beverages`, and `menu_items` (with calories and allergens) attributes. The tomorrow sensor also has `is_next_school_day`.

Find your exact entity IDs under **Settings** → **Devices & Services** → **Nutrislice**. Upgrading from 1.2.0 or earlier keeps your existing entity IDs.

## Options

Click **Configure** on the integration:

- **Update interval:** how often menus are fetched (1–24 hours, default 4).
- **Show next school day on weekends:** the tomorrow sensor shows the next school day's meal when tomorrow has none (on by default).
- **Sync menus to calendar:** copy upcoming meals into a writable calendar. Leave empty to turn off.

### About calendar sync

Meals are copied as all-day events (e.g. `Lunch: Cheeseburger, Pizza`) at startup, after each update, and when you run the `nutrislice.sync_calendar` action. Sync only adds events: meals already on the calendar are skipped, and events are never edited or deleted, so a menu changed after syncing stays as it was.

## Examples

Replace `my_school_lunch` with your own entity IDs.

### Notify the evening before

Uses the tomorrow sensor, so on a Friday it announces Monday's lunch.

```yaml
alias: School lunch reminder
triggers:
  - trigger: time
    at: "18:00:00"
conditions:
  - condition: not
    conditions:
      - condition: state
        entity_id: sensor.my_school_lunch_tomorrow
        state: ["No Menu Scheduled", "unknown", "unavailable"]
actions:
  - action: notify.notify
    data:
      title: >-
        Lunch for {{ strptime(state_attr('sensor.my_school_lunch_tomorrow', 'date'), '%Y-%m-%d').strftime('%A') }}
      message: >-
        {{ states('sensor.my_school_lunch_tomorrow') }}.
        Sides: {{ state_attr('sensor.my_school_lunch_tomorrow', 'sides') | join(', ') }}
```

### Notify the morning of

Fires at 7:00 AM on each school day with a menu.

```yaml
alias: School lunch this morning
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.my_school_lunch
    offset: "07:00:00"
actions:
  - action: notify.notify
    data:
      title: "{{ trigger.calendar_event.summary }}"
      message: "{{ trigger.calendar_event.description }}"
```

### Dashboard cards

```yaml
type: markdown
title: School Lunch
content: |
  **Today:** {{ states('sensor.my_school_lunch_today') }}

  **Next:** {{ states('sensor.my_school_lunch_tomorrow') }}
```

```yaml
type: calendar
entities:
  - calendar.my_school_lunch
initial_view: listWeek
```

## License

MIT, see [LICENSE](LICENSE).
