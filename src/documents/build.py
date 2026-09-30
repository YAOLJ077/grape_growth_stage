#!/usr/bin/env python3
"""Rebuild the final PDF and editable Word submission documents."""
from pathlib import Path
import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CODE = Path(__file__).resolve().parent


def run(command, env):
    subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'paper')
    parser.add_argument('--build-dir', type=Path, default=ROOT / 'build/documents')
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--pdf-only', action='store_true')
    choice.add_argument('--word-only', action='store_true', help='Requires current auxiliary files in the compiler cache')
    choice.add_argument('--verify-only', action='store_true', help='Verify existing DOCX files; requires current compiler cache')
    args = parser.parse_args()
    output, build = args.output_dir.resolve(), args.build_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = build / 'latex'
    cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GRAPE_DOCUMENT_OUTPUT=str(output), GRAPE_DOCUMENT_BUILD=str(build))
    if not args.pdf_only and not args.verify_only:
        run([sys.executable, CODE / 'build_front_matter.py'], env)
    if not args.word_only and not args.verify_only:
        tectonic = shutil.which('tectonic')
        if not tectonic and (ROOT / '.venv/bin/tectonic').exists():
            tectonic = str(ROOT / '.venv/bin/tectonic')
        if not tectonic:
            raise RuntimeError('Install Tectonic and put it on PATH to compile the LaTeX sources')
        for name in ('manuscript', 'supplementary', 'cover_letter'):
            source = ROOT / 'paper' / ('afm_submission' if name == 'cover_letter' else '') / (name + '.tex')
            if name == 'cover_letter' and not args.pdf_only:
                source = build / 'front_matter/cover_letter.tex'
            run([tectonic, '--keep-logs', '--keep-intermediates', '--outdir', cache,
                 source], env)
            log = (cache / (name + '.log')).read_text(errors='replace')
            if re.search(r'Overfull \\[hv]box|undefined|LaTeX Error|Float too large', log, re.I):
                raise RuntimeError(f'Unresolved compilation or layout warning in {name}.log')
            target = output / ('afm_submission' if name == 'cover_letter' else '') / (name + '.pdf')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache / (name + '.pdf'), target)
        if args.pdf_only:
            return
    if not args.verify_only:
        for name in ('build_manuscript.py', 'build_supplementary.py', 'build_complete.py'):
            run([sys.executable, CODE / name], env)
    for name in ('verify_citations.py', 'verify_documents.py'):
        run([sys.executable, CODE / name], env)


if __name__ == '__main__':
    main()
