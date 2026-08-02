"""Shared-vector and bounded device tests for the ADXL355 FIFO contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adxl355 import ADXL355, RawXYZ, decode_fifo_sample
from adxl355.errors import (
    FifoBusError,
    FifoEmptyError,
    FifoFormatError,
    FifoOverrunError,
    InvalidConfigurationError,
)
from adxl355.registers import STATUS_FIFO_OVR, Register
from adxl355.testing import MockTransport

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "spec" / "test_vectors.json").read_text()
)["fifo"]


def device_and_transport() -> tuple[ADXL355, MockTransport]:
    transport = MockTransport()
    transport.set_identity_ok()
    device = ADXL355(transport)
    device.probe()
    return device, transport


@pytest.mark.parametrize("vector", VECTORS["valid_samples"])
def test_decode_shared_valid_samples(vector: dict[str, object]) -> None:
    raw = vector["raw"]
    assert isinstance(raw, dict)
    assert decode_fifo_sample(bytes(vector["bytes"])) == RawXYZ(x=raw["x"], y=raw["y"], z=raw["z"])


@pytest.mark.parametrize("vector", VECTORS["invalid_samples"])
def test_decode_shared_invalid_samples(vector: dict[str, object]) -> None:
    error = {"length": FifoFormatError, "empty": FifoEmptyError, "format": FifoFormatError}[
        vector["error"]
    ]
    with pytest.raises(error):
        decode_fifo_sample(bytes(vector["bytes"]))


def test_bounded_reads_preserve_remaining_locations() -> None:
    device, transport = device_and_transport()
    payload = bytes(VECTORS["valid_samples"][1]["bytes"]) + bytes(
        VECTORS["valid_samples"][2]["bytes"]
    )
    transport.set_fifo_payload(payload)

    first = device.read_fifo_samples(1)
    assert first.samples == (RawXYZ(1, -1, 262144),)
    assert (first.available_locations, first.consumed_locations, first.remaining_locations) == (
        6,
        3,
        3,
    )

    second = device.read_fifo_samples(2)
    assert second.samples == (RawXYZ(524287, -524288, -1),)
    assert (second.available_locations, second.consumed_locations, second.remaining_locations) == (
        3,
        3,
        0,
    )


def test_partial_decode_error_exposes_valid_prefix() -> None:
    device, transport = device_and_transport()
    payload = bytes(VECTORS["valid_samples"][0]["bytes"]) + bytes(
        VECTORS["invalid_samples"][2]["bytes"]
    )
    transport.set_fifo_payload(payload)

    with pytest.raises(FifoEmptyError) as caught:
        device.read_fifo_samples(2)
    assert caught.value.partial_samples == (RawXYZ(0, 0, 0),)
    assert caught.value.consumed_locations == 6


def test_empty_overrun_and_malformed_count_do_not_consume() -> None:
    device, transport = device_and_transport()
    with pytest.raises(FifoEmptyError):
        device.read_fifo_samples(1)

    payload = bytes(VECTORS["valid_samples"][0]["bytes"])
    transport.set_fifo_payload(payload)
    transport.set_register(Register.STATUS, STATUS_FIFO_OVR)
    with pytest.raises(FifoOverrunError):
        device.read_fifo_samples(1)
    assert transport._fifo_offset == 0

    transport.set_register(Register.STATUS, 0)
    transport.set_fifo_payload(payload, locations=4)
    remainder = device.read_fifo_samples(1)
    assert remainder.samples == (RawXYZ(0, 0, 0),)
    assert remainder.remaining_locations == 1
    transport.set_register(Register.FIFO_ENTRIES, 0x80)
    with pytest.raises(FifoFormatError):
        device.read_fifo_entries()


@pytest.mark.parametrize("returned_length", [0, 8, 10])
def test_fifo_transport_length_errors_preserve_bus_hierarchy(returned_length: int) -> None:
    device, transport = device_and_transport()
    transport.set_fifo_payload(bytes(VECTORS["valid_samples"][0]["bytes"]))
    transport.inject_short_read(Register.FIFO_DATA, returned_length)
    with pytest.raises(FifoBusError) as caught:
        device.read_fifo_samples(1)
    assert caught.value.partial_samples == ()
    assert caught.value.consumed_locations == 0
    assert caught.value.consumption_indeterminate is True


@pytest.mark.parametrize("count", [0, 33, True])
def test_fifo_sample_limit_is_bounded(count: int) -> None:
    device, _ = device_and_transport()
    with pytest.raises(InvalidConfigurationError):
        device.read_fifo_samples(count)


def test_fifo_count_bus_failure_has_known_zero_consumption() -> None:
    device, transport = device_and_transport()
    transport.inject_short_read(Register.FIFO_ENTRIES, 0)
    with pytest.raises(FifoBusError) as caught:
        device.read_fifo_samples(1)
    assert caught.value.consumed_locations == 0
    assert caught.value.consumption_indeterminate is False
