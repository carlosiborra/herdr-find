import hashlib
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src' / 'herdr_find'

# sha256 of each vendored helper shared with other plugins.
VENDORED = {
    'theme.py': '601f8c1bc7ab32d7246c6a7adf07e676838242eaec4824686e80cf43eb21579c',
    'terminal.py': '1b8260c746e18eb338f9535f586abfed01aaabea7832135b7362713325711a20',
    'search.py': 'f925011c6200d598de507aecef34e91a707e8658bcbc07ed2078a15496abc408',
    'text.py': 'c9467cc4bd0cd09580f512682d9e20578b4e51414f70212383afbd36b3532db8',
}


class VendoredHelpersTest(unittest.TestCase):
    def test_hashes_match(self):
        for name, expected in VENDORED.items():
            actual = hashlib.sha256((SRC / name).read_bytes()).hexdigest()
            self.assertEqual(
                actual, expected,
                name + ' is a vendored helper shared with other plugins and must be changed '
                'deliberately. If the change is intended, update its hash in tests/test_vendored.py '
                'and mention it in CHANGELOG.md.')


if __name__ == '__main__':
    unittest.main()
