"""Measured process resources without optional monitoring dependencies."""
import os
import threading
from functools import lru_cache


@lru_cache(maxsize=1)
def _windows_types():
    # ctypes retains pointer/structure types. Defining these on every metrics
    # request creates a new retained type graph and unbounded memory growth.
    import ctypes
    from ctypes import wintypes as w
    class Memory(ctypes.Structure):
        _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(n,ctypes.c_size_t) for n in (
            'peak','working','quota_peak_paged','quota_paged','quota_peak_nonpaged',
            'quota_nonpaged','pagefile','peak_pagefile','private')]
    class Row4(ctypes.Structure):
        _fields_=[(name,w.DWORD) for name in ('state','local','localport','remote','remoteport','pid')]
    class Row6(ctypes.Structure):
        _fields_=[('local',ctypes.c_ubyte*16),('scope',w.DWORD),('localport',w.DWORD),
                  ('remote',ctypes.c_ubyte*16),('rscope',w.DWORD),('remoteport',w.DWORD),('state',w.DWORD),('pid',w.DWORD)]
    return Memory,Row4,Row6


def process_metrics():
    result={'pid':os.getpid(),'threads':threading.active_count(),'rss_mb':None,'private_mb':None,'sockets':None}
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes as w
        Memory,Row4,Row6=_windows_types()
        kernel=ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype=w.HANDLE
        memory=Memory();memory.cb=ctypes.sizeof(memory)
        getter=ctypes.windll.psapi.GetProcessMemoryInfo
        getter.argtypes=[w.HANDLE,ctypes.POINTER(Memory),w.DWORD]
        if getter(kernel.GetCurrentProcess(),ctypes.byref(memory),memory.cb):
            result['rss_mb']=memory.working/(1024*1024)
            result['private_mb']=memory.private/(1024*1024)
        # GetExtendedTcpTable OWNER_PID rows include active TCP sockets owned
        # by this process, not the load generator's desired client count.
        total=0;measured=False
        for family,row_type in ((2,Row4),(23,Row6)):
            size=w.DWORD(0);getter=ctypes.windll.iphlpapi.GetExtendedTcpTable
            getter(None,ctypes.byref(size),False,family,5,0)
            if not size.value:continue
            buffer=ctypes.create_string_buffer(size.value)
            if getter(buffer,ctypes.byref(size),False,family,5,0)!=0:continue
            count=w.DWORD.from_buffer(buffer).value;measured=True
            for i in range(count):
                row=row_type.from_buffer(buffer,4+i*ctypes.sizeof(row_type))
                total+=int(row.pid==os.getpid())
        if measured:result['sockets']=total
    elif os.path.isfile('/proc/self/status'):
        from pathlib import Path
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmRSS:'):result['rss_mb']=int(line.split()[1])/1024
            if line.startswith('Threads:'):result['threads']=int(line.split()[1])
        result['sockets']=sum(os.readlink(p).startswith('socket:') for p in Path('/proc/self/fd').iterdir() if p.exists())
    return result
