//go:build linux

// Command linux_spi performs one bounded ADXL355 read sequence through spidev.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log"
	"math"
	"os"
	"time"

	"github.com/oaslananka/adxl355/go/adxl355"
	"github.com/oaslananka/adxl355/go/adxl355/linuxio"
	"github.com/oaslananka/adxl355/go/examples/internal/bounded"
)

type options struct {
	bus     int
	device  int
	speedHz uint32
	samples int
	timeout time.Duration
}

func main() {
	if err := execute(os.Args[1:], os.Stdout); err != nil {
		log.Print(err)
		os.Exit(1)
	}
}

func parseOptions(args []string) (options, error) {
	flags := flag.NewFlagSet("linux_spi", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	bus := flags.Int("bus", 0, "Linux spidev bus number")
	device := flags.Int("device", 0, "Linux spidev chip-select number")
	speed := flags.Uint("speed-hz", 1_000_000, "SPI clock in Hz (100000..10000000)")
	samples := flags.Int("samples", 8, "bounded sample count (1..256)")
	timeout := flags.Duration("timeout", 10*time.Second, "overall command timeout")
	if err := flags.Parse(args); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, fmt.Errorf("unexpected positional arguments: %v", flags.Args())
	}
	if uint64(*speed) > math.MaxUint32 {
		return options{}, fmt.Errorf("speed-hz must fit in uint32")
	}
	if *samples < 1 || *samples > 256 {
		return options{}, fmt.Errorf("samples must be in 1..256")
	}
	if *timeout <= 0 || *timeout > time.Minute {
		return options{}, fmt.Errorf("timeout must be greater than zero and at most one minute")
	}
	return options{
		bus: *bus, device: *device, speedHz: uint32(*speed), samples: *samples, timeout: *timeout,
	}, nil
}

func execute(args []string, output io.Writer) (returnErr error) {
	config, err := parseOptions(args)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), config.timeout)
	defer cancel()

	transport, err := linuxio.OpenSPI(linuxio.SPIConfig{
		Bus: config.bus, Device: config.device, Mode: 0, SpeedHz: config.speedHz,
	})
	if err != nil {
		return fmt.Errorf("open SPI transport: %w", err)
	}
	defer func() {
		if err := transport.Close(); err != nil && returnErr == nil {
			returnErr = fmt.Errorf("close SPI transport: %w", err)
		}
	}()

	return bounded.Run(ctx, adxl355.New(transport), config.samples, output)
}
