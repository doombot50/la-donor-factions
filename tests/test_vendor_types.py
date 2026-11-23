"""Payee typing: the cases that once put a restaurant or a canvasser in the graph.

    python3 -m unittest discover -s tests
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from vendor_types import classify, desc_bucket, name_type


def typed(key, **desc):
    return classify(key, desc, frozenset({'GIL PINAC'}))


class NameRules(unittest.TestCase):
    def test_stations_and_papers_are_media(self):
        for k in ('WGNO TV', 'WGNO', 'KMDL-FM', 'WWL AM FM', 'AMPERSAND',
                  'MINDEN PRESS HERALD', 'COX CABLE', 'OUTFRONT MEDIA'):
            self.assertEqual(name_type(k), 'media', k)

    def test_call_sign_shaped_words_are_not_stations(self):
        # WINE (Total Wine) and KING (Smoothie King) are not radio stations
        self.assertEqual(name_type('WINE'), 'commodity')
        self.assertIsNone(name_type('KING'))

    def test_errands_are_not_operatives(self):
        for k, t in (('RUTH S CHRIS STEAK HOUSE', 'commodity'), ('TOTAL WINE', 'commodity'),
                     ('IRS', 'civic'), ('UNITED STATES TREASURY', 'civic'),
                     ('BOARD OF ETHICS', 'civic'), ('LOUISIANA SENATE', 'civic'),
                     ('HANCOCK WHITNEY', 'commodity'), ('UBER TECHNOLOGIES', 'commodity'),
                     ('DRIFTWOOD PARK CIVIC', 'civic')):
            self.assertEqual(name_type(k), t, k)

    def test_people_named_like_businesses_are_not_caught(self):
        # an over-broad pattern once swept up surnames: Hampton, Chase, Bourgeois
        for k in ('ANTRONIO HAMPTON', 'CHASE BOUDREAUX', 'HANNIS T BOURGEOIS', 'TARGETPOINT'):
            self.assertIsNone(name_type(k), k)


class People(unittest.TestCase):
    def test_canvasser_is_anonymous_field(self):
        self.assertEqual(typed('WANDA WILLIAMS', field=2300, blank=900), 'field')

    def test_unexplained_person_stays_anonymous(self):
        self.assertEqual(typed('JANE DOE', blank=500), 'field')

    def test_named_professional_is_operative(self):
        self.assertEqual(typed('CHRISTY CANNELLA', operative=90000, field=4000), 'operative')

    def test_candidate_paid_as_person_is_a_contribution(self):
        self.assertEqual(typed('GIL PINAC', operative=500, blank=9000), 'civic')
        self.assertEqual(typed('YVONNE DORSEY', political=3000, operative=200), 'civic')


class Descriptions(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(desc_bucket('ELECTION DAY WORKER'), 'field')
        self.assertEqual(desc_bucket('CAMPAIGN CONTRIBUTION'), 'political')
        self.assertEqual(desc_bucket('Direct mail'), 'operative')
        self.assertEqual(desc_bucket('Dinner meeting'), 'commodity')
        self.assertEqual(desc_bucket(''), 'blank')


if __name__ == '__main__':
    unittest.main()
