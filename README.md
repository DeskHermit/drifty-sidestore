# Telegram -> SideStore: Driftywinds YouTube variants

This project checks the **[IPA] Tweaked YouTube** topic of the Telegram group **drifty's megalomania**, downloads the newest matching IPA per app, uploads each changed file to a public GitHub Release, and publishes **three independent SideStore sources** (`ytlite.json`, `ytkace.json`, `youmod.json`) and a duplicate-safe combined `source.json`. All three release histories remain independent in `state.json`.

**Important:** Only use the mirror if you have permission to redistribute the software and any bundled proprietary content. IPA files may contain copyrighted apps or unauthorized modifications. A public GitHub release makes the file available to everyone. This is a third-party automation and is not endorsed by app developers.

## Requirements

- A GitHub repository, **public** if you want direct public IPA download links.
- A Telegram account that has joined https://t.me/+rvcObIvOpctiMDI9 and can read the `[IPA] Tweaked YouTube` topic.
- Telegram **API ID** and **API hash** from https://my.telegram.org/apps (different from a bot token).
- Python 3.12 locally for one-time authentication.
- A GitHub repository default branch named `main`. Change the `main` URLs in `scripts/sync.py` if yours is different.

## 1. Create repository

Create a blank GitHub repository, for example `YOUR_USERNAME/drifty-sidestore`. Put **all files and directories** from this package into that repository, with `.github/workflows/sync.yml` retained exactly. To do so using Git:

```bash
git init -b main
git add .
git commit -m "Initial Telegram SideStore pipeline"
git remote add origin https://github.com/YOUR_USERNAME/drifty-sidestore.git
git push -u origin main
```

