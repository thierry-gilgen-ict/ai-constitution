"""Optional local inference control plane. The constitution core stays dependency-free."""
from pathlib import Path
import sys

def application_version():
    source = Path(sys._MEIPASS) / 'library' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
    return (source / 'VERSION').read_text(encoding='utf-8').strip()

VERSION = application_version()
