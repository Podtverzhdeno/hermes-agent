---
name: findmy
description: Track Apple devices and AirTags via FindMy.app on macOS using AppleScript and screen capture.
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [FindMy, AirTag, location, tracking, macOS, Apple]
---

# Find My (Apple)

Use macOS Find My only to locate specifically authorized devices or items belonging to the current user. Its individual `harness.yaml` defines item/identity preflight, screenshot privacy, bounded tool use and cleanup; it is advisory, not a permission grant. Find My screenshots can expose precise locations, household membership and other unrelated devices.

## Prerequisites

- **macOS** with Find My app and iCloud signed in
- Devices/AirTags already registered in Find My
- Screen Recording permission for terminal (System Settings → Privacy → Screen Recording)
- **Optional**: a reviewed Peekaboo UI automation binary may improve reliability, but installing it or granting Screen Recording/Accessibility permissions requires explicit authorization; never install automatically.

## When to Use

- User asks "where is my [device/cat/keys/bag]?"
- Tracking AirTag locations
- Checking device locations (iPhone, iPad, Mac, AirPods)
- A single authorized item's current/last-known location. Continuous observation requires a separate, explicit, time-bounded monitoring request and privacy controls.

## Privacy preflight

1. Confirm the exact signed-in Apple account, owned/authorized device or item and whether a one-shot check or monitored series was requested.
2. Minimize the view to the target item; avoid screenshots containing unrelated people, shared devices, residential addresses or additional account data.
3. Keep capture in a temporary location with owner-only permissions and a bounded lifetime. Never upload screenshots to cloud OCR or external analysis without authorization.
4. Distinguish current location, **last seen** location, time of observation and map accuracy. Never invent coordinates that are not visible.
5. Do not initiate tracking of another person, their devices or an undisclosed shared item without appropriate consent and authority.

## Method 1: AppleScript + Screenshot (Basic)

### Open FindMy and Navigate

```bash
# Open Find My app
osascript -e 'tell application "FindMy" to activate'

# Wait for it to load
sleep 3

# Take a screenshot of the Find My window
umask 077
PRIVATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hermes-findmy-XXXXXXXX")"
chmod 700 "$PRIVATE_DIR"
screencapture -w -o "$PRIVATE_DIR/once.png"
printf "Capture: %s/once.png\n" "$PRIVATE_DIR"
```

Then use `vision_analyze` to read the screenshot:
```
vision_analyze(image_url="<absolute-path-reported-by-Capture>", question="Show only the authorized item and its visible location/last-updated time; ignore unrelated items.")
```

### Switch Between Tabs

```bash
# Switch to Devices tab
osascript -e '
tell application "System Events"
    tell process "FindMy"
        click button "Devices" of toolbar 1 of window 1
    end tell
end tell'

# Switch to Items tab (AirTags)
osascript -e '
tell application "System Events"
    tell process "FindMy"
        click button "Items" of toolbar 1 of window 1
    end tell
end tell'
```

## Method 2: Peekaboo UI Automation (Recommended)

If reviewed `peekaboo` is already installed and authorized, use it for UI interaction. Create a private directory for this method and preserve its actual absolute path across separate terminal shells:

```bash
PRIVATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hermes-findmy-XXXXXXXX")"
chmod 700 "$PRIVATE_DIR"
# Open Find My
osascript -e 'tell application "FindMy" to activate'
sleep 3

# Capture and annotate the UI
peekaboo see --app "FindMy" --annotate --path "$PRIVATE_DIR/findmy-ui.png"

# Click on a specific device/item by element ID
peekaboo click --on B3 --app "FindMy"

# Capture the detail view
peekaboo image --app "FindMy" --path "$PRIVATE_DIR/findmy-detail.png"
```

Then analyze with vision:
```
vision_analyze(image_url="<absolute-path-from-capture-session>/findmy-detail.png", question="For the authorized item only, report the visible last-seen time and location; include coordinates only if displayed.")
```

## Continuous tracking — disabled by default

Do **not** start an infinite screenshot loop, cronjob or continuous monitoring merely because a user requests one location. Such automation creates a sensitive location history, potentially captures unrelated devices and persists beyond the current response.

If monitoring is separately and explicitly authorized, specify exact owned item, start/end window, maximum captures, polling interval, local encrypted storage and deletion/retention period; verify the operating system and app allow the monitoring. Use a bounded user-controlled service rather than `while true` in a terminal. Stop and clean up on expiry or revocation.
## Limitations

- FindMy has **no CLI or API** — must use UI automation
- AirTags only update location while the FindMy page is actively displayed
- Location accuracy depends on nearby Apple devices in the FindMy network
- Screen Recording permission required for screenshots
- AppleScript UI automation may break across macOS versions

## Rules

1. Verify actual item update behavior and timestamps in the installed Find My version; do not assume a view refresh equals a new location update.
2. Use on-device vision analysis where available and authorized; do not upload sensitive screenshots to an external vision provider by default.
3. Never schedule ongoing location monitoring without separate explicit consent, a bounded lifetime and retention controls.
4. Only track devices/items with verified ownership/authorization. After the task, delete unneeded screenshot artifacts and avoid sharing unrelated account information.

## Verification and cleanup

Record the exact item label, report whether the location is current or last-seen, and give the displayed timestamp with precision limits. Preserve no unapproved location history. If UI automation or vision fails, say the location could not be verified rather than guessing. Delete temporary captures using the same authorized file scope; never send them to an external service just to improve recognition.

**Capture lifecycle:** Keep each absolute screenshot path within the authorized task; delete its private capture directory after analysis. Do not leave a cronjob, indefinite screenshot process or residual location history.
