"""Resource boundaries for decoder/inference children; no DB or HTTP access."""
import ctypes
import os
import signal
import subprocess


def child_options(memory_mb):
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    environment["SILATSENSE_CHILD_MEMORY_MB"] = str(memory_mb)
    environment["SILATSENSE_PARENT_PID"] = str(os.getpid())
    return {"env": environment, "creationflags": subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0}


def constrain_child():
    """Called before importing OpenCV/MediaPipe in each executable child."""
    memory = int(os.environ.get("SILATSENSE_CHILD_MEMORY_MB", "2048")) * 1024 * 1024
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        if os.name == "posix" and os.path.exists("/proc"):
            # Linux: a worker crash must not leave an inference child behind.
            ctypes.CDLL(None).prctl(1, signal.SIGKILL)
            if os.getppid() != int(os.environ.get("SILATSENSE_PARENT_PID", os.getppid())):
                os.kill(os.getpid(), signal.SIGKILL)


class ChildGuard:
    """Windows job closes children on parent crash and caps committed memory."""
    def __init__(self, process, memory_mb):
        self.handle = None
        if os.name != "nt":
            return
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                        ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ["ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount"]]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateJobObjectW(None, None)
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x100  # kill-on-close + process-memory
        limits.ProcessMemoryLimit = memory_mb * 1024 * 1024
        if (not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                or not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle)))):
            if handle:
                kernel.CloseHandle(handle)
            process.kill()
            process.wait()
            raise OSError("Cannot apply child process resource limits")
        self.handle, self.kernel = handle, kernel

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
