"""XML contract: download badge states, passive art overlay, restored labels.

Failures: ambiguous badge colors; badge on unflagged rows; badge replacing play
overlays or artist labels; shared row/tile surfaces missing the badge; status
text returning to list or info layouts; playback source separators going stale.
"""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def xml(name):
    return ET.parse(ROOT / '1080i' / name).getroot()


def condition(value, state, selected, *, ready='', ids=None, live=None):
    values = {'state': state, 'download_selected': selected,
              **dict.fromkeys(('downloadid', 'trackid', 'playlistid', 'albumid'), ''),
              **(ids or {})}
    for name, content in values.items():
        value = value.replace(f'$PARAM[{name}]', repr(content))
    for name in ('Complete', 'Active', 'Error', 'Ready'):
        content = ready if name == 'Ready' else (live or {}).get(name, '')
        value = value.replace(f'Window(Home).Property(Spotify.Badge{name})', repr(content))
    value = re.sub(r'(?<=[(,])(state|selected)(?=[,)])',
                   lambda match: repr(state if match[1] == 'state' else selected), value)
    value = value.replace('String.Contains(', 'contains(')
    value = value.replace('String.IsEqual(', 'equal(').replace('String.IsEmpty(', 'empty(')
    value = re.sub(r'(?<=,)([a-z]+)(?=\))', r"'\1'", value)
    value = value.replace('!', ' not ').replace('+', ' and ').replace('|', ' or ')
    value = value.replace('[', '(').replace(']', ')')
    return eval(value, {'__builtins__': {}}, {
        'contains': lambda haystack, needle: needle.lower() in haystack.lower(),
        'equal': lambda left, right: left.lower() == right.lower(),
        'empty': lambda text: not text,
    })


