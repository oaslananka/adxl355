//go:build linux

// Command linux_i2c performs one bounded ADXL355 read sequence through i2c-dev.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log"
	"math"
	"os"
	"strconv"
	"time"

	"github.com/oaslananka/adxl355/go/adxl355"
	"github.com/oaslananka/adxl355/go/adxl355/linuxio"
	"github.com/oaslananka/adxl355/go/examples/internal/bounded"
)

type options struct {
	bus     int
	address uint16
	busHz   uint32
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
	flags := flag.NewFlagSet("linux_i2c", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	bus := flags.Int("bus", 1, "Linux i2c-dev bus number")
	addressText := flags.String("address", "0x1D", "ADXL355 address: 0x1D or 0x53")
	busHz := flags.Uint("bus-hz", 400_000, "externally configured I2C bus clock")
	samples := flags.Int("samples", 8, "bounded sample count (1..256)")
	timeout := flags.Duration("timeout", 10*time.Second, "overall command timeout")
	if err := flags.Parse(args); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, fmt.Errorf("unexpected positional arguments: %v", flags.Args())
	}
	address, err := strconv.ParseUint(*addressText, 0, 16)
	if err != nil {
		return options{}, fmt.Errorf("invalid address %q: %w", *addressText, err)
	}
	if uint64(*busHz) > math.MaxUint32 {
		return options{}, fmt.Errorf("bus-hz must fit in uint32")
	}
	if *samples < 1 || *samples > 256 {
		return options{}, fmt.Errorf("samples must be in 1..256")
	}
	if *timeout <= 0 || *timeout > time.Minute {
		return options{}, fmt.Errorf("timeout must be greater than zero and at most one minute")
	}
	return options{
		bus: *bus, address: uint16(address), busHz: uint32(*busHz), samples: *samples, timeout: *timeout,
	}, nil
}

func execute(args []string, output io.Writer) (returnErr error) {
	config, err := parseOptions(args)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), config.timeout)
	defer cancel()

	transport, err := linuxio.OpenI2C(linuxio.I2CConfig{
		Bus: config.bus, Address: config.address, BusHz: config.busHz,
	})
	if err != nil {
		return fmt.Errorf("open I2C transport: %w", err)
	}
	defer func() {
		if err := transport.Close(); err != nil && returnErr == nil {
			returnErr = fmt.Errorf("close I2C transport: %w", err)
		}
	}()

	return bounded.Run(ctx, adxl355.New(transport), config.samples, output)
}
