from __future__ import annotations

import json
from uuid import uuid4

import pytest

from alpha_algo_backtest_persistence import (
    BacktestRecord,
    BacktestStatus,
    InMemoryBacktestStore,
    PersistenceError,
    cache_key_for_identity,
)
from tests.unit.backtest_p16_test_support import utc


def _record(
    identity_sha256: str = "f" * 64,
    run_id=None,
    metrics: tuple = (("final_equity", "123.45"),),
) -> BacktestRecord:
    return BacktestRecord(
        run_id=run_id or uuid4(),
        identity_sha256=identity_sha256,
        status=BacktestStatus.COMPLETED,
        created_at=utc(2026, 1, 1, 12, 0, 0),
        configuration=(("strategy", "sma"), ("cost", "0")),
        metrics=metrics,
    )


class TestRecordRoundTrip:
    def test_json_round_trip(self) -> None:
        record = _record()
        restored = BacktestRecord.from_json(record.to_json())
        assert restored == record

    def test_corrupted_json_rejected(self) -> None:
        with pytest.raises(PersistenceError):
            BacktestRecord.from_json("{not json")

    def test_missing_field_rejected(self) -> None:
        data = _record().to_dict()
        del data["run_id"]
        with pytest.raises(PersistenceError):
            BacktestRecord.from_json(json.dumps(data))

    def test_invalid_status_rejected(self) -> None:
        data = _record().to_dict()
        data["status"] = "NOT_A_STATUS"
        with pytest.raises(PersistenceError):
            BacktestRecord.from_json(json.dumps(data))

    def test_invalid_run_id_rejected(self) -> None:
        data = _record().to_dict()
        data["run_id"] = "not-a-uuid"
        with pytest.raises(PersistenceError):
            BacktestRecord.from_json(json.dumps(data))

    def test_deterministic_serialization(self) -> None:
        # Configuration/metrics pair ordering must not affect the JSON.
        a = BacktestRecord(
            run_id=uuid4(), identity_sha256="a" * 64, status=BacktestStatus.PENDING,
            created_at=utc(2026, 1, 1),
            configuration=(("b", "2"), ("a", "1")),
            metrics=(("z", "9"), ("m", "1")),
        )
        b = BacktestRecord(
            run_id=a.run_id, identity_sha256="a" * 64, status=BacktestStatus.PENDING,
            created_at=utc(2026, 1, 1),
            configuration=(("a", "1"), ("b", "2")),
            metrics=(("m", "1"), ("z", "9")),
        )
        assert a.to_json() == b.to_json()


class TestStore:
    def test_save_load_round_trip(self) -> None:
        store = InMemoryBacktestStore()
        record = _record(identity_sha256="a" * 64)
        store.save(record)
        assert store.contains("a" * 64)
        assert store.load("a" * 64) == record

    def test_missing_load_returns_none(self) -> None:
        store = InMemoryBacktestStore()
        assert store.load("b" * 64) is None

    def test_duplicate_identity_identical_payload_is_noop(self) -> None:
        store = InMemoryBacktestStore()
        record = _record(identity_sha256="a" * 64)
        first = store.save(record)
        second = store.save(record)
        assert first == second
        assert len(store) == 1

    def test_duplicate_identity_conflicting_payload_rejected(self) -> None:
        store = InMemoryBacktestStore()
        store.save(_record(identity_sha256="a" * 64, metrics=(("final_equity", "1"),)))
        with pytest.raises(PersistenceError):
            store.save(_record(identity_sha256="a" * 64, metrics=(("final_equity", "2"),)))

    def test_cache_key_requires_64_hex(self) -> None:
        assert cache_key_for_identity("c" * 64) == "c" * 64
        with pytest.raises(PersistenceError):
            cache_key_for_identity("short")

    def test_save_rejects_non_record(self) -> None:
        store = InMemoryBacktestStore()
        with pytest.raises(PersistenceError):
            store.save("not-a-record")  # type: ignore[arg-type]
