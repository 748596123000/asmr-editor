import os
import tempfile
import threading


class TempFileManager:
    def __init__(self):
        self._temp_files: list[str] = []
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.cleanup()
        except OSError:
            pass
        return False

    def create_temp(self, suffix: str = "", prefix: str = "asmr_") -> str:
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        os.close(fd)
        os.chmod(path, 0o600)
        with self._lock:
            self._temp_files.append(path)
        return path

    def cleanup(self):
        with self._lock:
            files = list(self._temp_files)
            self._temp_files.clear()
        for path in files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass


def secure_temp_directory() -> str:
    return tempfile.mkdtemp(prefix="asmr_")
