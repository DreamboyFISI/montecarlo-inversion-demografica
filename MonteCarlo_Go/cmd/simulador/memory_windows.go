//go:build windows

package main

import (
	"syscall"
	"unsafe"
)

type processMemoryCounters struct {
	CB, PageFaultCount                                                                                                                                                     uint32
	PeakWorkingSetSize, WorkingSetSize, QuotaPeakPagedPoolUsage, QuotaPagedPoolUsage, QuotaPeakNonPagedPoolUsage, QuotaNonPagedPoolUsage, PagefileUsage, PeakPagefileUsage uintptr
}

func peakMemoryMiB() float64 {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	psapi := syscall.NewLazyDLL("psapi.dll")
	getCurrentProcess := kernel32.NewProc("GetCurrentProcess")
	getInfo := psapi.NewProc("GetProcessMemoryInfo")
	handle, _, _ := getCurrentProcess.Call()
	var m processMemoryCounters
	m.CB = uint32(unsafe.Sizeof(m))
	ok, _, _ := getInfo.Call(handle, uintptr(unsafe.Pointer(&m)), uintptr(m.CB))
	if ok == 0 {
		return 0
	}
	return float64(m.PeakWorkingSetSize) / (1024 * 1024)
}
