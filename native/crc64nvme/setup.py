from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class build_ext_with_stub(build_ext):
    def run(self):
        super().run()
        self.copy_file(
            Path(__file__).parent / "src" / "_crc64nvme.pyi",
            Path(self.build_lib) / "_crc64nvme.pyi",
        )


setup(
    ext_modules=[
        Extension(
            "_crc64nvme",
            ["src/crc64nvme.c"],
        )
    ],
    cmdclass={"build_ext": build_ext_with_stub},
)
