"""XML contract: state precedence, empty rows, context binding, overlays, and shared surfaces.

Failures: ambiguous states; selected hides progress/error; false completion for partial;
normal rows gain chrome; metadata reads another container; status replaces play overlays;
shared row variants omit status; playback source labels or artist separators become stale.
"""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def xml(name):
    return ET.parse(ROOT / '1080i' / name).getroot()


def condition(value, state, selected):
    value = value.replace('$PARAM[state]', 'state').replace('$PARAM[download_selected]', 'selected')
    values = {'state': state, 'selected': selected}
    value = re.sub(r'String.IsEqual\((state|selected),([^)]*)\)',
                   lambda match: str(values[match[1]] == match[2]), value)
    value = re.sub(r'String.IsEmpty\((state|selected)\)',
                   lambda match: str(not values[match[1]]), value)
    value = value.replace('!', ' not ').replace('+', ' and ').replace('|', ' or ')
    value = value.replace('[', '(').replace(']', ')')
    return eval(value, {'__builtins__': {}}, {})


class SpotifyDownloadStatusTests(unittest.TestCase):
    def status(self):
        node = xml('Includes_Objects.xml').find("include[@name='Object_SpotifyDownloadStatus']")
        self.assertIsNotNone(node, 'shared secondary status required')
        return node

    def test_state_matrix_and_selected_precedence(self):
        group = self.status().find('definition/control')
        labels = group.findall('control')
        expected = {'queued': '31891', 'downloading': '31892', 'complete': '31893',
                    'partial': '31894', 'error': '31895', '': '31890'}
        for state, selected in [(s, flag) for s in expected for flag in ('', 'true')]:
            rendered = [node.findtext('label') for node in labels
                        if condition(node.findtext('visible'), state, selected)]
            if not state and not selected:
                self.assertEqual([], rendered)
            else:
                self.assertEqual(1, len(rendered), (state, selected, rendered))
                self.assertIn('$LOCALIZE[' + expected[state] + ']', rendered[0])
        self.assertFalse(any(condition(node.findtext('visible'), 'unknown', '') for node in labels))

    def test_status_is_passive_and_keeps_playing_overlays(self):
        status = self.status()
        self.assertEqual({'label', 'group'}, {node.get('type') for node in status.iter('control')})
        self.assertNotIn('IsPlaying', ET.tostring(status, encoding='unicode'))
        overlay = xml('Includes_Images.xml').find("variable[@name='Image_Overlay_List']/value")
        self.assertEqual('ListItem.IsPlaying', overlay.get('condition'))
        self.assertEqual('indicator/play.png', overlay.text)
        for name in ('Object_Indicator', 'Object_Indicator_List'):
            node = xml('Includes_Objects.xml').find(f"include[@name='{name}']")
            self.assertNotIn('Spotify.Download', ET.tostring(node, encoding='unicode'))

    def test_all_shared_row_and_tile_label_surfaces_use_status(self):
        root = xml('Includes_Layouts.xml')
        for name in ('Layout_MediaList_Detailed', 'Layout_Labels'):
            node = root.find(f"include[@name='{name}']")
            self.assertIsNotNone(node.find(".//include[@content='Object_SpotifyDownloadStatus']"), name)
        standard = root.find("include[@name='Layout_MediaList']")
        opted_in = standard.findall(".//include[@content='Object_InfoCircle']/param[@name='spotify_status']")
        self.assertEqual(['true', 'true'], [node.text for node in opted_in])
        circle = xml('Includes_Objects.xml').find("include[@name='Object_InfoCircle']")
        self.assertIsNotNone(circle.find(".//include[@content='Object_SpotifyDownloadStatus']"))
        for node in standard.findall('.//label'):
            if 'Label_MediaList_Year' in (node.text or '') or 'Label_MediaList_Rating' in (node.text or ''):
                parent = next(parent for parent in standard.iter() if node in list(parent))
                self.assertIn('!$EXP[Exp_SpotifyDownloadStatus]', ' '.join(v.text or '' for v in parent.findall('visible')))

    def test_info_status_preserves_container_and_unknown_collection_types(self):
        info = xml('Includes_Info.xml').find("include[@name='Info_Line']")
        node = info.find(".//include[@content='Object_SpotifyDownloadStatus']")
        self.assertIsNotNone(node)
        self.assertEqual('$PARAM[container]$PARAM[listitem].Property(Spotify.DownloadState)',
                         node.findtext("param[@name='state']"))
        self.assertEqual('$PARAM[container]$PARAM[listitem].Property(Spotify.DownloadSelected)',
                         node.findtext("param[@name='download_selected']"))
        self.assertIn('Spotify.Download', ' '.join(v.text or '' for v in info.findall('definition/control/visible')))

    def test_info_status_follows_metadata_with_a_conditional_dot_divider(self):
        line = xml('Includes_Info.xml').find("include[@name='Info_Line']")
        children = list(line.find('definition/control/control[@type="grouplist"]'))
        self.assertEqual('Object_SpotifyDownloadStatus', children[-1].get('content'))
        self.assertEqual('Info_Line_Divider', children[-2].get('content'))
        visible = children[-2].findtext("param[@name='visible']")
        self.assertIn('$PARAM[show_meta]', visible)
        self.assertIn('Spotify.DownloadState', visible)
        self.assertIn('.Year', visible)

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

    def test_progress_is_optional_and_zero_is_visible(self):
        nodes = self.status().findall('definition/control/control')
        label = next(node.findtext('label') for node in nodes
                     if condition(node.findtext('visible'), 'downloading', 'true'))
        self.assertIn('$INFO[$PARAM[progress], ,%]', label)
        for progress, expected in (('', '$LOCALIZE[31892]'), ('0', '$LOCALIZE[31892] 0%'),
                                   ('47', '$LOCALIZE[31892] 47%'), ('100', '$LOCALIZE[31892] 100%')):
            rendered = label.replace('$INFO[$PARAM[progress], ,%]', f' {progress}%' if progress else '')
            self.assertEqual(expected, rendered)

    def test_seven_shared_music_row_families_reach_the_tile_status(self):
        rows = xml('Includes_Lists.xml')
        layouts = xml('Includes_Layouts.xml')
        for family, layout in (('Poster', 'Poster'), ('Card', 'Card'), ('Landscape', 'Landscape'),
                               ('Board', 'Landscape'), ('Banner', 'Banner'), ('Circle', 'Circle'),
                               ('Square', 'Square')):
            row = rows.find(f"include[@name='List_{family}_Row']")
            targets = [node.text for node in row.findall(".//param[@name='itemlayout_include']")]
            self.assertIn('Layout_' + layout, targets, family)
            target = layouts.find(f"include[@name='Layout_{layout}']")
            self.assertIsNotNone(target.find(".//include[@content='Layout_Labels']"), family)
        labels = layouts.find("include[@name='Layout_Labels']")
        self.assertIsNotNone(labels.find(".//include[@content='Object_SpotifyDownloadStatus']"))

    def test_per_row_state_uses_runtime_visibility(self):
        for name in ('Includes_Layouts.xml', 'Includes_Objects.xml', 'Includes_Info.xml'):
            for node in xml(name).iter('include'):
                self.assertNotIn('Exp_SpotifyDownloadStatus', node.get('condition', ''), name)
                self.assertNotIn('Spotify.Download', node.get('condition', ''), name)

    def test_english_labels_are_short_and_distinct(self):
        text = (ROOT / 'language/resource.language.en_gb/strings.po').read_text()
        for number, label in enumerate(('Selected', 'Queued', 'Downloading', 'Downloaded',
                                        'Partly downloaded', 'Download failed', 'Local playback',
                                        'Spotify stream'), 31890):
            self.assertIn(f'msgctxt "#{number}"\nmsgid "{label}"', text)


if __name__ == '__main__':
    unittest.main()