## 2. Authenticate Telegram once, on your own machine

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
python scripts/create_session.py
```

Enter your Telegram API ID and API hash, then the phone/SMS/Telegram code and two-factor password (if prompted). The output is a single **StringSession**. This session can access your Telegram account; do **not** commit it, publish it in an issue, or paste it into a public chat.

## 3. Add GitHub Actions secrets

In your repository, navigate to **Settings -> Secrets and variables -> Actions -> New repository secret**. Add:

| Name | Value |
| --- | --- |
| `TG_API_ID` | Telegram API ID from my.telegram.org |
| `TG_API_HASH` | Telegram API hash from my.telegram.org |
| `TG_SESSION` | StringSession from step 2 |

The workflow uses GitHub's automatically supplied `GITHUB_TOKEN` to create Releases and commit the JSON files. No manually generated GitHub PAT is required.

Go to **Settings -> Actions -> General -> Workflow permissions**. Ensure the Actions token can write repository contents (where this option is offered); the workflow also declares `permissions: contents: write`. Ensure Actions are enabled.

## 4. Start sync and check

Go to **Actions -> Update Telegram SideStore source -> Run workflow**. The first run discovers the topic by exact title and searches the document attachments in that topic. It chooses the newest IPA matching each of these patterns:

- `YTPlusYTweaks_custom_*_v21.43.5.ipa` -> YTLite
- `YTKACE_1.1.4_YouTube_21.44.4.ipa` -> YTKACE
- `YouMod_21.44.4_v2.0.0.ipa` -> YouMod

The patterns also recognize future version numbers. Other documents and messages are ignored. The most recent known release is retained separately for each variant, even if that variant was not updated in the latest Telegram batch.

After a successful run, the repository contains `source.json`, `ytlite.json`, `ytkace.json`, `youmod.json`, and `state.json`, and the Releases section contains the IPAs. The combined source URL will be:

```text
https://raw.githubusercontent.com/YOUR_USERNAME/drifty-sidestore/main/source.json
```

The independent SideStore source URLs are:

```text
https://raw.githubusercontent.com/YOUR_USERNAME/drifty-sidestore/main/ytlite.json
https://raw.githubusercontent.com/YOUR_USERNAME/drifty-sidestore/main/ytkace.json
https://raw.githubusercontent.com/YOUR_USERNAME/drifty-sidestore/main/youmod.json
```

**Why separate URLs?** SideStore / AltStore sources require unique `bundleIdentifier` values within any one source. If all three IPAs share `com.google.ios.youtube`, the combined `source.json` shows only the first one in priority order (YTLite, YTKACE, YouMod), while each dedicated JSON includes its own variant. SideStore may still deduplicate app identities across added sources, so separate URLs do not guarantee three simultaneous listings or installations. For that, the actual IPAs require distinct bundle IDs and correct re-signing; changing JSON alone is insufficient. These are source URLs, not IPA URLs.

## Automatic schedule

The included workflow runs at minute 17 every six hours (`17 */6 * * *`, UTC) and on demand. GitHub scheduled workflows are best-effort and may start late or be disabled after extended repository inactivity. They run from the default branch. For more frequent checks, update the cron (for example `17 */2 * * *` every two hours) while keeping Telegram API-rate and GitHub Actions usage in mind.

## Important behavior

- **No invented release:** A text message such as "waiting for YTLite crack" has no IPA attachment and cannot cause an update.
- **New file detection:** The Telegram message ID determines whether an IPA is new. If the same Telegram message stays the newest, no file is downloaded or re-uploaded.
- **Versions:** The source's `version`, `buildVersion`, and `bundleIdentifier` come from the IPA's `Payload/*.app/Info.plist`, not merely the Telegram caption. The YouTube and mod versions from the filename go in release notes.
- **Failure safety:** JSON is written only after all chosen upload operations succeed. Releases already uploaded in an interrupted run are reused when it is retried.
- **Duplicate bundle IDs:** A combined source emits at most one app listing per actual IPA bundle ID, so the source remains valid. Each of the three independent URLs targets one variant. SideStore may still merge/conflict across sources or on installation when IPA bundle IDs match.
- **Existing history:** `state.json` preserves older versions and the generator writes them in newest-first order.
- **Privacy:** This setup turns private-group downloads into **public GitHub Release assets**. Do not use it for content you are not allowed to publish. Keeping the repo private does *not* produce anonymous downloadable IPA URLs usable in SideStore.
- **Size:** Each GitHub Release asset must be under 2 GiB. Large IPA transfers and the 55-minute job timeout may make this unsuitable for very large app files.
- **Version collisions:** If the actual Info.plist version and build version are unchanged for a newer IPA, the job fails deliberately rather than silently offering a potentially undetectable update. See Troubleshooting.

## Troubleshooting

- `Joined Telegram group ... not found`: Join the invite in the same Telegram account used for your StringSession. Edit `TG_GROUP_NAME` if Telegram displays a different exact group name.
- `Could not uniquely identify topic`: Verify the exact topic title. Edit `TG_TOPIC_NAME` in `.github/workflows/sync.yml` if necessary.
- `No matching IPA attachments`: Confirm you have Telegram access, the post is a **file attachment**, and the topic has matching filenames. The script scans at most `MAX_MESSAGES=1200` document posts in the matching topic. Increase `MAX_MESSAGES` in the workflow environment if needed.
- `upstream IPA ... Info.plist version/build are still ...`: A newer modified build may carry the same version/build; SideStore can't reliably recognize it as a new update. You will need to decide whether to patch `CFBundleVersion` and re-sign the IPA (not handled here), or use a policy that serves only the latest download without promising update notification. Do not just falsify metadata in the source.
- `bundle ID changed`: Manual review is required; a changed bundle identifier may be a distinct iOS app and cannot be a normal in-place update.
- The workflow fails after uploading some releases: re-run it. It will reuse tags/assets that already exist.
- If the group changes post formatting, update the patterns in `scripts/sync.py`.
- For security, use a dedicated Telegram account if possible, revoke the session if leaked, and never log or print the session in Actions.

## References

- Telegram forum topic API: https://core.telegram.org/api/forum
- AltStore source: https://faq.altstore.io/developers/make-a-source
- SideStore source schema: https://github.com/SideStore/sidestore-source-types/blob/main/schema.json
- GitHub CLI releases: https://cli.github.com/manual/gh_release_create
