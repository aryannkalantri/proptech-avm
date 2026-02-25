"""
test_processor.py
-----------------
Lightweight unit tests for processor.py logic.
Run with:
    python -m pytest test_processor.py -v
"""

import pytest
from processor import parse_fields, compute_valuation


SAMPLE_TEXT = """
Property Address: 4821 Oakwood Drive
City: Austin
State: TX
ZIP: 78745
Year Built: 2003
Square Feet: 2,150
Bedrooms: 4
Bathrooms: 2.5
Lot Size: 0.22 acres
List Price: $485,000

Comp 1: 4705 Maple Lane | $472,000 | 2,080 sqft
Comp 2: 4930 Cedar Ridge Blvd | $495,500 | 2,240 sqft
Comp 3: 4612 Birchwood Court | $468,000 | 2,010 sqft
"""


class TestParseFields:
    def setup_method(self):
        self.fields = parse_fields(SAMPLE_TEXT)

    def test_address(self):
        assert "4821 Oakwood Drive" in self.fields["address"]

    def test_city(self):
        assert self.fields["city"].strip().lower() == "austin"

    def test_state(self):
        assert self.fields["state"] == "TX"

    def test_zip(self):
        assert self.fields["zip_code"] == "78745"

    def test_sq_ft(self):
        assert self.fields["sq_ft"] == "2150"

    def test_bedrooms(self):
        assert self.fields["bedrooms"] == "4"

    def test_bathrooms(self):
        assert "2.5" in self.fields["bathrooms"] or "2" in self.fields["bathrooms"]

    def test_year_built(self):
        assert self.fields["year_built"] == "2003"

    def test_list_price(self):
        assert self.fields["list_price"] == "485000"

    def test_comp1_present(self):
        assert "Maple Lane" in self.fields["comp1_address"]

    def test_comp2_price(self):
        assert self.fields["comp2_price"] == "495500"

    def test_comp3_sqft(self):
        assert self.fields["comp3_sqft"] == "2010"

    def test_report_date_present(self):
        assert len(self.fields["report_date"]) > 0


class TestComputeValuation:
    def setup_method(self):
        raw = parse_fields(SAMPLE_TEXT)
        self.data = compute_valuation(raw)

    def test_price_per_sqft(self):
        # $485,000 / 2,150 = $225.58
        assert self.data["price_per_sqft"] != "N/A"
        val = float(self.data["price_per_sqft"].replace("$", "").replace(",", ""))
        assert abs(val - 225.58) < 0.5

    def test_avg_comp_ppsf(self):
        # Comp avg: (472000/2080 + 495500/2240 + 468000/2010) / 3
        assert self.data["avg_comp_ppsf"] != "N/A"

    def test_estimated_value_is_numeric(self):
        assert self.data["estimated_value"] != "N/A"
        val_str = self.data["estimated_value"].replace("$", "").replace(",", "")
        assert float(val_str) > 0

    def test_list_price_display_formatted(self):
        assert self.data["list_price_display"] == "$485,000"

    def test_comp_displays_populated(self):
        for i in range(1, 4):
            assert self.data[f"comp{i}_price_display"] != ""
            assert self.data[f"comp{i}_ppsf"] != ""
