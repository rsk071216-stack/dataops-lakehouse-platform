"""The ODCS ingestion contracts pass on the fixture and fail on upstream drift."""

import csv
from pathlib import Path

import pytest
import yaml
from datacontract.data_contract import DataContract

from lakehouse.config import FIXTURE_DIR, REPO_ROOT

CONTRACTS = REPO_ROOT / "contracts"
pytestmark = pytest.mark.contract


def _run(contract: Path) -> str:
    return str(DataContract(data_contract_file=str(contract), server="fixture").test().result)


@pytest.fixture(autouse=True)
def _repo_cwd(monkeypatch):
    # Contract server paths are relative to the repository root.
    monkeypatch.chdir(REPO_ROOT)


@pytest.mark.parametrize("name", ["tlc_green_trips", "tlc_taxi_zones"])
def test_contracts_pass_on_committed_fixture(name):
    assert _run(CONTRACTS / f"{name}.odcs.yaml").endswith("passed")


def _drifted_contract(tmp_path: Path, mutate) -> Path:
    rows = list(csv.reader((FIXTURE_DIR / "green_tripdata_2024-01.csv").open()))
    rows = mutate(rows)
    data = tmp_path / "drifted.csv"
    with data.open("w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    contract = yaml.safe_load((CONTRACTS / "tlc_green_trips.odcs.yaml").read_text())
    contract["servers"][0]["path"] = data.as_posix()
    out = tmp_path / "contract.yaml"
    out.write_text(yaml.safe_dump(contract, sort_keys=False))
    return out


def test_dropped_upstream_column_breaks_the_contract(tmp_path):
    def drop_fare(rows):
        i = rows[0].index("fare_amount")
        return [r[:i] + r[i + 1 :] for r in rows]

    assert _run(_drifted_contract(tmp_path, drop_fare)).endswith("failed")


def test_out_of_domain_codes_break_the_contract(tmp_path):
    def bad_payment(rows):
        i = rows[0].index("payment_type")
        for r in rows[1:50]:
            r[i] = "9"
        return rows

    assert _run(_drifted_contract(tmp_path, bad_payment)).endswith("failed")
