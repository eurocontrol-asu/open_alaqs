from gse_application.model.storage import load_emission_factors_csv, load_gse_csv


def _test_load_gse():
    gse = load_gse_csv("model/database/default_gse.csv")
    assert len(gse) > 0


def _test_load_emission_factors():
    ef = load_emission_factors_csv("model/database/default_emission_factors.csv")
    assert len(ef) > 0
