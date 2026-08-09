from pathlib import Path
from sysconfig import get_path

if __name__ == "__main__":
    module_root = Path(__file__).resolve().parents[1]
    (module_root / "compile_flags.txt").write_text(
        f"-I{get_path('include')}\n",
        encoding="utf-8",
    )
