# Nutrislice School Menus for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/default)
[![Validate](https://img.shields.io/github/actions/workflow/status/The-Croz/ha-nutrislice/validate.yml?branch=main&label=Hassfest%20%26%20HACS&style=for-the-badge)](https://github.com/The-Croz/ha-nutrislice/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

A Home Assistant custom integration for tracking school menus (Lunch, Breakfast, Snacks, etc.) published on **Nutrislice**, for any school or district on the platform.

View upcoming meals on a Home Assistant calendar, show today's and tomorrow's menu on your dashboard, and automate notifications for the next school meal.

---

## ✨ Features

- 🔍 **Universal School & District Search:** Works for any school using Nutrislice. Enter your school district slug or simply paste any URL from your school's Nutrislice website. The integration automatically discovers your school and all available meal menus.
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
3. Follow the setup wizard:
   - **Step 1 (District Discovery):** 
     - Enter your district subdomain (e.g. `mydistrict` for `mydistrict.nutrislice.com`)
     - **OR** simply paste any link from your school's menu website (e.g. `https://mydistrict.nutrislice.com/menu/my-school/lunch`). The setup wizard will automatically parse the district and school from the link!
   - **Step 2 (School Selection):** Select your school from the dropdown list of schools found in that district.
   - **Step 3 (Menu Types):** Select which meal menus you want to track (e.g. `Lunch`, `Breakfast`, `Snack`).
4. Click **Submit**. Your school device, sensors, and calendar entities will be automatically created!

---

## 📱 Entities Created

For each configured school and meal type:

| Entity Pattern | Platform | Description |
| :--- | :--- | :--- |
| `calendar.<school>_<menu>_calendar` | Calendar | Upcoming school meals with entree summaries and formatted descriptions. |
| `sensor.<school>_<menu>_today` | Sensor | State is today's main entree summary (e.g. `Cheeseburger, Pizza`). |
| `sensor.<school>_<menu>_tomorrow` | Sensor | State is tomorrow's main entrees (or the next school day's meal on weekends). |
| `sensor.<school>_<menu>_menu` | Sensor | State is the current date, with the full raw `days` structure in attributes. |

`<school>` is the school's name and `<menu>` is the meal type, both lowercased with underscores. *(For example, a school named "Maple Grove" with a Lunch menu gets `sensor.maple_grove_lunch_today`, `sensor.maple_grove_lunch_tomorrow`, and `calendar.maple_grove_lunch_calendar`.)*

The examples below use `my_school_lunch` as a placeholder. Replace it with your own entity IDs, which you can find under **Settings** > **Devices & Services** > **Nutrislice**.

---

## 🔄 Syncing Menus to Another Calendar

The calendar entities this integration creates are read-only. To get school meals onto a calendar you already use, such as a shared family calendar, sync them into a writable one:

1. Make sure you have a calendar that supports creating events, e.g. [Local Calendar](https://www.home-assistant.io/integrations/local_calendar/), [Google Calendar](https://www.home-assistant.io/integrations/google/) (with write access), or CalDAV.
2. Go to **Settings** > **Devices & Services** > **Nutrislice** and click **Configure**.
3. Pick the calendar under **Sync menus to calendar** and submit.

Upcoming meals are then copied as all-day events (titled like `Lunch: Cheeseburger, Pizza`, with the school as the location) right away, after every menu update, and whenever you call the `nutrislice.sync_calendar` action. All menu types for a school go to the same calendar. Clear the field to turn syncing off.

**Good to know:**
- Sync only adds events. Home Assistant has no way for an integration to edit or delete calendar events, so a meal is created once and never rewritten. If the school changes a menu after it was synced, edit or delete that event on the target calendar yourself.
- Meals already on the target calendar (same day, menu type, and school) are skipped, so nothing is duplicated. To re-create a meal, delete its event and run `nutrislice.sync_calendar`.
- Only today and upcoming days are synced; past meals are left alone.
- If the target calendar is missing or can't create events, a warning is logged and the next update tries again.

---

## 🔔 Automations & Notifications

### Example 1: Clean Notification for Tomorrow's School Lunch (Recommended)
Using the dedicated **Tomorrow's Menu** sensor:

```yaml
alias: "School Lunch: Tomorrow's Menu Notification"
triggers:
  - trigger: time
    at: "18:00:00" # 6:00 PM every evening
conditions:
  - condition: template
    value_template: "{{ states('sensor.my_school_lunch_tomorrow') not in ['No Menu Scheduled', 'unknown', 'unavailable'] }}"
actions:
  - action: notify.notify
    data:
      title: "Tomorrow's School Lunch"
      message: >
        Tomorrow at {{ state_attr('sensor.my_school_lunch_tomorrow', 'school_name') }}:
        Entrees: {{ states('sensor.my_school_lunch_tomorrow') }}
        Sides: {{ state_attr('sensor.my_school_lunch_tomorrow', 'sides') | join(', ') }}
```

### Example 2: Using the Raw Days Attribute Template
If you prefer extracting specific items via Jinja template:

```yaml
alias: "School Lunch Notification via Raw Days"
triggers:
  - trigger: time
    at: "18:00:00"
actions:
  - action: notify.notify
    data:
      title: "Tomorrow's School Lunch"
      message: >
        {% set tomorrow = (now() + timedelta(days=1)).strftime("%Y-%m-%d") %}
        {% for day in state_attr('sensor.my_school_lunch_menu', 'days') | selectattr("menu_items") %}
          {%- if day.date == tomorrow -%}
            {% set items = day.menu_items | slice(2) | first %}
            {%- if items -%}
              {{ items | map(attribute="food.name") | reject("equalto", None) | select('string') | join(', ') }}
            {%- endif -%}
          {%- endif -%}
        {% endfor %}
```

### Example 3: Calendar Event Trigger
You can also trigger reminders directly from the school calendar:

```yaml
alias: "School Lunch: Morning Calendar Reminder"
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.my_school_lunch_calendar
    offset: "07:00:00" # 7:00 AM on the day of the meal
actions:
  - action: notify.notify
    data:
      title: "{{ trigger.calendar_event.summary }}"
      message: "{{ trigger.calendar_event.description }}"
```

---

## 📊 Dashboard Card Examples

### Markdown Card: Today & Tomorrow Overview
```yaml
type: markdown
title: 🎒 School Lunch Menu
content: >
  ### Today ({{ state_attr('sensor.my_school_lunch_today', 'date') }})
  **Entrees:** {{ states('sensor.my_school_lunch_today') }}

  **Sides:** {{ state_attr('sensor.my_school_lunch_today', 'sides') | join(', ') }}

  ---
  ### Tomorrow ({{ state_attr('sensor.my_school_lunch_tomorrow', 'date') }})
  **Entrees:** {{ states('sensor.my_school_lunch_tomorrow') }}

  **Sides:** {{ state_attr('sensor.my_school_lunch_tomorrow', 'sides') | join(', ') }}
```

### Calendar Card
```yaml
type: calendar
entities:
  - calendar.my_school_lunch_calendar
initial_view: dayGridMonth
```

---

## 🛠️ Options & Customization

Click **Configure** on the Nutrislice integration entry in **Settings** > **Devices & Services**:
- **Update Interval (hours):** Adjust how frequently Home Assistant checks for menu updates (1 to 24 hours, default `4`).
- **Show Next School Day on Weekends:** When enabled, the `Tomorrow` sensor will show the next school day's meal when tomorrow has no menu, such as on Friday evening, weekends, and holidays.
- **Sync Menus to Calendar:** Optional. Copy upcoming meals into another calendar. See [Syncing Menus to Another Calendar](#-syncing-menus-to-another-calendar).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
