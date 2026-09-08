"""Site weather: reuse values safely, fetch only gaps, never invent coverage."""
import importlib
import json

import pandas as pd
import pytest


def api():
    try:
        return importlib.import_module("src.weather_processing.site_weather")
    except ModuleNotFoundError:
        pytest.fail("Site-weather reuse/download workflow is not implemented")


def inventory(tmp_path, names=("Example vineyard",)):
    path = tmp_path / "inventory.csv"
    pd.DataFrame([dict(site_uid=f"France|france_tempo|{i}", site_name=name,
                       country="France", source="france_tempo", site_id=str(i),
                       lat=44., lon=4., first_year=2001, last_year=2001)
                  for i, name in enumerate(names)]).to_csv(path, index=False)
    return path


def test_inventory_windows_include_previous_calendar_year_and_safe_names(tmp_path):
    mod = api()
    sites = mod.load_inventory(inventory(tmp_path, ("Example vineyard", "A/B: C")))
    assert sites[0].start == pd.Timestamp("2000-01-01")
    assert sites[0].end == pd.Timestamp("2001-12-31")
    assert sites[0].filename == "Example vineyard.csv"
    assert sites[1].filename == "A_B_ C.csv"


@pytest.mark.parametrize("names", [("Same", "same"), ("A/B", "A:B"), ("",)])
def test_ambiguous_or_empty_filenames_are_rejected(tmp_path, names):
    with pytest.raises(ValueError):
        api().load_inventory(inventory(tmp_path, names))


def test_missing_windows_split_at_year_boundaries_and_keep_leap_day():
    mod = api()
    have = pd.Series([1., 2.], index=pd.to_datetime(["1999-12-31", "2000-01-02"]))
    assert mod.missing_windows(have, pd.Timestamp("1999-12-30"), pd.Timestamp("2000-03-01")) == [
        (pd.Timestamp("1999-12-30"), pd.Timestamp("1999-12-30")),
        (pd.Timestamp("2000-01-01"), pd.Timestamp("2000-01-01")),
        (pd.Timestamp("2000-01-03"), pd.Timestamp("2000-03-01"))]


def test_reuse_raw_kelvin_exports_deduplicates_and_ignores_indexes(tmp_path):
    mod = api()
    sites = mod.load_inventory(inventory(tmp_path))
    local = tmp_path / "gee"
    local.mkdir()
    pd.DataFrame({"site_uid": [sites[0].uid] * 3,
                  "weather_date": ["2000-01-01", "2000-01-01", "2000-01-02"],
                  "temperature_2m": [273.15, 273.15, 283.15]}).to_csv(local / "daily.csv", index=False)
    pd.DataFrame({"weather_id": ["index only"], "year": [2000]}).to_csv(local / "index.csv", index=False)
    cache, audit = mod.read_local([local], sites)
    assert cache[sites[0].uid].tolist() == pytest.approx([0, 10])
    assert len(audit["used_files"]) == 1
    assert len(audit["ignored_files"]) == 1


def test_two_column_files_match_site_name_and_keep_celsius(tmp_path):
    mod = api()
    sites = mod.load_inventory(inventory(tmp_path))
    local = tmp_path / "gee"
    local.mkdir()
    pd.DataFrame({"Date": ["2000-02-29"], "Tmean": [4.5]}).to_csv(local / sites[0].filename, index=False)
    cache, _ = mod.read_local([local], sites)
    assert cache[sites[0].uid].loc["2000-02-29"] == 4.5


def test_conflicting_reused_values_are_not_silently_selected(tmp_path):
    mod = api()
    sites = mod.load_inventory(inventory(tmp_path))
    local = tmp_path / "gee"
    local.mkdir()
    pd.DataFrame({"site_uid": [sites[0].uid] * 2, "Date": ["2000-01-01"] * 2,
                  "Tmean": [1., 2.]}).to_csv(local / "daily.csv", index=False)
    with pytest.raises(ValueError, match="Conflicting"):
        mod.read_local([local], sites)


def test_source_qualified_ids_prevent_cross_country_matches(tmp_path):
    mod = api()
    sites = mod.load_inventory(inventory(tmp_path))
    local = tmp_path / "gee"
    local.mkdir()
    pd.DataFrame({"country": ["Germany", "France"], "source": ["dwd", "france_tempo"],
                  "site_id": ["0", "0"], "weather_date": ["2000-01-01"] * 2,
                  "temperature_2m_c": [99., 5.]}).to_csv(local / "daily.csv", index=False)
    cache, _ = mod.read_local([local], sites)
    assert cache[sites[0].uid].tolist() == [5.]


