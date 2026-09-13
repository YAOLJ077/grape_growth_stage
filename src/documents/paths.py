"""Shared source, delivery and disposable build locations."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / 'paper'
BUILD_ROOT = Path(os.environ.get('GRAPE_DOCUMENT_BUILD', ROOT / 'build/documents')).resolve()
DELIVERY = Path(os.environ.get('GRAPE_DOCUMENT_OUTPUT', PAPER)).resolve()
LATEX = BUILD_ROOT / 'latex'
CITATIONS = BUILD_ROOT / 'citations'


def build_directory(name):
    path = BUILD_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def compiled(name, suffix):
    """Use the compiler cache, never tracked auxiliary files."""
    path = LATEX / f'{name}.{suffix}'
    if not path.exists():
        raise FileNotFoundError(f'{path}: run src/documents/build.py first')
    return path


DELIVERY.mkdir(parents=True, exist_ok=True)
