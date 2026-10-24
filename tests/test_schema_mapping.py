from datetime import datetime

import pytest

from lakehouse.ingest.schema import GREEN_TRIPS, TAXI_ZONES, dlt_columns, map_row


def test_map_row_renames_and_types_known_columns():
    row = map_row(
        {
            "VendorID": "2",
            "lpep_pickup_datetime": "2024-01-01 00:46:55",
            "PULocationID": "236",
            "fare_amount": "12.8",
            "ehail_fee": "",
            "passenger_count": "1.0",
        },
        GREEN_TRIPS,
    )
    assert row == {
        "vendor_id": 2,
        "pickup_datetime": datetime(2024, 1, 1, 0, 46, 55),
        "pickup_location_id": 236,
        "fare_amount": 12.8,
        "ehail_fee": None,
        "passenger_count": 1,
    }


def test_unknown_upstream_columns_pass_through_for_the_frozen_contract_to_reject():
    row = map_row({"LocationID": "1", "brand_new_column": "x"}, TAXI_ZONES)
    assert row == {"location_id": 1, "brand_new_column": "x"}


def test_bad_values_fail_loudly_with_the_column_name():
    with pytest.raises(ValueError, match="PULocationID"):
        map_row({"PULocationID": "Z236"}, GREEN_TRIPS)


def test_dlt_columns_are_timezone_naive_timestamps_plus_lineage():
    cols = dlt_columns(GREEN_TRIPS)
    assert cols["pickup_datetime"] == {
        "data_type": "timestamp",
        "nullable": True,
        "timezone": False,
    }
    assert {"source_month", "source_file", "ingested_at"} <= cols.keys()
    assert len(cols) == len(GREEN_TRIPS) + 3
