"""Telegram topic -> GitHub Release assets -> SideStore source.

Requires joined Telegram user account, GH_TOKEN, GH_REPO, TG_API_ID,
TG_API_HASH, TG_SESSION. The repo workflow commits JSON sources and state.
For all three apps, each new Telegram release receives a distinct CFBundleVersion
within a repackaged IPA, matched by the SideStore source metadata.
"""
import asyncio
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest, SearchRequest
from telethon.tl.types import InputMessagesFilterDocument

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'state.json'
SOURCE = ROOT / 'source.json'
REPO = os.environ['GH_REPO']
GROUP_NAME = os.getenv('TG_GROUP_NAME', "drifty's megalomania")
TOPIC_NAME = os.getenv('TG_TOPIC_NAME', '[IPA] Tweaked YouTube')
MAX_MESSAGES = int(os.getenv('MAX_MESSAGES', '1200'))

APPS = {
    'YTLite': {'name': 'YTLite', 'description': 'YTLite with additional YouTube tweaks.', 'icon': 'ytlite.png'},
    'YTKACE': {'name': 'YTKACE', 'description': 'YTKACE with additional YouTube tweaks.', 'icon': 'ytkace.png'},
    'YouMod': {'name': 'YouMod', 'description': 'YouMod with additional YouTube tweaks.', 'icon': 'youmod.png'},
}
PATTERNS = {
    'YTLite': re.compile(r'^YTPlusYTweaks_custom_.*_v(?P<yt>\d+\.\d+\.\d+)\.ipa$', re.I),
    'YTKACE': re.compile(r'^YTKACE_(?P<mod>[\w.]+)_YouTube_(?P<yt>\d+\.\d+\.\d+)\.ipa$', re.I),
    'YouMod': re.compile(r'^YouMod_(?P<yt>\d+\.\d+\.\d+)_v(?P<mod>[\w.]+)\.ipa$', re.I),
}


def command(*args):
    subprocess.run(args, check=True, cwd=ROOT)


def load_state():
    if STATE.exists():
        state = json.loads(STATE.read_text())
        if not isinstance(state.get('apps'), dict):
            raise ValueError('state.json must contain apps object')
        return state
    return {'apps': {}}


def classify(name):
    for key, pattern in PATTERNS.items():
        match = pattern.fullmatch(name)
        if match:
            return key, match.groupdict()
    return None, None


