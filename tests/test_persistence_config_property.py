"""Property-based tests for FinestVX persistence configuration invariants."""

from __future__ import annotations

import pytest
from hypothesis import event, given

from finestvx.persistence.config import PersistenceConfig, ReadReplicaConfig
from tests.strategies.config import (
    invalid_reserve_bytes,
    valid_reserve_bytes,
)


@pytest.mark.property
@pytest.mark.hypothesis
class TestPersistenceConfigProperties:
    """Property checks for PersistenceConfig and ReadReplicaConfig reserve-bytes invariants."""

    @given(reserve_bytes=valid_reserve_bytes())
    def test_valid_reserve_bytes_accepted_in_persistence_config(
        self, reserve_bytes: int
    ) -> None:
        """PersistenceConfig accepts any reserve_bytes within [0, 255]."""
        config = PersistenceConfig(
            database_path="/tmp/test.db",
            reserve_bytes=reserve_bytes,
        )

        event(f"outcome=accepted_reserve_bytes={reserve_bytes}")
        assert config.reserve_bytes == reserve_bytes

    @given(reserve_bytes=invalid_reserve_bytes())
    def test_invalid_reserve_bytes_rejected_in_persistence_config(
        self, reserve_bytes: int
    ) -> None:
        """PersistenceConfig rejects any reserve_bytes outside [0, 255]."""
        event(f"outcome=rejected_reserve_bytes={reserve_bytes}")
        with pytest.raises(ValueError, match=r"reserve_bytes must be in range \[0, 255\]"):
            PersistenceConfig(
                database_path="/tmp/test.db",
                reserve_bytes=reserve_bytes,
            )

    @given(reserve_bytes=valid_reserve_bytes())
    def test_valid_reserve_bytes_accepted_in_read_replica_config(
        self, reserve_bytes: int
    ) -> None:
        """ReadReplicaConfig accepts any reserve_bytes within [0, 255]."""
        config = ReadReplicaConfig(
            database_path="/tmp/test_replica.db",
            reserve_bytes=reserve_bytes,
        )

        event(f"outcome=accepted_replica_reserve_bytes={reserve_bytes}")
        assert config.reserve_bytes == reserve_bytes

    @given(reserve_bytes=invalid_reserve_bytes())
    def test_invalid_reserve_bytes_rejected_in_read_replica_config(
        self, reserve_bytes: int
    ) -> None:
        """ReadReplicaConfig rejects any reserve_bytes outside [0, 255]."""
        event(f"outcome=rejected_replica_reserve_bytes={reserve_bytes}")
        with pytest.raises(ValueError, match=r"reserve_bytes must be in range \[0, 255\]"):
            ReadReplicaConfig(
                database_path="/tmp/test_replica.db",
                reserve_bytes=reserve_bytes,
            )
