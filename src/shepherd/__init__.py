"""FPGA Shepherd: set up, build, flash and diagnose FPGA projects."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fpga-shepherd")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0+unknown"
