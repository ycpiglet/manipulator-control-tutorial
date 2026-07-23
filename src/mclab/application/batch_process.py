"""Cross-platform process-tree containment for the desktop batch worker."""

from __future__ import annotations

import os
import signal
import sys
import time
import uuid
from typing import Any


class ProcessContainmentError(RuntimeError):
    """Raised when a batch worker cannot be contained or proven quiescent."""


class BatchProcessTree:
    """Small platform-neutral contract used by the Qt batch controller."""

    def __init__(self, process_type: Any, process: Any) -> None:
        self.process_type = process_type
        self.process = process

    @property
    def worker_arguments(self) -> tuple[str, ...]:
        return ()

    def configure(self) -> None:
        """Configure containment before ``QProcess.start``."""

    def attach(self, pid: int) -> None:
        """Attach the newly started leader and release any start gate."""

    def terminate(self) -> None:
        self.process.terminate()

    def kill(self) -> None:
        self.process.kill()

    def is_active(self) -> bool:
        return self.process.state() != self.process_type.NotRunning

    def wait_dead(self, timeout_ms: int) -> bool:
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        while self.is_active() and time.monotonic() < deadline:
            time.sleep(0.01)
        return not self.is_active()

    def close(self, *, require_empty: bool = True) -> None:
        if require_empty and self.is_active():
            raise ProcessContainmentError("The batch process tree is still active.")


