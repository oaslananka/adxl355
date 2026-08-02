// Package bounded implements the shared finite hardware-read sequence used by
// the Linux SPI and I2C examples.
package bounded

import (
	"context"
	"fmt"
	"io"
	"time"

	"github.com/oaslananka/adxl355/go/adxl355"
)

// Run probes one sensor, reads temperature, collects a finite number of samples,
// and restores standby before returning. The caller owns transport Close.
func Run(
	ctx context.Context,
	sensor *adxl355.Device,
	samples int,
	output io.Writer,
) (returnErr error) {
	if err := contextError(ctx); err != nil {
		return err
	}
	identityOK, err := sensor.Probe()
	if err != nil {
		return fmt.Errorf("probe: %w", err)
	}
	if !identityOK {
		return fmt.Errorf("probe: identity mismatch")
	}
	if _, err := fmt.Fprintln(output, "identity_ok=true"); err != nil {
		return fmt.Errorf("write identity result: %w", err)
	}

	if err := sensor.SetPowerMode(adxl355.PowerMeasurement); err != nil {
		return fmt.Errorf("enter measurement: %w", err)
	}
	defer func() {
		if err := sensor.SetPowerMode(adxl355.PowerStandby); err != nil && returnErr == nil {
			returnErr = fmt.Errorf("restore standby: %w", err)
		}
	}()

	// Temperature and acceleration output registers are not considered fresh
	// until measurement mode has had a bounded settling interval.
	if err := waitContext(ctx, 20*time.Millisecond); err != nil {
		return err
	}
	temperature, err := sensor.ReadTemperatureC()
	if err != nil {
		return fmt.Errorf("temperature: %w", err)
	}
	if _, err := fmt.Fprintf(output, "temperature_c=%.4f\n", temperature); err != nil {
		return fmt.Errorf("write temperature result: %w", err)
	}

	for index := 0; index < samples; index++ {
		if err := waitReady(ctx, sensor, 250*time.Millisecond); err != nil {
			return err
		}
		raw, err := sensor.ReadRaw()
		if err != nil {
			return fmt.Errorf("sample %d: %w", index+1, err)
		}
		if _, err := fmt.Fprintf(
			output,
			"sample=%d raw_x=%d raw_y=%d raw_z=%d\n",
			index+1,
			raw.X,
			raw.Y,
			raw.Z,
		); err != nil {
			return fmt.Errorf("write sample %d: %w", index+1, err)
		}
	}
	return nil
}

func waitReady(ctx context.Context, sensor *adxl355.Device, limit time.Duration) error {
	deadline := time.NewTimer(limit)
	defer deadline.Stop()
	ticker := time.NewTicker(time.Millisecond)
	defer ticker.Stop()
	for {
		status, err := sensor.ReadStatus()
		if err != nil {
			return fmt.Errorf("read status: %w", err)
		}
		if status&(1<<adxl355.StatusDATA_RDY) != 0 {
			return nil
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("overall timeout: %w", ctx.Err())
		case <-deadline.C:
			return fmt.Errorf("sample data-ready timeout after %s", limit)
		case <-ticker.C:
		}
	}
}

func contextError(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return fmt.Errorf("overall timeout: %w", ctx.Err())
	default:
		return nil
	}
}

func waitContext(ctx context.Context, duration time.Duration) error {
	timer := time.NewTimer(duration)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return fmt.Errorf("overall timeout: %w", ctx.Err())
	case <-timer.C:
		return nil
	}
}
