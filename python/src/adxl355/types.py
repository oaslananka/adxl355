"""ADXL355 data types."""

from dataclasses import dataclass

from adxl355.registers import InterruptPolarity


@dataclass(frozen=True)
class RawXYZ:
    """Raw 20-bit acceleration data (sign-extended to int)."""

    x: int
    y: int
    z: int


@dataclass(frozen=True)
class AccelXYZ:
    """Acceleration in floating-point units."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class DataReadyConfig:
    """Internal-clock DRDY and DATA_RDY interrupt routing configuration."""

    dedicated_drdy_enabled: bool = True
    route_to_int1: bool = False
    route_to_int2: bool = False
    interrupt_polarity: InterruptPolarity = InterruptPolarity.ACTIVE_LOW


@dataclass(frozen=True)
class FifoLocation:
    """One decoded FIFO axis location."""

    raw: int
    is_x_axis: bool
    empty: bool = False


@dataclass(frozen=True)
class FifoReadResult:
    """Complete samples and bounded FIFO consumption metadata."""

    samples: tuple[RawXYZ, ...]
    available_locations: int
    consumed_locations: int
    remaining_locations: int
    consumption_indeterminate: bool = False


@dataclass(frozen=True)
class SelfTestThresholds:
    """Caller-owned absolute response windows in g for one fixture policy."""

    min_abs_delta_g: AccelXYZ
    max_abs_delta_g: AccelXYZ


@dataclass(frozen=True)
class SelfTestConfig:
    """Bounded electrostatic self-test acquisition configuration."""

    sample_count: int = 32
    settle_samples: int = 4
    max_ready_polls: int = 500
    poll_delay_ms: int = 1
    thresholds: SelfTestThresholds | None = None


@dataclass(frozen=True)
class SelfTestResult:
    """Measured baseline, stimulated response, and caller-policy outcome."""

    baseline_g: AccelXYZ
    stimulated_g: AccelXYZ
    delta_g: AccelXYZ
    abs_delta_g: AccelXYZ
    samples: int
    thresholds_evaluated: bool
    thresholds_passed: bool