def test_ee_payload_converts_kelvin_and_keeps_masked_values_missing():
    mod = api()
    payload = [["id", "longitude", "latitude", "time", "temperature_2m"],
               ["a", 4., 44., 946684800000, 273.15],
               ["b", 4., 44., 946771200000, None]]
    result = mod.parse_ee_rows(payload)
    assert result.index.tolist() == [pd.Timestamp("2000-01-01")]
    assert result.tolist() == [0.]


def test_run_reuses_existing_days_and_fetches_only_available_gap(tmp_path):
    mod = api()
    path = inventory(tmp_path)
    local = tmp_path / "gee"
    local.mkdir()
    pd.DataFrame({"Date": ["2000-01-01"], "Tmean": [3.]}).to_csv(local / "Example vineyard.csv", index=False)
    # Only the external Earth Engine transport is substituted; matching, coverage,
    # persistence and Celsius conversion contracts run through production code.
    class Provider:
        first_date = pd.Timestamp("1950-01-02")
        last_date = pd.Timestamp("2000-01-03")

        def fetch(self, site, start, end):
            assert site.uid == "France|france_tempo|0"
            assert (start, end) == (pd.Timestamp("2000-01-02"), pd.Timestamp("2000-01-03"))
            return pd.Series([4., 5.], index=pd.date_range(start, end))

    out = tmp_path / "out"
    summary = mod.run(path, [local], out, provider=Provider())
    result = pd.read_csv(out / "Example vineyard.csv")
    assert result.columns.tolist() == ["Date", "Tmean"]
    assert result.Date.tolist() == ["2000-01-01", "2000-01-02", "2000-01-03"]
    assert result.Tmean.tolist() == [3., 4., 5.]
    assert summary[0]["n_reused"] == 1 and summary[0]["n_downloaded"] == 2
    assert summary[0]["status"] == "incomplete"
    assert summary[0]["n_missing"] == 728
    # Offline rerun preserves every previously obtained value without fetching.
    before = (out / "Example vineyard.csv").read_bytes()
    mod.run(path, [local], out)
    assert (out / "Example vineyard.csv").read_bytes() == before


def test_offline_no_values_creates_audit_not_empty_weather_files(tmp_path):
    mod = api()
    out = tmp_path / "out"
    result = mod.run(inventory(tmp_path), [], out)
    assert result[0]["n_missing"] == 731
    assert result[0]["status"] == "missing"
    assert not (out / "Example vineyard.csv").exists()
    assert (out / "metadata" / "manifest.csv").is_file()
    assert json.loads((out / "metadata" / "run.json").read_text())["n_sites"] == 1


def test_long_unicode_site_names_fit_filesystem_limits_without_colliding():
    mod = api()
    first = mod.safe_filename("葡萄" * 130 + "a")
    second = mod.safe_filename("葡萄" * 130 + "b")
    assert first != second
    assert len(first.encode()) <= 255
    assert first.endswith(".csv")


def test_limited_rerun_ignores_other_site_outputs(tmp_path):
    mod = api()
    path = inventory(tmp_path, ("Site A", "Site B"))
    out = tmp_path / "out"
    out.mkdir()
    for name in ("Site A", "Site B"):
        pd.DataFrame({"Date": ["2000-01-01"], "Tmean": [3.]}).to_csv(out / f"{name}.csv", index=False)
    other_before = (out / "Site B.csv").read_bytes()
    result = mod.run(path, [], out, limit=1)
    assert result[0]["n_reused"] == 1
    assert (out / "Site B.csv").read_bytes() == other_before


def test_existing_destination_with_extra_dates_is_not_truncated(tmp_path):
    mod = api()
    path = inventory(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    destination = out / "Example vineyard.csv"
    pd.DataFrame({"Date": ["1999-12-31", "2000-01-01"], "Tmean": [2., 3.]}).to_csv(destination, index=False)
    before = destination.read_bytes()
    with pytest.raises(ValueError, match="outside|truncate"):
        mod.run(path, [], out)
    assert destination.read_bytes() == before


def test_filtered_run_preserves_all_site_coverage_audit(tmp_path):
    mod = api()
    path = inventory(tmp_path, ("Site A", "Site B"))
    out = tmp_path / "out"
    mod.run(path, [], out)
    before = (out / "metadata/manifest.csv").read_bytes()
    mod.run(path, [], out, limit=1)
    assert (out / "metadata/manifest.csv").read_bytes() == before
