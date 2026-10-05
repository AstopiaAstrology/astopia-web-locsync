import unittest
from webloc.core import check


class RawTests(unittest.TestCase):
    def test_explicit_html_and_credit_contracts(self):
        policy = {'html': 'html-color', 'credit': 'credit-token'}
        check({'html': '<p><span style="color: rgb(255, 255, 255);">Text</span></p>',
               'credit': '<credit> free message'}, raw_messages=policy)
        for message in ['<script>x</script>', '<p onclick="x">x</p>', '<p>x',
                        '<p><span>x</p></span>', '<p>{name}</p>', '<p><', '<p><!--x--></p>']:
            with self.assertRaises(ValueError):
                check({'html': message}, raw_messages=policy)
        for message in ['none', '<credit><credit>', '<credit>{name}', '<credit></credit>']:
            with self.assertRaises(ValueError):
                check({'credit': message}, raw_messages=policy)

    def test_no_global_icu_bypass(self):
        with self.assertRaises(ValueError): check({'ordinary': '<credit>'})
        with self.assertRaises(ValueError): check({'ordinary': '{broken'}, raw_messages={'html': 'html-color'})
        with self.assertRaises(ValueError): check({'ordinary': '{name}'}, {'ordinary': '{other}'})
