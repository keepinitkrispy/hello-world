# Android Phone Bridge

Mobile-only, free, privacy-focused Termux bridge for the owner's Android phone.

## Privacy model

- The public repository contains code only.
- GitHub authentication stays on the phone in the GitHub CLI credential store.
- Routine bridge heartbeats contain capability/status data only.
- Call/SMS/notification/location contents remain on-device unless an explicit allowlisted query requests them.
- Requested results are sent only to a private GitHub repository controlled by the owner.
- GitHub may retain edit history, so private GitHub storage is not treated as ephemeral.
- There is no arbitrary remote-shell operation in the cloud command queue.

## Install

Install **Termux** and **Termux:API** from the same signing source. F-Droid is the recommended path:

- https://f-droid.org/packages/com.termux/
- https://f-droid.org/packages/com.termux.api/

Optional after core setup:

- Termux:Boot: https://f-droid.org/packages/com.termux.boot/
- Shizuku: https://shizuku.rikka.app/download/

Open Termux and paste exactly one command:

```sh
curl -fsSL https://raw.githubusercontent.com/keepinitkrispy/hello-world/phone-bridge/phonebridge/bootstrap.sh | bash
```

The bootstrap installs its own free dependencies, validates the downloaded Python agent, triggers Android permission prompts, performs GitHub device authentication when needed, launches the bridge, and only prints `PHONE BRIDGE READY` after an end-to-end heartbeat reaches the private control channel.

## Current remote allowlist

Read/query operations only:

- `snapshot`
- `battery`
- `calls`
- `notifications`
- `sms`
- `location`
- `device`
- `apps`

No arbitrary remote shell command is accepted.
