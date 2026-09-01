from __future__ import annotations

from qgarage.core.search import fuzzy_matches


def test_fuzzy_matches_ignores_case_punctuation_and_spacing():
    assert fuzzy_matches("DEM-SLOPE", ["dem_slope", "Calculates terrain slope"])


def test_fuzzy_matches_allows_close_and_abbreviated_terms():
    assert fuzzy_matches("slop cal", ["DEM Slope Calculator"])


def test_fuzzy_matches_rejects_unrelated_terms():
    assert not fuzzy_matches("watershed", ["DEM Slope Calculator", "raster"])