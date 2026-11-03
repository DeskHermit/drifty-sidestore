"""Telegram topic -> GitHub Release assets -> SideStore source.

Requires joined Telegram user account, GH_TOKEN, GH_REPO, TG_API_ID,
TG_API_HASH, TG_SESSION. The repo's workflow commits state.json/source.json.
"""
import asyncio
import json
import os
import plistlib
import re
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
            entry = {field: v[field] for field in ('version', 'buildVersion', 'date', 'downloadURL', 'size', 'localizedDescription')}
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
        'name': 'Driftywinds Tweaked YouTube',
        'identifier': 'com.community.driftywinds.youtube' + ('.' + selected_keys[0].lower() if len(selected_keys) == 1 else ''),
        'subtitle': 'Automated mirror of selected Telegram topic releases',
        'iconURL': f'https://raw.githubusercontent.com/{REPO}/main/assets/source.png',
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
                # Message id is stable within the group and prevents redundant downloads.
                if prior and prior[0].get('telegramMessageId') == msg.id:
                    print(f'{key}: unchanged')
                    continue
                local = Path(tmp) / filename
                print(f'{key}: downloading {filename}')
                await client.download_media(msg, file=str(local))
                if not local.is_file():
                    raise RuntimeError(f'Telegram download failed for {filename}')
                size = local.stat().st_size
                if size >= 2 * 1024**3:
                    raise ValueError(f'GitHub Releases asset size limit exceeded: {filename}')
                bundle, version, build = ipa_info(local)
                if prior and prior[0]['bundleIdentifier'] != bundle:
                    raise ValueError(f'{key}: bundle ID changed from {prior[0]["bundleIdentifier"]} to {bundle}')
                # Updates require changes to the version/build pair. If upstream reused both,
                # don't silently replace a previously installed release with ambiguous metadata.
                if prior and (prior[0]['version'], prior[0]['buildVersion']) == (version, build):
                    raise ValueError(f'{key}: upstream IPA {filename} changed, but Info.plist version/build are still {version}/{build}; manually fix the source/update policy')
                tag = f'{key.lower()}-tg-{msg.id}'
                url = f'https://github.com/{REPO}/releases/download/{quote(tag)}/{quote(filename)}'
                description = f'YouTube {match["yt"]}; {key}'
                if match.get('mod'):
                    description += f' {match["mod"]}'
                description += f'. Original Telegram attachment: {filename}'
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
