import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional


class FFmpegError(Exception):
    pass


class FFmpegNotFoundError(FFmpegError):
    pass


class InvalidPathError(FFmpegError):
    pass


_SHELL_METACHARACTERS = re.compile(r'[;|&$`()<>!\n\r]')
_TRAVERSAL_PATTERN = re.compile(r'\.\.')


def validate_file_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise InvalidPathError("File path must be a non-empty string")

    if _SHELL_METACHARACTERS.search(path):
        raise InvalidPathError(
            f"Path contains shell metacharacters: {path!r}"
        )

    if _TRAVERSAL_PATTERN.search(path):
        raise InvalidPathError(
            f"Path contains directory traversal sequence '..': {path!r}"
        )

    resolved = os.path.realpath(path)

    if _SHELL_METACHARACTERS.search(resolved):
        raise InvalidPathError(
            f"Resolved path contains shell metacharacters: {resolved!r}"
        )

    if _TRAVERSAL_PATTERN.search(resolved):
        raise InvalidPathError(
            f"Resolved path contains directory traversal sequence '..': {resolved!r}"
        )

    if not os.path.exists(resolved):
        raise InvalidPathError(f"File does not exist: {resolved!r}")

    if not os.path.isfile(resolved):
        raise InvalidPathError(f"Path is not a regular file: {resolved!r}")

    return resolved


def validate_output_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise InvalidPathError("Output path must be a non-empty string")

    if _SHELL_METACHARACTERS.search(path):
        raise InvalidPathError(
            f"Output path contains shell metacharacters: {path!r}"
        )

    if _TRAVERSAL_PATTERN.search(path):
        raise InvalidPathError(
            f"Output path contains directory traversal sequence '..': {path!r}"
        )

    resolved = os.path.realpath(path)

    if _SHELL_METACHARACTERS.search(resolved):
        raise InvalidPathError(
            f"Resolved output path contains shell metacharacters: {resolved!r}"
        )

    if _TRAVERSAL_PATTERN.search(resolved):
        raise InvalidPathError(
            f"Resolved output path contains directory traversal sequence '..': {resolved!r}"
        )

    parent_dir = os.path.dirname(resolved)
    if parent_dir and not os.path.isdir(parent_dir):
        raise InvalidPathError(
            f"Parent directory does not exist: {parent_dir!r}"
        )

    return resolved


@dataclass
class FFmpegResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class FFmpegRunner:
    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        ffprobe_path: Optional[str] = None,
        default_timeout: Optional[float] = None,
    ):
        self._ffmpeg_path = ffmpeg_path or self._find_executable("ffmpeg")
        self._ffprobe_path = ffprobe_path or self._find_executable("ffprobe")
        self._default_timeout = default_timeout

    @staticmethod
    def _find_executable(name: str) -> str:
        path = shutil.which(name)
        if path is None:
            raise FFmpegNotFoundError(
                f"{name} executable not found in PATH"
            )
        return path

    def run_ffmpeg(
        self,
        args: List[str],
        input_paths: Optional[List[str]] = None,
        output_paths: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> FFmpegResult:
        if input_paths:
            for p in input_paths:
                validate_file_path(p)

        if output_paths:
            for p in output_paths:
                validate_output_path(p)

        cmd = [self._ffmpeg_path] + args

        effective_timeout = timeout if timeout is not None else self._default_timeout

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=effective_timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            raise FFmpegError(
                f"FFmpeg process timed out after {effective_timeout} seconds"
            )
        except FileNotFoundError:
            raise FFmpegNotFoundError(
                f"FFmpeg executable not found: {self._ffmpeg_path!r}"
            )
        except OSError as exc:
            raise FFmpegError(f"Failed to execute FFmpeg: {exc}") from exc

        return FFmpegResult(
            returncode=proc.returncode,
            stdout=proc.stdout.decode("utf-8", errors="replace"),
            stderr=proc.stderr.decode("utf-8", errors="replace"),
        )

    def run_ffmpeg_progress(
        self,
        args: List[str],
        progress_callback: Optional[Callable[[float], None]] = None,
        input_paths: Optional[List[str]] = None,
        output_paths: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> FFmpegResult:
        if input_paths:
            for p in input_paths:
                validate_file_path(p)

        if output_paths:
            for p in output_paths:
                validate_output_path(p)

        cmd = [self._ffmpeg_path, "-progress", "pipe:1"] + args

        effective_timeout = timeout if timeout is not None else self._default_timeout

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except FileNotFoundError:
            raise FFmpegNotFoundError(
                f"FFmpeg executable not found: {self._ffmpeg_path!r}"
            )
        except OSError as exc:
            raise FFmpegError(f"Failed to execute FFmpeg: {exc}") from exc

        stdout_lines: List[str] = []
        stderr_lines: List[str] = []

        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue

                decoded = line.decode("utf-8", errors="replace").rstrip()
                stdout_lines.append(decoded)

                if progress_callback and decoded.startswith("out_time_ms="):
                    try:
                        time_us = int(decoded.split("=")[1])
                        progress_callback(time_us / 1_000_000.0)
                    except (ValueError, IndexError):
                        pass

            remaining_stderr = proc.stderr.read()
            if remaining_stderr:
                stderr_lines.append(
                    remaining_stderr.decode("utf-8", errors="replace")
                )

            proc.wait(timeout=effective_timeout)

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise FFmpegError(
                f"FFmpeg process timed out after {effective_timeout} seconds"
            )

        return FFmpegResult(
            returncode=proc.returncode,
            stdout="\n".join(stdout_lines),
            stderr="\n".join(stderr_lines),
        )

    def run_ffprobe(
        self,
        args: List[str],
        input_paths: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> FFmpegResult:
        if input_paths:
            for p in input_paths:
                validate_file_path(p)

        cmd = [self._ffprobe_path] + args

        effective_timeout = timeout if timeout is not None else self._default_timeout

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=effective_timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            raise FFmpegError(
                f"FFprobe process timed out after {effective_timeout} seconds"
            )
        except FileNotFoundError:
            raise FFmpegNotFoundError(
                f"FFprobe executable not found: {self._ffprobe_path!r}"
            )
        except OSError as exc:
            raise FFmpegError(f"Failed to execute FFprobe: {exc}") from exc

        return FFmpegResult(
            returncode=proc.returncode,
            stdout=proc.stdout.decode("utf-8", errors="replace"),
            stderr=proc.stderr.decode("utf-8", errors="replace"),
        )
