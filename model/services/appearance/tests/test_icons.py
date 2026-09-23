from django.test import SimpleTestCase

from model.services.appearance import icons, schema

_ORIGINAL_GLYPHS = {
    "person": ("Person", '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>'),
    "organisation": (
        "Organisation",
        '<path d="M4 21V4h10v17M14 9h6v12M8 8h2M8 12h2M8 16h2M4 21h16"/>',
    ),
    "document": ("Document", '<path d="M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6"/>'),
    "database": (
        "Database",
        '<ellipse cx="12" cy="6" rx="7" ry="3"/>'
        '<path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
    ),
    "process": (
        "Process",
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    ),
    "server": (
        "Server",
        '<rect x="3" y="4" width="18" height="6" rx="1"/><rect x="3" y="14" width="18" height="6" rx="1"/>'
        '<path d="M7 7h.01M7 17h.01"/>',
    ),
    "globe": (
        "Globe",
        '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    ),
    "folder": ("Folder", '<path d="M3 6h6l2 2h10v11H3z"/>'),
    "flag": ("Flag", '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>'),
    "shield": ("Shield", '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>'),
    "cube": ("Cube", '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5"/>'),
    "event": (
        "Event",
        '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',
    ),
}


class IconCatalogueTests(SimpleTestCase):

    def test_every_icon_renders_valid_svg_and_data_uri(self):
        for name in icons.NAMES:
            svg = icons.icon_svg(name, "#4C6EF5")
            self.assertTrue(svg.startswith("<svg"), msg=name)
            self.assertTrue(svg.endswith("</svg>"), msg=name)
            self.assertIn("4C6EF5", svg, msg=name)

            data_uri = icons.icon_data_uri(name, "#4C6EF5")
            self.assertTrue(data_uri.startswith("data:image/svg+xml;charset=utf-8,"), msg=name)

    def test_new_icon_keys_are_valid_style_choices(self):
        for name in ("team", "tractor", "api", "lock", "spreadsheet", "barn"):
            self.assertEqual(schema.clean_value(schema.OBJECT, "icon", name), name)

    def test_existing_icons_are_unchanged(self):
        for name, expected in _ORIGINAL_GLYPHS.items():
            self.assertEqual(icons._GLYPHS[name], expected, msg=name)

    def test_no_duplicate_keys_or_labels(self):
        labels = [label for label, _body in icons._GLYPHS.values()]
        self.assertEqual(len(icons.NAMES), len(set(icons.NAMES)))
        self.assertEqual(len(labels), len(set(labels)))

    def test_catalogue_has_grown_with_a_balanced_new_selection(self):
        self.assertGreaterEqual(len(icons.NAMES), 12 + 25)
        self.assertLessEqual(len(icons.NAMES), 12 + 30)