class SpotifyDownloadBadgeTests(unittest.TestCase):
    def badge(self):
        node = xml('Includes_Objects.xml').find("include[@name='Object_SpotifyDownloadBadge']")
        self.assertIsNotNone(node, 'shared download badge required')
        return node

    def badge_images(self):
        badge = self.badge()
        helper = badge.find("definition/include[@content='Object_SpotifyDownloadBadge_States']")
        self.assertIsNotNone(helper)
        node = xml('Includes_Objects.xml').find("include[@name='Object_SpotifyDownloadBadge_States']")
        params = {param.get('name'): param.text for param in helper.findall('param')}
        images = node.findall('definition/control/control')
        for image in images:
            visible = image.find('visible')
            for name, value in params.items():
                visible.text = visible.text.replace(f'$PARAM[{name}]', value)
        return images

    def assert_badge(self, expected, state='', selected='', **kwargs):
        images = self.badge_images()
        rendered = [node.findtext('colordiffuse') for node in images
                    if node.findtext('texture') == 'common/circle.png'
                    and condition(node.findtext('visible'), state, selected, **kwargs)]
        arrows = [node for node in images if 'arrow-up-240' in (node.findtext('texture') or '')]
        self.assertEqual([] if expected is None else [expected], rendered)
        arrow_visible = condition(arrows[0].findtext('visible'), state, selected, **kwargs)
        self.assertEqual(expected is not None, bool(arrow_visible))

    def test_live_state_replaces_stale_rows(self):
        for identity in ('downloadid', 'trackid', 'playlistid', 'albumid'):
            for stale, selected in (('complete', ''), ('error', ''), ('', 'true')):
                with self.subTest(identity=identity, stale=stale, selected=selected):
                    self.assert_badge('FF707070', stale, selected, ready='true',
                                      ids={identity: 'track123'}, live={'Active': ',track123,'})
                    self.assert_badge(None, stale, selected, ready='true', ids={identity: 'track123'})

    def test_liked_songs_and_local_collections_use_generic_identity(self):
        for identity in ('songs', 'local-collection'):
            for status, color in (('Complete', 'FF1DB954'), ('Active', 'FF707070'), ('Error', 'FFE22134')):
                with self.subTest(identity=identity, status=status):
                    self.assert_badge(color, ready='true', ids={'downloadid': identity},
                                      live={status: f',{identity},'})

    def test_row_fallback_before_ready_or_without_identity(self):
        for ready, ids in (('', {'trackid': 'track123'}), ('false', {'downloadid': 'songs'}), ('true', {})):
            self.assert_badge('FF1DB954', 'complete', ready=ready, ids=ids, live={'Active': ',track123,songs,'})
            self.assert_badge('FFE22134', 'error', ready=ready, ids=ids)
            self.assert_badge('FF707070', selected='true', ready=ready, ids=ids)
            self.assert_badge(None, ready=ready, ids=ids, live={'Complete': ',track123,songs,'})

    def test_generic_identity_has_priority_over_legacy_identity(self):
        self.assert_badge('FF707070', 'complete', ready='true',
                          ids={'downloadid': 'songs', 'playlistid': 'old'},
                          live={'Complete': ',old,', 'Active': ',songs,'})

    def test_badge_color_matrix_and_arrow(self):
        images = self.badge_images()
        circles = [node for node in images if (node.findtext('texture') or '') == 'common/circle.png']
        arrows = [node for node in images if 'arrow-up-240' in (node.findtext('texture') or '')]
        self.assertEqual(3, len(circles))
        self.assertEqual(1, len(arrows))
        self.assertEqual('true', arrows[0].find('texture').get('flipy'))
        expected = {'complete': 'FF1DB954', 'queued': 'FF707070', 'downloading': 'FF707070',
                    'partial': 'FF707070', 'error': 'FFE22134', '': 'FF707070'}
        for state, selected in [(s, flag) for s in expected for flag in ('', 'true')]:
            rendered = [node.findtext('colordiffuse') for node in circles
                        if condition(node.findtext('visible'), state, selected)]
            arrow = condition(arrows[0].findtext('visible'), state, selected)
            if not state and not selected:
                self.assertEqual([], rendered)
                self.assertFalse(arrow)
            else:
                self.assertEqual([expected[state]], rendered, (state, selected))
                self.assertTrue(arrow)
        self.assertFalse(any(condition(node.findtext('visible'), 'unknown', '') for node in images))

    def test_badge_matches_live_window_sets_with_empty_needle_guards(self):
        text = ET.tostring(self.badge(), encoding='unicode')
        for name in ('Spotify.BadgeComplete', 'Spotify.BadgeActive', 'Spotify.BadgeError'):
            self.assertIn(f'Window(Home).Property({name})', text)
        self.assertIn('Window(Home).Property(Spotify.BadgeReady)', text)
        self.assertEqual('ListItem.Property(Spotify.DownloadId)',
                         self.badge().findtext("param[@name='downloadid']"))
        for param in ('downloadid', 'trackid', 'playlistid', 'albumid'):
            self.assertIn(f'!String.IsEmpty($PARAM[{param}])', text)
        objects = (ROOT / '1080i/Includes_Objects.xml').read_text()
        self.assertNotIn('Exp_SpotifyDownloadStatus]</visible>\n                    </include>\n                </control>\n                <nested', objects)

    def test_badge_is_passive_and_keeps_playing_overlays(self):
        badge = xml('Includes_Objects.xml').find("include[@name='Object_SpotifyDownloadBadge_States']")
        self.assertEqual({'image', 'group'}, {node.get('type') for node in badge.iter('control')})
        self.assertNotIn('IsPlaying', ET.tostring(badge, encoding='unicode'))
        self.assertNotIn('<label', ET.tostring(badge, encoding='unicode'))
        overlay = xml('Includes_Images.xml').find("variable[@name='Image_Overlay_List']/value")
        self.assertEqual('ListItem.IsPlaying', overlay.get('condition'))
        self.assertEqual('indicator/play.png', overlay.text)

    def test_no_status_text_or_hidden_labels_anywhere(self):
        for name in ('Includes_Layouts.xml', 'Includes_Objects.xml', 'Includes_Info.xml'):
            text = (ROOT / '1080i' / name).read_text()
            self.assertNotIn('Object_SpotifyDownloadStatus', text, name)
            self.assertNotIn('!$EXP[Exp_SpotifyDownloadStatus]', text, name)
        info = xml('Includes_Info.xml').find("include[@name='Info_Line']")
        self.assertNotIn('Spotify.Download', ET.tostring(info, encoding='unicode'))

    def test_shared_surfaces_carry_the_badge(self):
        objects = xml('Includes_Objects.xml')
        circle = objects.find("include[@name='Object_InfoCircle']")
        badge = circle.find(".//include[@content='Object_SpotifyDownloadBadge']")
        self.assertIsNotNone(badge)
        self.assertEqual('$PARAM[spotify_status]', badge.get('condition'))
        layouts = xml('Includes_Layouts.xml')
        standard = layouts.find("include[@name='Layout_MediaList']")
        opted_in = standard.findall(".//include[@content='Object_InfoCircle']/param[@name='spotify_status']")
        self.assertEqual(['true', 'true'], [node.text for node in opted_in])
        detailed = layouts.find("include[@name='Layout_MediaList_Detailed']")
        self.assertIsNotNone(detailed.find(".//include[@content='Object_Layout_Image_Rectangle']"))

    def test_seven_shared_music_row_families_reach_the_badge(self):
        rows = xml('Includes_Lists.xml')
        layouts = xml('Includes_Layouts.xml')
        rectangle = xml('Includes_Objects.xml').find("include[@name='Object_Layout_Image_Rectangle']")
        rectangle_badge = rectangle.find(".//include[@content='Object_SpotifyDownloadBadge']")
        self.assertIsNotNone(rectangle_badge)
        self.assertEqual('$PARAM[listitem].Property(Spotify.DownloadId)',
                         rectangle_badge.findtext("param[@name='downloadid']"))
        for family, layout in (('Poster', 'Poster'), ('Card', 'Card'), ('Landscape', 'Landscape'),
                               ('Board', 'Landscape'), ('Banner', 'Banner'), ('Circle', 'Circle'),
                               ('Square', 'Square')):
            row = rows.find(f"include[@name='List_{family}_Row']")
            targets = [node.text for node in row.findall(".//param[@name='itemlayout_include']")]
            self.assertIn('Layout_' + layout, targets, family)
            target = layouts.find(f"include[@name='Layout_{layout}']")
            art = {node.get('content') for node in target.findall('.//include')}
            self.assertTrue({'Object_Layout_Image_Icon', 'Object_Layout_Image_Rectangle'} & art, family)

    def test_per_row_state_uses_runtime_visibility(self):
        for name in ('Includes_Layouts.xml', 'Includes_Objects.xml', 'Includes_Info.xml'):
            for node in xml(name).iter('include'):
                self.assertNotIn('Exp_SpotifyDownloadStatus', node.get('condition', ''), name)
                self.assertNotIn('Spotify.Download', node.get('condition', ''), name)

    def test_playback_source_transitions_preserve_artist_separators(self):
        root = xml('Includes_OSD.xml')
        osd = root.find("include[@name='OSD_TitleDetails']")
        labels = osd.findall(".//include[@content='Info_Line_Label']")
        sources = [node for node in labels
                   if not node.findtext("param[@name='label']").startswith('$INFO[')]
        self.assertEqual(1, len(sources), 'one mutually exclusive source label region')
        source = sources[0]
        artist = next(node for node in labels
                      if node.findtext("param[@name='label']") == '$INFO[$PARAM[listitem].Artist]')
        self.assertEqual('false', source.findtext("param[@name='show_divider']"))
        source_property = 'Window(Home).Property(Spotify.CurrentTrackPlaybackSource)'
        for state, expected in (('local', '$LOCALIZE[31896]'), ('stream', '$LOCALIZE[31897]'),
                                ('', ''), ('unknown', ''), ('stream', '$LOCALIZE[31897]'),
                                ('local', '$LOCALIZE[31896]'), ('', '')):
            with self.subTest(source=state):
                def active(expression):
                    return condition(expression.replace(source_property, 'state'), state, '')

                label = source.findtext("param[@name='label']")
                if label.startswith('$VAR['):
                    variable = root.find(f"variable[@name='{label[5:-1]}']")
                    self.assertIsNotNone(variable)
                    label = next((node.text or '' for node in variable.findall('value')
                                  if node.get('condition') is None or active(node.get('condition'))), '')
                visible = active(source.findtext("param[@name='visible']"))
                self.assertEqual(expected, label if visible else '')
                self.assertEqual(bool(expected), visible)
                for artist_name, album_artist in (('Artist', ''), ('', 'Album artist'), ('', '')):
                    artist_visible = condition(artist.findtext("param[@name='visible']")
                                               .replace('$PARAM[listitem].AlbumArtist', 'selected')
                                               .replace('$PARAM[listitem].Artist', 'state'),
                                               artist_name, album_artist)
                    divider_visible = artist_visible and active(artist.findtext("param[@name='show_divider']"))
                    self.assertEqual(bool(expected and (artist_name or album_artist)), divider_visible)

    def test_english_labels_are_short_and_distinct(self):
        text = (ROOT / 'language/resource.language.en_gb/strings.po').read_text()
        for number, label in enumerate(('Selected', 'Queued', 'Downloading', 'Downloaded',
                                        'Partly downloaded', 'Download failed', 'Local playback',
                                        'Spotify stream'), 31890):
            self.assertIn(f'msgctxt "#{number}"\nmsgid "{label}"', text)


if __name__ == '__main__':
    unittest.main()
