"""Native process lifecycle test. Starts only this project's own application."""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app"))
from halo_text.paths import configure
configure()
from halo_text.ipc import request

def wait_for(predicate,seconds=45):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=predicate()
        if result:
            return result
        time.sleep(.2)
    raise RuntimeError("Lifecycle test timed out")

if request("status").get("running"):
    raise RuntimeError("Close the existing HALO TEXT instance before running this test.")
output=ROOT/"reports"/"lifecycle_process.log"
with output.open("w",encoding="utf-8") as log:
    process=subprocess.Popen([sys.executable,"app/run.py"],cwd=ROOT,
        stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        started=time.monotonic()
        def ready():
            if process.poll() is not None:
                raise RuntimeError("Application exited before readiness; inspect lifecycle_process.log")
            state=request("status")
            return state if state.get("ready") else None
        state=wait_for(ready)
        # Windows venv launchers may create a child interpreter process.
        runtime_pid=int((ROOT/"runtime/state"/"halo.lock").read_text().splitlines()[0])
        assert state["pid"]==runtime_pid and not state["hotkey_conflicts"],state
        startup_seconds=round(time.monotonic()-started,2)
        duplicate=subprocess.run([sys.executable,"app/run.py"],cwd=ROOT,
            stdout=log,stderr=subprocess.STDOUT,timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW)
        assert duplicate.returncode==0
        assert request("status")["pid"]==runtime_pid
        assert request("original")["original_visible"]
        assert not request("original")["original_visible"]
        assert request("clear")["displayed_blocks"]==0
        assert request("stop")["running"]
        process.wait(timeout=45)
        assert process.returncode==0
        assert not request("status")["running"]
        report={"status_returns_live_pid":True,"ready":True,
                "duplicate_launch_reuses_instance":True,"clear_command":True,"original_command":True,
                "graceful_stop_exit_code":process.returncode,
                "status_after_stop_running":False,"startup_seconds":startup_seconds}
        (ROOT/"reports"/"lifecycle_smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
    finally:
        if process.poll() is None:
            state=request("status")
            if state.get("running"):
                request("stop")
                process.wait(timeout=45)
