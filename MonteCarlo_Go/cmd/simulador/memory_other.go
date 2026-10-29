//go:build !windows

package main

import "runtime"

func peakMemoryMiB() float64 {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	return float64(m.Sys) / (1024 * 1024)
}