def ipa_info(path):
    with zipfile.ZipFile(path) as archive:
        candidates = [n for n in archive.namelist() if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', n)]
        if len(candidates) != 1:
            raise ValueError(f'Expected exactly one top-level app Info.plist, found {len(candidates)}')
        info = plistlib.loads(archive.read(candidates[0]))
    bundle = info.get('CFBundleIdentifier')
    version = info.get('CFBundleShortVersionString')
    build = info.get('CFBundleVersion')
    if not all(isinstance(v, str) and v for v in (bundle, version, build)):
        raise ValueError('IPA is missing usable bundle identifier/version/build metadata')
    return bundle, version, build


def sidestore_release_build(message_id):
    """Make a monotonically increasing iOS-compatible build from a Telegram ID.

    Message ID 23827 becomes 238.27.0. The first component stays below
    the documented four-digit maximum until the ID reaches 1,000,000.
    Telegram message IDs increase as new releases are posted to the topic.
    """
    if not 1 <= message_id < 1_000_000:
        raise ValueError(
            f'Telegram message ID {message_id} is outside the supported '
            'CFBundleVersion range; revise the build-number scheme.'
        )
    return f'{message_id // 100}.{message_id % 100}.0'


def repack_ipa_build_version(input_path, output_path, new_build):
    """Change only the main app's CFBundleVersion in an IPA archive.

    This invalidates the IPA's existing code signature. SideStore must re-sign
    the app during installation. No executable or bundled framework is edited.
    """
    plist_pattern = re.compile(r'Payload/[^/]+\.app/Info\.plist')
    changed = 0
    with zipfile.ZipFile(input_path, 'r') as original, zipfile.ZipFile(output_path, 'w') as output:
        output.comment = original.comment
        for member in original.infolist():
            if plist_pattern.fullmatch(member.filename):
                raw = original.read(member)
                info = plistlib.loads(raw)
                info['CFBundleVersion'] = new_build
                fmt = plistlib.FMT_BINARY if raw.startswith(b'bplist00') else plistlib.FMT_XML
                output.writestr(member, plistlib.dumps(info, fmt=fmt, sort_keys=False))
                changed += 1
            elif member.is_dir():
                output.writestr(member, b'')
            else:
                # Stream assets to avoid holding a 100+ MB IPA in memory.
                with original.open(member, 'r') as reader, output.open(member, 'w', force_zip64=True) as writer:
                    shutil.copyfileobj(reader, writer, length=1024 * 1024)
    if changed != 1:
        output_path.unlink(missing_ok=True)
        raise ValueError(f'Expected one app Info.plist for IPA repack, found {changed}')


async def get_group(client):
    # User must join the group in Telegram before running. Invite links are not entity usernames.
    async for dialog in client.iter_dialogs():
        if dialog.name == GROUP_NAME:
            return dialog.entity
    raise RuntimeError(f'Joined Telegram group {GROUP_NAME!r} not found. Join the invite link in the Telegram app first, or override TG_GROUP_NAME.')


async def get_topic(client, group):
    result = await client(GetForumTopicsRequest(peer=group, q=TOPIC_NAME,
        offset_date=0, offset_id=0, offset_topic=0, limit=100))
    exact = [x for x in result.topics if getattr(x, 'title', '').strip().casefold() == TOPIC_NAME.casefold()]
    if len(exact) != 1:
        raise RuntimeError(f'Could not uniquely identify topic {TOPIC_NAME!r}: {[getattr(x, "title", "") for x in result.topics]}')
    return exact[0].id


async def discover(client, group, topic_id):
    """Search just this forum topic, newest first, for IPA documents."""
    found = {}
    offset = 0
    scanned = 0
    while scanned < MAX_MESSAGES and len(found) < len(APPS):
        result = await client(SearchRequest(peer=group, q='', filter=InputMessagesFilterDocument(),
            min_date=None, max_date=None, offset_id=offset, add_offset=0,
            limit=min(100, MAX_MESSAGES - scanned), max_id=0, min_id=0,
            hash=0, top_msg_id=topic_id, from_id=None))
        messages = result.messages
        if not messages:
            break
        for msg in messages:
            scanned += 1
            document = getattr(getattr(msg, 'media', None), 'document', None)
            if not document:
                continue
            for attr in document.attributes:
                name = getattr(attr, 'file_name', None)
                if not name:
                    continue
                key, match = classify(name)
                if key and key not in found:
                    found[key] = (msg, name, match)
                    print(f'Found {key}: {name}, Telegram message {msg.id}')
        new_offset = min(msg.id for msg in messages)
        if new_offset >= offset and offset:
            break
        offset = new_offset
    print(f'Scanned {scanned} topic documents; found: {list(found)}')
    return found


def source_from_state(state, selected_keys=None):
    if selected_keys is None:
        selected_keys = ('YTLite', 'YTKACE', 'YouMod')

    source_names = {
        'YTLite': 'Driftywinds YTLite',
        'YTKACE': 'Driftywinds YTKACE',
        'YouMod': 'Driftywinds YouMod',
    }

    source_name = (
        source_names[selected_keys[0]]
        if len(selected_keys) == 1
        else 'Driftywinds Tweaked YouTube'
    )

    source_icon = (
        APPS[selected_keys[0]]['icon']
        if len(selected_keys) == 1
        else 'source.png'
    )

    seen_bundle_ids = set()
    apps = []

    for key in selected_keys:
        versions = state['apps'].get(key, [])
        if not versions:
            continue

        # Maintain newest-first order; stale apps remain on their own latest version.
        latest = versions[0]

        # A single AltSource may not expose duplicate bundle identifiers.
        if latest['bundleIdentifier'] in seen_bundle_ids:
            print(f'Skipping {key} in this source: shared bundle ID {latest["bundleIdentifier"]}')
            continue

        seen_bundle_ids.add(latest['bundleIdentifier'])

        if any(v['bundleIdentifier'] != latest['bundleIdentifier'] for v in versions):
            raise ValueError(f'{key} changed bundle IDs; migration requires manual review')

        rendered = []
        for v in versions:
            entry = {
                field: v[field]
                for field in (
                    'version',
                    'buildVersion',
                    'date',
                    'downloadURL',
                    'size',
                    'localizedDescription'
                )
            }
            rendered.append(entry)

        apps.append({
            'name': APPS[key]['name'],
            'bundleIdentifier': latest['bundleIdentifier'],
            'developerName': 'Driftywinds (community repack)',
            'subtitle': 'Tweaked YouTube client',
            'localizedDescription': APPS[key]['description'] + ' Unofficial, third-party release.',
            'iconURL': f'https://raw.githubusercontent.com/{REPO}/main/assets/{APPS[key]["icon"]}',
            'versions': rendered,
        })

    return {
        'name': source_name,
        'identifier': 'com.community.driftywinds.youtube' + (
            '.' + selected_keys[0].lower() if len(selected_keys) == 1 else ''
        ),
        'subtitle': 'Automated mirror of selected Telegram topic releases',
        'iconURL': f'https://raw.githubusercontent.com/{REPO}/main/assets/{source_icon}',
        'apps': apps,
        'news': [],
    }


async def main():
    state = load_state()
    async with TelegramClient(StringSession(os.environ['TG_SESSION']),
                              int(os.environ['TG_API_ID']), os.environ['TG_API_HASH']) as client:
        group = await get_group(client)
        topic_id = await get_topic(client, group)
        print(f'Group {GROUP_NAME!r}; topic {TOPIC_NAME!r} ID {topic_id}')
        found = await discover(client, group, topic_id)
        if not found:
            raise RuntimeError('No matching IPA attachments found in the topic')
        with tempfile.TemporaryDirectory() as tmp:
            for key, (msg, filename, match) in found.items():
                prior = state['apps'].get(key, [])
                # The source uses a unique, increasing internal build for EACH
                # variant. Also migrate the currently mirrored YTLite/YouMod
                # attachments (and older YTKACE ones) exactly once.
                desired_build = sidestore_release_build(msg.id)
                if prior and prior[0].get('telegramMessageId') == msg.id:
                    if prior[0].get('buildVersion') == desired_build:
                        print(f'{key}: unchanged')
                        continue
                    print(f'{key}: upgrading previously mirrored release to unique build metadata')

                local = Path(tmp) / filename
                print(f'{key}: downloading {filename}')
                await client.download_media(msg, file=str(local))
                if not local.is_file():
                    raise RuntimeError(f'Telegram download failed for {filename}')
                bundle, version, original_build = ipa_info(local)
                if prior and prior[0]['bundleIdentifier'] != bundle:
                    raise ValueError(
                        f'{key}: bundle ID changed from '
                        f'{prior[0]["bundleIdentifier"]} to {bundle}'
                    )

                build = desired_build
                if original_build != build:
                    # Alter ONLY the main app's CFBundleVersion, never its
                    # CFBundleIdentifier or CFBundleShortVersionString.
                    # The repack invalidates its old signature: SideStore must
                    # re-sign the IPA when installing/updating it.
                    repacked = local.with_name('repacked-' + local.name)
                    repack_ipa_build_version(local, repacked, build)
                    os.replace(repacked, local)
                actual_bundle, actual_version, actual_build = ipa_info(local)
                if (actual_bundle, actual_version, actual_build) != (bundle, version, build):
                    raise ValueError(f'{key}: repacked IPA version verification failed')
                print(f'{key}: build {original_build} -> {build} '
                      f'(YouTube {version}, tweak {match.get("mod", "not in filename")})')

                size = local.stat().st_size
                if size >= 2 * 1024**3:
                    raise ValueError(f'GitHub Releases asset size limit exceeded: {filename}')
                # Use new release tags for all three apps, leaving older,
                # unmodified GitHub Releases untouched and preserving history.
                # Existing YTKACE -ss- tags remain the same.
                tag = f'{key.lower()}-ss-tg-{msg.id}'
                url = f'https://github.com/{REPO}/releases/download/{quote(tag)}/{quote(filename)}'
                description = f'YouTube {match["yt"]}; {key}'
                if match.get('mod'):
                    description += f' {match["mod"]}'
                description += (
                    f'. Mirror of Telegram attachment {filename}; '
                    f'internal build metadata {original_build} -> {build} '
                    'for SideStore update detection'
                )
                # Do not publish state/source until release upload succeeds.
                existing = subprocess.run(
                    ['gh', 'release', 'view', tag, '--repo', REPO, '--json', 'assets',
                     '--jq', '.assets[].name'], capture_output=True, text=True)
                if existing.returncode == 0:
                    if filename not in existing.stdout.splitlines():
                        command('gh', 'release', 'upload', tag, str(local), '--repo', REPO)
                else:
                    command('gh', 'release', 'create', tag, str(local),
                            '--repo', REPO, '--title', f'{key} / YouTube {match["yt"]}',
                            '--notes', description, '--latest=false')
                date = msg.date.astimezone(timezone.utc).date().isoformat()
                item = {
                    'telegramMessageId': msg.id, 'telegramFileName': filename,
                    'bundleIdentifier': bundle, 'version': version,
                    'buildVersion': build, 'date': date, 'downloadURL': url,
                    'size': size, 'localizedDescription': description,
                }
                state['apps'][key] = [item] + [v for v in prior if v['telegramMessageId'] != msg.id]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n')
    SOURCE.write_text(json.dumps(source_from_state(state), indent=2, ensure_ascii=False) + '\n')
    for key, filename in [('YTLite', 'ytlite.json'), ('YTKACE', 'ytkace.json'), ('YouMod', 'youmod.json')]:
        (ROOT / filename).write_text(json.dumps(source_from_state(state, (key,)), indent=2, ensure_ascii=False) + '\n')
    print('Wrote state.json, source.json, ytlite.json, ytkace.json, youmod.json')


if __name__ == '__main__':
    asyncio.run(main())