class PosixBatchProcessTree(BatchProcessTree):
    """Contain one trusted worker and its descendants in a new POSIX session."""

    def __init__(self, process_type: Any, process: Any) -> None:
        super().__init__(process_type, process)
        self.pid = 0
        self.pgid = 0
        self.session_id = 0
        self._attachment_failed = False

    def configure(self) -> None:
        try:
            parameters = self.process_type.UnixProcessParameters()
            parameters.flags = self.process_type.UnixProcessFlag.CreateNewSession
            self.process.setUnixProcessParameters(parameters)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ProcessContainmentError(
                "Qt cannot create a dedicated POSIX session for the batch worker."
            ) from exc

    def attach(self, pid: int) -> None:
        if pid <= 0:
            self._attachment_failed = True
            raise ProcessContainmentError("The batch worker did not expose a valid process ID.")
        try:
            pgid = os.getpgid(pid)
            session_id = os.getsid(pid)
        except OSError as exc:
            self._attachment_failed = True
            raise ProcessContainmentError(
                "The batch worker exited before its POSIX session could be verified."
            ) from exc
        if pgid != pid or session_id != pid or pgid == os.getpgrp():
            self._attachment_failed = True
            raise ProcessContainmentError(
                "The batch worker is not isolated in the expected POSIX session."
            )
        self.pid = pid
        self.pgid = pgid
        self.session_id = session_id
        self._attachment_failed = False

    def _signal_group(self, signal_number: int) -> None:
        if self.pgid <= 0 or self.pgid == os.getpgrp():
            raise ProcessContainmentError("Refusing to signal an unverified process group.")
        try:
            os.killpg(self.pgid, signal_number)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise ProcessContainmentError(
                "Permission was denied while stopping the batch process group."
            ) from exc

    def terminate(self) -> None:
        if self.pgid > 0:
            self._signal_group(signal.SIGTERM)
        else:
            super().terminate()

    def kill(self) -> None:
        if self.pgid > 0:
            self._signal_group(signal.SIGKILL)
        else:
            super().kill()

    def is_active(self) -> bool:
        if self._attachment_failed:
            raise ProcessContainmentError(
                "The failed POSIX session attachment prevents a process-tree death proof."
            )
        if self.pgid <= 0:
            return super().is_active()
        try:
            os.killpg(self.pgid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # An existing group that cannot be inspected is not proof of death.
            return True
        return True

    def close(self, *, require_empty: bool = True) -> None:
        super().close(require_empty=require_empty)
        self.pid = self.pgid = self.session_id = 0


class _WindowsJobApi:
    """Minimal ctypes wrapper; no shell command or optional package is required."""

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _SYNCHRONIZE = 0x00100000

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class BasicAccountingInformation(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_longlong),
                ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        self.ExtendedLimitInformation = ExtendedLimitInformation
        self.BasicAccountingInformation = BasicAccountingInformation
        self._declare_functions()

    def _declare_functions(self) -> None:
        ctypes = self.ctypes
        wintypes = self.wintypes
        functions = self.kernel32
        functions.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        functions.CreateJobObjectW.restype = wintypes.HANDLE
        functions.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        functions.SetInformationJobObject.restype = wintypes.BOOL
        functions.QueryInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        )
        functions.QueryInformationJobObject.restype = wintypes.BOOL
        functions.CreateEventW.argtypes = (
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        functions.CreateEventW.restype = wintypes.HANDLE
        functions.SetEvent.argtypes = (wintypes.HANDLE,)
        functions.SetEvent.restype = wintypes.BOOL
        functions.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        functions.OpenProcess.restype = wintypes.HANDLE
        functions.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        functions.AssignProcessToJobObject.restype = wintypes.BOOL
        functions.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        functions.TerminateJobObject.restype = wintypes.BOOL
        functions.CloseHandle.argtypes = (wintypes.HANDLE,)
        functions.CloseHandle.restype = wintypes.BOOL

    def _raise_last(self, message: str) -> None:
        error = self.ctypes.get_last_error()
        raise OSError(error, f"{message}: {self.ctypes.FormatError(error)}")

    def create_job(self) -> Any:
        job = self.kernel32.CreateJobObjectW(None, None)
        if not job:
            self._raise_last("Could not create the batch Job Object")
        limits = self.ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel32.SetInformationJobObject(
            job,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            self.ctypes.byref(limits),
            self.ctypes.sizeof(limits),
        ):
            error = self.ctypes.get_last_error()
            message = self.ctypes.FormatError(error)
            try:
                self.close_handle(job)
            except OSError:
                pass
            raise OSError(
                error,
                f"Could not configure kill-on-close for the batch Job Object: {message}",
            )
        return job

    def create_event(self, name: str) -> Any:
        event = self.kernel32.CreateEventW(None, True, False, name)
        if not event:
            self._raise_last("Could not create the batch worker start gate")
        return event

    def assign(self, job: Any, pid: int) -> None:
        access = (
            self._PROCESS_TERMINATE
            | self._PROCESS_SET_QUOTA
            | self._PROCESS_QUERY_LIMITED_INFORMATION
            | self._SYNCHRONIZE
        )
        process = self.kernel32.OpenProcess(access, False, pid)
        if not process:
            self._raise_last("Could not open the held batch worker")
        try:
            if not self.kernel32.AssignProcessToJobObject(job, process):
                self._raise_last("Could not assign the held batch worker to its Job Object")
        finally:
            self.close_handle(process)

    def release_event(self, event: Any) -> None:
        if not self.kernel32.SetEvent(event):
            self._raise_last("Could not release the contained batch worker")

    def active_processes(self, job: Any) -> int:
        accounting = self.BasicAccountingInformation()
        if not self.kernel32.QueryInformationJobObject(
            job,
            self._JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            self.ctypes.byref(accounting),
            self.ctypes.sizeof(accounting),
            None,
        ):
            self._raise_last("Could not query the batch Job Object")
        return int(accounting.ActiveProcesses)

    def terminate(self, job: Any) -> None:
        if not self.kernel32.TerminateJobObject(job, 3):
            self._raise_last("Could not terminate the batch Job Object")

    def close_handle(self, handle: Any) -> None:
        if handle and not self.kernel32.CloseHandle(handle):
            self._raise_last("Could not close a batch containment handle")


class WindowsBatchProcessTree(BatchProcessTree):
    """Hold the worker, assign it to a kill-on-close Job Object, then release it."""

    def __init__(
        self,
        process_type: Any,
        process: Any,
        *,
        api: Any | None = None,
    ) -> None:
        super().__init__(process_type, process)
        self._api = api or _WindowsJobApi()
        self._event_name = f"Local\\MCLabBatch-{uuid.uuid4().hex}"
        self._job: Any = None
        self._event: Any = None
        self._attached = False
        self._closed = False
        try:
            self._job = self._api.create_job()
            self._event = self._api.create_event(self._event_name)
        except Exception:
            if self._event is not None:
                try:
                    self._api.close_handle(self._event)
                except Exception:
                    pass
            if self._job is not None:
                try:
                    self._api.close_handle(self._job)
                except Exception:
                    pass
            raise

    @property
    def worker_arguments(self) -> tuple[str, ...]:
        return ("--start-event", self._event_name)

    def attach(self, pid: int) -> None:
        if pid <= 0:
            raise ProcessContainmentError("The batch worker did not expose a valid process ID.")
        try:
            self._api.assign(self._job, pid)
            self._attached = True
            self._api.release_event(self._event)
        except Exception as exc:
            if self._attached:
                try:
                    self._api.terminate(self._job)
                except Exception:
                    pass
            # Assignment can fail before ``_attached`` becomes true.  The
            # child is still held on the named event in that case, but it is
            # not protected by the Job Object.  Reap that direct process here
            # so callers can never mistake an attach failure for quiescence.
            try:
                self.process.kill()
                self.process.waitForFinished(2_000)
            except (AttributeError, RuntimeError):
                pass
            raise ProcessContainmentError(
                "The held batch worker could not be assigned to its Windows Job Object."
            ) from exc

    def terminate(self) -> None:
        # QProcess terminate is only a cooperative request on Windows.  The
        # Job Object is used by ``kill`` after the grace interval.
        super().terminate()

    def kill(self) -> None:
        if self._attached:
            try:
                self._api.terminate(self._job)
            except Exception as exc:
                raise ProcessContainmentError(
                    "The Windows batch process tree could not be terminated."
                ) from exc
        else:
            super().kill()

    def is_active(self) -> bool:
        direct_active = self.process.state() != self.process_type.NotRunning
        if not self._attached or self._job is None:
            return direct_active
        try:
            # Job accounting can reach zero before QProcess has delivered its
            # final state transition.  Both independent witnesses must report
            # quiescence before the controller may settle the output.
            return self._api.active_processes(self._job) > 0 or direct_active
        except Exception as exc:
            raise ProcessContainmentError(
                "The Windows batch process tree could not be inspected."
            ) from exc

    def close(self, *, require_empty: bool = True) -> None:
        if self._closed:
            if require_empty and super().is_active():
                raise ProcessContainmentError("The Windows batch process is still active.")
            return
        if require_empty and self.is_active():
            raise ProcessContainmentError("The Windows batch Job Object is still active.")
        if self._event is not None:
            self._api.close_handle(self._event)
            self._event = None
        if self._job is not None:
            self._api.close_handle(self._job)
            self._job = None
        self._closed = True


def create_batch_process_tree(
    process_type: Any,
    process: Any,
    *,
    platform_name: str | None = None,
    windows_api: Any | None = None,
) -> BatchProcessTree:
    """Return the required containment implementation for this platform."""

    selected = sys.platform if platform_name is None else platform_name
    if selected == "win32":
        return WindowsBatchProcessTree(process_type, process, api=windows_api)
    if selected.startswith(("linux", "darwin", "freebsd")):
        return PosixBatchProcessTree(process_type, process)
    raise ProcessContainmentError(f"Unsupported batch process-containment platform: {selected}")
