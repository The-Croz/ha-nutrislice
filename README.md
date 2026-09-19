# Nutrislice School Menus for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/default)
[![Validate](https://img.shields.io/github/actions/workflow/status/The-Croz/ha-nutrislice/validate.yml?branch=main&label=Hassfest%20%26%20HACS&style=for-the-badge)](https://github.com/The-Croz/ha-nutrislice/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

A Home Assistant custom integration for tracking school menus (Lunch, Breakfast, Snacks, etc.) published on **Nutrislice**, for any school or district on the platform.

View upcoming meals on a Home Assistant calendar, show today's and tomorrow's menu on your dashboard, and automate notifications for the next school meal.

---

## ✨ Features

- 🔍 **Easy Setup:** Paste a link to your school's Nutrislice menu, or search by district name. The integration then finds your school and all of its available meal menus.
- 📅 **Native Calendar Platform:** Generates all-day calendar events for each school day with entrees, sides, and beverages, directly on your Home Assistant calendar.
- 🔄 **Calendar Sync:** Optionally copy upcoming meals into any writable calendar (Local Calendar, Google Calendar, CalDAV, ...) so they appear alongside your other events on every device.
- 🍽️ **Smart Sensors:**
  - **Today's Menu:** Displays today's main entrees as state, with sides, allergens, and full menu items in attributes.
  - **Tomorrow's Menu:** Displays tomorrow's main entrees (with an option to preview Monday's lunch over the weekend!).
  - **Full Menu (Raw / Legacy Compatible):** Exposes the full raw `days` list matching standard REST sensor formats so existing notification templates work with zero changes.
- 🛡️ **Rate-Limit Friendly:** Fetches 2 weeks in advance with configurable update polling (default: every 4 hours).
- 🏷️ **Clean Item Categorization:** Separates entrees from sides, fruits, vegetables, milk, and condiments.

---

## 📦 Installation

### Option 1: HACS (Recommended)

1. Ensure [HACS (Home Assistant Community Store)](https://hacs.xyz/) is installed.
2. In Home Assistant, open **HACS** > **Integrations**.
3. Click the **three dots** in the top right corner and select **Custom repositories**.
4. Paste the repository URL: `https://github.com/The-Croz/ha-nutrislice`
5. Select **Integration** as the Category and click **Add**.
6. Find **Nutrislice School Menus** in HACS, click **Download**, and restart Home Assistant.

### Option 2: Manual Installation

1. Download the `custom_components/nutrislice` folder from the latest release.
2. Copy the `nutrislice` folder into your Home Assistant `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## ⚙️ Configuration & School Discovery

The integration includes an interactive UI setup flow to find your school:

1. In Home Assistant, navigate to **Settings** > **Devices & Services**.
2. Click **+ Add Integration** and search for **Nutrislice**.
3. On **Step 1 (Find Your School)**, fill in *either* box:
   - **Link to your school's Nutrislice menu** — the reliable option. Paste any address from your school's menu site, e.g. `https://my-district.nutrislice.com/menu/my-school/lunch`. A link that includes your school skips straight to Step 3.
   - **Or search by district name** — e.g. `Souderton` or `Fairfax County Public Schools`. See the caveat below.
4. **Step 2 (School Selection):** Pick your school from the list. If the search matched more than one district, each school is labelled with its district.
5. **Step 3 (Menu Types):** Select which meal menus to track (e.g. `Lunch`, `Breakfast`, `Snack`), and which courses to show in calendar event titles.
6. Click **Submit**. Your school device, sensors, and calendar entities are created automatically.

### Finding your link

Don't know your school's Nutrislice address? Open **[Nutrislice Lookup](https://lookup.nutrislice.com)**, search for your school, open its menu page, then copy the address out of your browser's address bar and paste it into Step 1.

### Why search by name doesn't always work

Nutrislice has no public directory of districts, and its own lookup service is protected by a CAPTCHA that an integration can't use. Searching by name therefore works by *guessing* the web address from the name — trying forms like `souderton`, `soudertonsd`, `soudertonschools`, and initials such as `fcps`.

That finds many districts, but **it cannot find a district whose web address is unrelated to its name.** For example, Pender County Schools in North Carolina publishes at `greatschools.nutrislice.com`, which no amount of guessing will produce from "Pender" or "Surf City". If your district is one of these, use the link instead — it always works.

---

## 📱 Entities Created

For each configured school and meal type:

| Entity Pattern | Platform | Description |
| :--- | :--- | :--- |
| `calendar.<school>_<menu>` | Calendar | Upcoming school meals with entree summaries and formatted descriptions. |
| `sensor.<school>_<menu>_today` | Sensor | State is today's main entree summary (e.g. `Cheeseburger, Pizza`). |
| `sensor.<school>_<menu>_tomorrow` | Sensor | State is tomorrow's main entrees (or the next school day's meal on weekends). |
| `sensor.<school>_<menu>_menu` | Sensor | State is the current date, with the full raw `days` structure in attributes. |

`<school>` is the school's name and `<menu>` is the meal type, both lowercased with underscores. *(For example, a school named "Maple Grove" with a Lunch menu gets `sensor.maple_grove_lunch_today`, `sensor.maple_grove_lunch_tomorrow`, and `calendar.maple_grove_lunch`.)*

> **Upgrading from 1.2.0 or earlier?** Entity IDs you already have are kept as-is by Home Assistant, so your automations keep working. Only the display names change (the redundant trailing "Calendar" is dropped).

The **Today** and **Tomorrow** sensors carry `date`, `entrees`, `sides`, `fruits`, `vegetables`, `beverages`, and `menu_items` (with calories and allergens) attributes. The **Tomorrow** sensor also has `is_next_school_day`, which is `true` when it's showing a later school day because tomorrow has no menu. `sides` includes fruit and vegetables; `fruits` and `vegetables` list those separately.

The examples below use `my_school_lunch` as a placeholder. Replace it with your own entity IDs, which you can find under **Settings** > **Devices & Services** > **Nutrislice**.

---

## 🔄 Syncing Menus to Another Calendar

The calendar entities this integration creates are read-only. To get school meals onto a calendar you already use, such as a shared family calendar, sync them into a writable one:

1. Make sure you have a calendar that supports creating events, e.g. [Local Calendar](https://www.home-assistant.io/integrations/local_calendar/), [Google Calendar](https://www.home-assistant.io/integrations/google/) (with write access), or CalDAV.
2. Go to **Settings** > **Devices & Services** > **Nutrislice** and click **Configure**.
3. Pick the calendar under **Sync menus to calendar** and submit.

Upcoming meals are then copied as all-day events (titled like `🍽️ Lunch: Cheeseburger, Pizza`, with the menu grouped into 🍽️ Entrees, 🥖 Sides, 🍎 Fruit, 🥦 Vegetables, and 🥛 Beverages in the description, and the school as the location) right away, after every menu update, and whenever you call the `nutrislice.sync_calendar` action. All menu types for a school go to the same calendar. Clear the field to turn syncing off.

**Good to know:**
- Sync only adds events. Home Assistant has no way for an integration to edit or delete calendar events, so a meal is created once and never rewritten. If the school changes a menu after it was synced, edit or delete that event on the target calendar yourself.
- Meals already on the target calendar (same day, menu type, and school) are skipped, so nothing is duplicated. To re-create a meal, delete its event and run `nutrislice.sync_calendar`.
- Only today and upcoming days are synced; past meals are left alone.
- If the target calendar is missing or can't create events, a warning is logged and the next update tries again.

---

## 🔔 Automations & Notifications

### Example 1: Evening Reminder for the Next School Lunch (Recommended)
Uses the **Tomorrow** sensor, so on a Friday evening it announces Monday's lunch. The title names the day the meal is for.

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

### Example 2: Morning Reminder from the Calendar
Fires at 7:00 AM on each school day that has a menu:

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

---

## 📊 Dashboard Card Examples

### Markdown Card: Today & Next School Day
```yaml
type: markdown
title: School Lunch
content: |
  **Today:** {{ states('sensor.my_school_lunch_today') }}

  **Next:** {{ states('sensor.my_school_lunch_tomorrow') }}
```

### Calendar Card
```yaml
type: calendar
entities:
  - calendar.my_school_lunch
initial_view: listWeek
```

---

## 🛠️ Options & Customization

Click **Configure** on the Nutrislice integration entry in **Settings** > **Devices & Services**:
- **Update Interval (hours):** Adjust how frequently Home Assistant checks for menu updates (1 to 24 hours, default `4`).
- **Show Next School Day on Weekends:** When enabled, the `Tomorrow` sensor will show the next school day's meal when tomorrow has no menu, such as on Friday evening, weekends, and holidays.
- **Show in Calendar Event Titles:** Tick which courses appear in event titles: 🍽️ Entrees, 🥖 Sides, 🍎 Fruit, 🥦 Vegetables, 🥛 Beverages. The default, Entrees only, gives `🍽️ Lunch: Cheeseburger, Pizza`. Tick more and each course is led by its emoji, e.g. `Lunch: 🍽️ Cheeseburger, Pizza 🍎 Apple, Orange`. Tick none for just `🍽️ Lunch`. The full grouped menu is always in the event description. Also offered during setup.
- **Sync Menus to Calendar:** Optional. Copy upcoming meals into another calendar. See [Syncing Menus to Another Calendar](#-syncing-menus-to-another-calendar).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
