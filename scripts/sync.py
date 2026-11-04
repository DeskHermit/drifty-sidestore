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

