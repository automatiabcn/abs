// Copyright (c) 2026 Automatia BCN. All rights reserved.
// abs-vmhost --probe — can THIS machine actually run a Tier-2 microVM?
//
// The Python side used to answer that by checking whether
// Virtualization.framework exists on disk. A file being present is not a
// capability: the framework is on every modern macOS, and the question that
// matters is whether a VM configuration built the way ours will be built
// validates on this hardware, for this process, with this entitlement.
//
// So this asks the framework itself. It builds the smallest configuration
// that still resembles the real one — a boot loader, CPU, memory, a vsock
// device for the exec agent — and calls validate(). No VM is started, no
// image is needed, and nothing is claimed that the framework did not say.
//
// Output is one line of JSON on stdout, because the caller is a Python
// module and a human reading a log both deserve the same answer:
//   {"ok":true,"reason":"","cpu_max":10,"mem_max_mb":49152}
//
// Build:  swiftc -O -framework Virtualization -o abs-vmhost probe.swift

import Foundation

#if arch(arm64) || arch(x86_64)
import Virtualization
#endif

struct Answer: Encodable {
    var ok: Bool
    var reason: String
    var cpuMax: Int?
    var memMaxMb: UInt64?

    enum CodingKeys: String, CodingKey {
        case ok, reason
        case cpuMax = "cpu_max"
        case memMaxMb = "mem_max_mb"
    }
}

func emit(_ a: Answer) -> Never {
    let data = (try? JSONEncoder().encode(a)) ?? Data("{\"ok\":false,\"reason\":\"encode failed\"}".utf8)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(a.ok ? 0 : 1)
}

// A kernel we do not have yet must not make the probe lie in either
// direction: the boot loader needs a path, so it gets one that will exist
// when the guest image ships. validate() checks everything else — and the
// missing kernel is reported as exactly that, not as "this Mac cannot".
let KERNEL_PLACEHOLDER = "/usr/local/share/abs/vmlinuz"

#if canImport(Virtualization)
guard CommandLine.arguments.contains("--probe") else {
    emit(Answer(ok: false, reason: "usage: abs-vmhost --probe", cpuMax: nil, memMaxMb: nil))
}

let cpuMax = VZVirtualMachineConfiguration.maximumAllowedCPUCount
let memMax = VZVirtualMachineConfiguration.maximumAllowedMemorySize

let config = VZVirtualMachineConfiguration()
config.cpuCount = min(2, cpuMax)
config.memorySize = min(512 * 1024 * 1024, memMax)

let loader = VZLinuxBootLoader(kernelURL: URL(fileURLWithPath: KERNEL_PLACEHOLDER))
loader.commandLine = "console=hvc0"
config.bootLoader = loader

// The exec agent will talk over vsock; a configuration without it would
// validate while telling us nothing about the shape we actually need.
config.socketDevices = [VZVirtioSocketDeviceConfiguration()]
config.memoryBalloonDevices = [VZVirtioTraditionalMemoryBalloonDeviceConfiguration()]

do {
    try config.validate()
    let haveKernel = FileManager.default.fileExists(atPath: KERNEL_PLACEHOLDER)
    emit(Answer(
        ok: haveKernel,
        reason: haveKernel
            ? ""
            : "the framework accepts this configuration; the guest kernel is not installed yet",
        cpuMax: cpuMax,
        memMaxMb: memMax / (1024 * 1024)
    ))
} catch {
    emit(Answer(
        ok: false,
        reason: "Virtualization refused the configuration: \(error.localizedDescription)",
        cpuMax: cpuMax,
        memMaxMb: memMax / (1024 * 1024)
    ))
}
#else
emit(Answer(ok: false, reason: "Virtualization.framework is not available on this platform", cpuMax: nil, memMaxMb: nil))
#endif
