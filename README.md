<div align="center">

# Drifty SideStore

**Automatically synchronized SideStore sources for YTLite, YTKACE, and YouMod.**

Mirroring releases from the **[IPA] Tweaked YouTube** topic in [drifty's megalomania on Telegram](https://t.me/+rvcObIvOpctiMDI9).

[![Sync](https://github.com/DeskHermit/drifty-sidestore/actions/workflows/sync.yml/badge.svg)](https://github.com/DeskHermit/drifty-sidestore/actions/workflows/sync.yml)
[![GitHub releases](https://img.shields.io/github/v/release/DeskHermit/drifty-sidestore?include_prereleases&label=latest%20release)](https://github.com/DeskHermit/drifty-sidestore/releases)

[**SideStore sources**](#add-a-source-to-sidestore) · [**Releases**](https://github.com/DeskHermit/drifty-sidestore/releases) · [**How it works**](#how-it-works) · [**Setup**](#self-hosting)

</div>

> [!IMPORTANT]
> This is an **unofficial, community-maintained automation project**, not an official release channel for YouTube, YTLite, YTKACE, YouMod, SideStore, or their developers. The scripts index files from a third-party Telegram topic; they do not create, verify, or endorse the modifications. Only redistribute or install software you are authorized to use.

## Add a source to SideStore

Choose the variant you want, copy its URL, and add it in **SideStore → Sources → +** (the exact menu name may vary by version).

| Variant | Source URL |
| :-- | :-- |
| **YTLite** | [`ytlite.json`](https://raw.githubusercontent.com/DeskHermit/drifty-sidestore/main/ytlite.json) |
| **YTKACE** | [`ytkace.json`](https://raw.githubusercontent.com/DeskHermit/drifty-sidestore/main/ytkace.json) |
| **YouMod** | [`youmod.json`](https://raw.githubusercontent.com/DeskHermit/drifty-sidestore/main/youmod.json) |
| **Combined** | [`source.json`](https://raw.githubusercontent.com/DeskHermit/drifty-sidestore/main/source.json) |

<details>
<summary>Copyable source URLs</summary>

**YTLite**
```text
https://raw.githubusercontent.com/DeskHermit/drifty-sidestore/main/ytlite.json
```

**YTKACE**
```text
https://raw.githubusercontent.com/DeskHermit/drifty-sidestore/main/ytkace.json
```

**YouMod**
```text
https://raw.githubusercontent.com/DeskHermit/drifty-sidestore/main/youmod.json
```

**Combined**
```text
https://raw.githubusercontent.com/DeskHermit/drifty-sidestore/main/source.json
```

</details>

### Why are there separate sources?

The upstream IPAs may share the same iOS bundle identifier, `com.google.ios.youtube`.

- Each **variant-specific** source contains its own app and release history, independent of the others.
- The **combined** source avoids duplicate bundle identifiers. When they conflict, it keeps **YTLite first, then YTKACE, then YouMod**; it does *not* list all three as separate apps.
- Adding multiple sources does **not** change the IPA's embedded bundle identifier or guarantee simultaneous installation. SideStore/iOS can still treat variants with the same identifier as the same app.

**For a specific variant, use its dedicated source URL.** These are source feed URLs, not direct IPA download links.

## How it works

```text
Telegram: [IPA] Tweaked YouTube
              |
              v
 GitHub Actions (every 6 hours)
              |
              v
   Identify newest IPA per variant
              |
         New release?
          /        \
        No          Yes
        |            |
       Skip      Download IPA
                     |
                     v
              GitHub Release
                     |
                     v
           Update JSON + state
                     |
                     v
              SideStore feeds
```

The workflow:

1. Connects to Telegram using a session stored as a GitHub Actions secret.
2. Looks only in **drifty's megalomania → [IPA] Tweaked YouTube** and matches recognized IPA filenames.
3. Tracks YTLite, YTKACE, and YouMod **independently**; a delayed YTLite release does not block other updates.
4. Skips downloads when the latest matching Telegram message has already been processed.
5. Uploads new IPA attachments to [GitHub Releases](https://github.com/DeskHermit/drifty-sidestore/releases) and updates the source JSON files and [`state.json`](state.json).
6. Reads each IPA's embedded bundle identifier, version, and build version instead of guessing those values from the caption.

A message saying *“waiting for YTLite crack”* is not an IPA attachment and does not trigger a release.

**Schedule:** `17 */6 * * *` (UTC), plus manual runs from the [Actions tab](https://github.com/DeskHermit/drifty-sidestore/actions). Scheduled GitHub Actions runs can start later than their nominal time.

## Self-hosting

You can fork or copy this project to operate your own source. A **public** repository is required for anonymously accessible GitHub Release links used by SideStore. Ensure you have permission to redistribute any mirrored IPA files.

### 1. Telegram credentials

Create an application at [my.telegram.org/apps](https://my.telegram.org/apps) to obtain an API ID and API hash. Use a Telegram account with access to the topic.

On your own computer (Python 3.12 recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/create_session.py
```

On Linux/macOS, activate with `source .venv/bin/activate` instead.

The script prints a Telegram **StringSession**. **Never commit or share it.** It grants access as the signed-in Telegram account.

### 2. GitHub repository secrets

In **Settings → Secrets and variables → Actions**, add:

| Secret | Description |
| :-- | :-- |
| `TG_API_ID` | Numeric Telegram API ID |
| `TG_API_HASH` | Telegram API hash |
| `TG_SESSION` | Entire generated StringSession, including trailing `=` if present |

The workflow uses the built-in `GITHUB_TOKEN` with `contents: write`; no personal access token is needed. Enable write access under **Settings → Actions → General** if required by your repository settings.

### 3. Configure and run

- Update hard-coded `DeskHermit/drifty-sidestore` URLs and relevant repository references in `scripts/sync.py` when using a different repository.
- Review `TG_GROUP_NAME` and `TG_TOPIC_NAME` in [`.github/workflows/sync.yml`](.github/workflows/sync.yml).
- Open **Actions → Update Telegram SideStore source → Run workflow**.
- Confirm that [`state.json`](state.json), the four JSON feeds, and [Releases](https://github.com/DeskHermit/drifty-sidestore/releases) were updated.

The first run may take several minutes to download the initial IPA files. Subsequent runs with no new releases should be much faster.

## Project layout

```text
.github/workflows/sync.yml   Scheduled and manual synchronization
scripts/sync.py              Telegram scan, release publishing, source generation
scripts/create_session.py    One-time local Telegram login
requirements.txt             Python dependencies
state.json                   Stored release history / deduplication state
source.json                  Combined, duplicate-safe SideStore feed
ytlite.json                  YTLite-only feed
ytkace.json                  YTKACE-only feed
youmod.json                  YouMod-only feed
assets/                      Source and app icons
```

## Troubleshooting

| Symptom | What to check |
| :-- | :-- |
| Telegram group or topic not found | The session's account must be a member; check the exact `TG_GROUP_NAME` / `TG_TOPIC_NAME` values. |
| No matching attachments | Check the filenames and topic, and the script's message scan limit. |
| Missing repository permissions | Ensure the workflow has `contents: write` and that Actions is allowed to write. |
| Existing app does not show an update | The IPA's internal version/build may not have changed, even if its filename did. |
| Different variants overwrite each other | They share the same embedded iOS bundle identifier. Separate feed URLs do not fix installed-app identity. |
| Failed run after an upload | Re-run the workflow; existing release assets can be reused. |

For detailed errors, open the latest [workflow run](https://github.com/DeskHermit/drifty-sidestore/actions/workflows/sync.yml) and review **Sync Telegram files and source**. Never paste secret values into an issue or log.

## Usage, costs, and attribution

Standard GitHub-hosted Actions runners are free for public repositories under GitHub's current pricing policy. The first sync transfers large IPA files; unchanged releases are skipped to reduce bandwidth and runtime. GitHub's policies and limits can change.

All application names and trademarks belong to their respective owners. This repository is an independent distribution/indexing tool and is not affiliated with or endorsed by them. Downloaded software may include proprietary content; publication should only be enabled with appropriate rights. Review the upstream source and binaries before installation.
