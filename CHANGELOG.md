# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-09-18

### Added
- **Calendar sync:** optionally copy upcoming meals into any writable Home Assistant calendar (Local Calendar, Google Calendar, CalDAV, ...) as all-day events. Choose the calendar under **Configure** > **Sync menus to calendar**.
  - Runs at startup and after every menu update.
  - Meals already on the target calendar are skipped, so nothing is duplicated.
  - Sync only adds events. Home Assistant offers no way to edit or delete calendar events, so a menu changed by the school after syncing is not updated.
- New `nutrislice.sync_calendar` action to sync immediately.

### Changed
- Minimum Home Assistant version is now 2024.11.0.
- README is no longer specific to elementary schools, and automation examples use current Home Assistant syntax.

### Fixed
- Options flow no longer sets `config_entry` explicitly, which stops working in Home Assistant 2025.12.
- "Today" is now determined by Home Assistant's configured time zone instead of the server's.
- The calendar entity no longer returns a meal that falls on the (exclusive) end of the requested range.
