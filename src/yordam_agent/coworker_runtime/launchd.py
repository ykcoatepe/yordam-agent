import plistlib
import shutil
import sys
from pathlib import Path
from typing import Optional


DEFAULT_LAUNCHD_LABEL = "com.yordam.agent.coworker-runtime"
DEFAULT_STDOUT_PATH = Path("/tmp/yordam-agent.coworker-runtime.out")
DEFAULT_STDERR_PATH = Path("/tmp/yordam-agent.coworker-runtime.err")


def resolve_program_path(raw: Optional[str]) -> Optional[Path]:
    if raw:
        path = Path(raw).expanduser()
        if path.exists():
            return path.resolve()
        return None
    detected = shutil.which("yordam-agent")
    if detected:
        return Path(detected).resolve()
    argv0 = Path(sys.argv[0]).expanduser()
    if argv0.exists():
        return argv0.resolve()
    return None


def render_launchd_plist(
    *,
    program: Path,
    label: str = DEFAULT_LAUNCHD_LABEL,
    state_dir: Optional[Path] = None,
    workers: Optional[int] = None,
    poll_seconds: Optional[float] = None,
    worker_id: Optional[str] = None,
    stdout_path: Optional[Path] = DEFAULT_STDOUT_PATH,
    stderr_path: Optional[Path] = DEFAULT_STDERR_PATH,
    enable_runtime_env: bool = False,
    run_at_load: bool = True,
    keep_alive: bool = True,
) -> str:
    args = [str(program), "coworker-runtime", "daemon"]
    if worker_id:
        args.extend(["--worker-id", worker_id])
    if workers is not None:
        args.extend(["--workers", str(int(workers))])
    if poll_seconds is not None:
        args.extend(["--poll-seconds", str(poll_seconds)])
    if state_dir is not None:
        args.extend(["--state-dir", str(state_dir)])

    payload = {
        "Label": label,
        "ProgramArguments": args,
        "RunAtLoad": bool(run_at_load),
        "KeepAlive": bool(keep_alive),
    }
    if stdout_path is not None:
        payload["StandardOutPath"] = str(stdout_path)
    if stderr_path is not None:
        payload["StandardErrorPath"] = str(stderr_path)
    if enable_runtime_env:
        payload["EnvironmentVariables"] = {"YORDAM_COWORKER_RUNTIME_ENABLED": "1"}

    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False).decode("utf-8")
