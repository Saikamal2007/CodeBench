import os
import subprocess
import tempfile
import time
import concurrent.futures
from dataclasses import dataclass

LANGUAGE_CONFIG = {
    "python": {
        "image": "python:3.11-slim",
        "filename": "solution.py",
        "compile_cmd": None,
        "run_cmd_docker": "python3 /code/solution.py < /code/input.txt",
        "run_local": lambda d: ["python3", os.path.join(d, "solution.py")],
        "compile_local": None,
    },
    "cpp": {
        "image": "gcc:13",
        "filename": "solution.cpp",
        "compile_cmd": "g++ -O2 -o /code/solution /code/solution.cpp",
        "run_cmd_docker": "/code/solution < /code/input.txt",
        "run_local": lambda d: [os.path.join(d, "solution")],
        "compile_local": lambda d: [
            "g++",
            "-O2",
            "-o",
            os.path.join(d, "solution"),
            os.path.join(d, "solution.cpp"),
        ],
    },
    "java": {
        "image": "eclipse-temurin:17-jdk", 
        "filename": "Solution.java",
        "compile_cmd": "javac /code/Solution.java",
        "run_cmd_docker": "java -cp /code Solution < /code/input.txt",
        "run_local": lambda d: ["java", "-cp", d, "Solution"],
        "compile_local": lambda d: ["javac", os.path.join(d, "Solution.java")],
    },
}


def normalize(text: str) -> str:
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")


def _docker_run_blocking(client, image, cmd, code_dir, time_limit_s, memory_limit_mb):
    import docker as docker_sdk

    start = time.time()
    try:
        output = client.containers.run(
            image,
            ["sh", "-c", cmd],
            volumes={code_dir: {"bind": "/code", "mode": "rw"}},
            mem_limit=f"{memory_limit_mb}m",
            memswap_limit=f"{memory_limit_mb}m",
            network_disabled=True,
            remove=True,
            stdout=True,
            stderr=True,
        )
        runtime_ms = int((time.time() - start) * 1000)
        return 0, output.decode("utf-8", errors="replace"), "", runtime_ms
    except docker_sdk.errors.ContainerError as e:
        runtime_ms = int((time.time() - start) * 1000)
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        return e.exit_status, "", stderr, runtime_ms
    except Exception as e:
        runtime_ms = int((time.time() - start) * 1000)
        return -1, "", str(e), runtime_ms


def _run_subprocess(cmd, stdin_text, time_limit_s):
    """Run a command with stdin, return (exit_code, stdout, stderr, runtime_ms)."""
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=time_limit_s + 1,
        )
        runtime_ms = int((time.time() - start) * 1000)
        return proc.returncode, proc.stdout, proc.stderr, runtime_ms
    except subprocess.TimeoutExpired:
        runtime_ms = int(time_limit_s * 1000) + 1000
        return -9, "", "Time limit exceeded", runtime_ms
    except Exception as e:
        runtime_ms = int((time.time() - start) * 1000)
        return -1, "", str(e), runtime_ms


def _judge_with_subprocess(config, code, test_cases, time_limit_ms, memory_limit_mb):
    """Judge using local compilers via subprocess."""
    time_limit_s = time_limit_ms / 1000.0

    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = os.path.join(tmpdir, config["filename"])
        with open(code_file, "w") as f:
            f.write(code)

        # Compile step
        compile_fn = config["compile_local"]
        if compile_fn:
            compile_cmd = compile_fn(tmpdir)
            exit_code, stdout, stderr, _ = _run_subprocess(compile_cmd, "", 30)
            if exit_code != 0:
                return "compilation_error", 0,stderr

        max_runtime_ms = 0
        run_fn = config["run_local"]

        for tc in test_cases:
            stdin_text = tc.input or ""
            run_cmd = run_fn(tmpdir)
            exit_code, stdout, stderr, runtime_ms = _run_subprocess(
                run_cmd, stdin_text, time_limit_s
            )

            max_runtime_ms = max(max_runtime_ms, runtime_ms)

            if runtime_ms > time_limit_ms + 1000:
                return "time_limit_exceeded", max_runtime_ms

            if "Time limit exceeded" in stderr:
                return "time_limit_exceeded", max_runtime_ms

            if exit_code != 0:
                return "runtime_error", max_runtime_ms

            actual = normalize(stdout)
            expected = normalize(tc.expected_output)

            if actual != expected:
                return "wrong_answer", max_runtime_ms

    return "accepted", max_runtime_ms


def _judge_with_docker(
    client, config, code, test_cases, time_limit_ms, memory_limit_mb
):
    """Judge using Docker containers."""
    time_limit_s = time_limit_ms / 1000.0

    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = os.path.join(tmpdir, config["filename"])
        with open(code_file, "w") as f:
            f.write(code)

        if config["compile_cmd"]:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(
                    _docker_run_blocking,
                    client,
                    config["image"],
                    config["compile_cmd"],
                    tmpdir,
                    30,
                    memory_limit_mb,
                )
                try:
                    exit_code, _, stderr, _ = future.result(timeout=35)
                except concurrent.futures.TimeoutError:
                    return "compilation_error", 0
            if exit_code != 0:
                return "compilation_error", 0,stderr

        max_runtime_ms = 0

        for tc in test_cases:
            input_file = os.path.join(tmpdir, "input.txt")
            with open(input_file, "w") as f:
                f.write(tc.input or "")

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(
                    _docker_run_blocking,
                    client,
                    config["image"],
                    config["run_cmd_docker"],
                    tmpdir,
                    time_limit_s,
                    memory_limit_mb,
                )
                try:
                    exit_code, stdout, stderr, runtime_ms = future.result(
                        timeout=time_limit_s + 5
                    )
                except concurrent.futures.TimeoutError:
                    return "time_limit_exceeded", time_limit_ms

            max_runtime_ms = max(max_runtime_ms, runtime_ms)

            if runtime_ms > time_limit_ms:
                return "time_limit_exceeded", max_runtime_ms

            if exit_code != 0:
                return "runtime_error", max_runtime_ms

            actual = normalize(stdout)
            expected = normalize(tc.expected_output)

            if actual != expected:
                return "wrong_answer", max_runtime_ms

    return "accepted", max_runtime_ms


def judge_submission(
    language: str, code: str, test_cases: list, time_limit_ms: int, memory_limit_mb: int
) -> tuple:
    """
    Judge a submission against all test cases.
    Uses Docker if available, falls back to local subprocess execution.
    Returns (verdict, runtime_ms).
    """
    config = LANGUAGE_CONFIG.get(language)
    if not config:
        return "runtime_error", 0

    # Try Docker first
    try:
        import docker as docker_sdk

        client = docker_sdk.from_env(timeout=5)
        client.ping()
        return _judge_with_docker(
            client, config, code, test_cases, time_limit_ms, memory_limit_mb
        )
    except Exception:
        pass

    # Fall back to local subprocess execution
    return _judge_with_subprocess(
        config, code, test_cases, time_limit_ms, memory_limit_mb
    )
