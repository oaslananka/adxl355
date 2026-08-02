//go:build linux

package main

import (
	"math"
	"strconv"
	"testing"
	"time"
)

func TestParseOptionsUsesBoundedDefaults(t *testing.T) {
	config, err := parseOptions(nil)
	if err != nil {
		t.Fatalf("parseOptions failed: %v", err)
	}
	if config.bus != 0 || config.device != 0 || config.speedHz != 1_000_000 || config.samples != 8 || config.timeout != 10*time.Second {
		t.Fatalf("unexpected defaults: %+v", config)
	}
}

func TestParseOptionsRejectsUnsafeBounds(t *testing.T) {
	cases := [][]string{
		{"-samples", "0"},
		{"-samples", "257"},
		{"-timeout", "0s"},
		{"-timeout", "61s"},
		{"extra"},
	}
	if strconv.IntSize == 64 {
		cases = append(cases, []string{"-speed-hz", strconv.FormatUint(uint64(math.MaxUint32)+1, 10)})
	}
	for _, args := range cases {
		if _, err := parseOptions(args); err == nil {
			t.Fatalf("parseOptions accepted %v", args)
		}
	}
}
