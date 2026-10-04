#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from common import ROOT, BuildError, require

REFERENCE_DEFINITION_RE = re.compile(r'^\s*\[[^\]]+\]:\s*', re.MULTILINE)
EXTERNAL_SCHEMES = {'data', 'http', 'https', 'mailto'}


def _without_fenced_code(text: str) -> str:
    lines: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        marker = '~~~' if stripped.startswith('~~~') else None
        if marker is None and stripped.startswith(chr(96) * 3):
            marker = chr(96) * 3
        if marker is not None:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            lines.append('')
            continue
        lines.append('' if fence is not None else line)
    return '\n'.join(lines)


def _parse_destination(
    text: str,
    start: int,
    *,
    inline: bool,
) -> tuple[str, int] | None:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text):
        return None

    if text[index] == '<':
        end = index + 1
        escaped = False
        while end < len(text):
            char = text[end]
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '>':
                return text[index : end + 1], end + 1
            elif char in '\n\r':
                return None
            end += 1
        return None

    depth = 0
    end = index
    escaped = False
    while end < len(text):
        char = text[end]
        if escaped:
            escaped = False
            end += 1
            continue
        if char == '\\':
            escaped = True
            end += 1
            continue
        if char == '(':
            depth += 1
            end += 1
            continue
        if char == ')':
            if depth > 0:
                depth -= 1
                end += 1
                continue
            if inline:
                break
            return None
        if char.isspace() and depth == 0:
            break
        end += 1

    if end == index or depth != 0:
        return None
    return text[index:end], end


def _inline_targets(text: str) -> list[str]:
    targets: list[str] = []
    search_from = 0
    while True:
        marker = text.find('](', search_from)
        if marker < 0:
            return targets
        parsed = _parse_destination(text, marker + 2, inline=True)
        if parsed is not None:
            target, end = parsed
            targets.append(target)
            search_from = max(end, marker + 2)
        else:
            search_from = marker + 2


def _reference_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in REFERENCE_DEFINITION_RE.finditer(text):
        parsed = _parse_destination(text, match.end(), inline=False)
        if parsed is not None:
            targets.append(parsed[0])
    return targets


def _target_path(markdown: Path, raw_target: str, root: Path) -> Path | None:
    target = raw_target.strip()
    if target.startswith('<') and target.endswith('>'):
        target = target[1:-1]
    if not target or target.startswith('#'):
        return None

    parsed = urlsplit(target)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc:
        return None

    path_text = unquote(parsed.path)
    if not path_text:
        return None

    if path_text.startswith('/'):
        candidate = root / path_text.lstrip('/')
    else:
        candidate = markdown.parent / path_text
    resolved = candidate.resolve()
    relative = markdown.relative_to(root)
    require(
        resolved.is_relative_to(root.resolve()),
        f'Markdown link escapes repository: {relative} -> {raw_target}',
    )
    return resolved


def find_broken_links(paths: list[Path], *, root: Path) -> list[str]:
    root = root.resolve()
    broken: list[str] = []
    for markdown in paths:
        markdown = markdown.resolve()
        require(
            markdown.is_relative_to(root),
            f'Markdown input escapes repository: {markdown}',
        )
        text = _without_fenced_code(markdown.read_text(encoding='utf-8'))
        targets = _inline_targets(text)
        targets.extend(_reference_targets(text))
        for target in targets:
            resolved = _target_path(markdown, target, root)
            if resolved is not None and not resolved.exists():
                broken.append(
                    f'{markdown.relative_to(root).as_posix()} -> {target} '
                    f'(missing {resolved.relative_to(root).as_posix()})'
                )
    return sorted(set(broken))


def tracked_markdown(root: Path) -> list[Path]:
    output = subprocess.check_output(['git', 'ls-files', '-z', '*.md'], cwd=root)
    return [root / item.decode() for item in output.split(b'\0') if item]


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Validate repository-local links in tracked Markdown'
    )
    parser.add_argument('paths', nargs='*', type=Path)
    args = parser.parse_args()

    root = ROOT.resolve()
    if args.paths:
        paths = [path.resolve() for path in args.paths]
    else:
        paths = tracked_markdown(root)
    broken = find_broken_links(paths, root=root)
    if broken:
        raise BuildError('broken repository Markdown links:\n' + '\n'.join(broken))
    print(f'Markdown links: ok ({len(paths)} files)')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
