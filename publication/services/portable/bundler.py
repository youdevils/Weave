"""
Inlines ES modules into one script so the published file needs no module loader.

Weave has no JS build step in production (the image has no Node), and a module
graph cannot be loaded from a single ``file://`` document anyway. This does the
one transformation needed, for a deliberately *strict subset* of ES modules:

  * static ``import { a, b } from "./relative.js"`` (plain names only);
  * ``export function|class|const|let|var name`` at the start of a line.

Anything outside that subset (default exports, renames, namespace imports,
side-effect imports, ``export { ... }`` lists, dynamic ``import()``,
``import.meta``, cycles, top-level name collisions between modules, importing a
name the target does not export) is an error, so a change to the shared Explorer
modules that the inliner cannot represent fails loudly in tests instead of
producing a broken file.

The result is a classic script wrapped in an IIFE: module-private names cannot
leak or collide with the page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class BundleError(Exception):
    """The module graph is outside the subset this inliner supports."""


@dataclass(frozen=True)
class BundledScript:
    code: str
    modules: tuple  # module paths in the order they appear in ``code``


_IMPORT = re.compile(
    r"^import\s*\{(?P<names>[^}]*)\}\s*from\s*(?P<quote>[\"'])(?P<spec>[^\"']+)(?P=quote)\s*;?[ \t]*$",
    re.MULTILINE,
)
_ANY_IMPORT = re.compile(r"^\s*import\b(?!\s*\()", re.MULTILINE)
_DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(")
_IMPORT_META = re.compile(r"\bimport\.meta\b")
_EXPORT_DECLARATION = re.compile(
    r"^export\s+(?P<kind>async\s+function\*?|function\*?|class|const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_ANY_EXPORT = re.compile(r"^\s*export\b", re.MULTILINE)
_TOP_LEVEL = re.compile(
    r"^(?:export\s+)?(?:async\s+function\*?|function\*?|class|const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_SOURCE_MAP = re.compile(r"^\s*//[#@]\s*sourceMappingURL=.*$", re.MULTILINE)


def _parse_names(raw: str, module: Path) -> list[str]:
    names = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not re.fullmatch(r"[A-Za-z_$][\w$]*", part):
            raise BundleError(f"{module}: unsupported import binding {part!r} (renames are not supported)")
        names.append(part)
    return names


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise BundleError(f"Cannot read module {path}: {error}") from None


def bundle_modules(entry: Path) -> BundledScript:
    """Bundle ``entry`` and everything it imports (relative specifiers only) into one script."""
    entry = Path(entry).resolve()
    order: list[Path] = []
    sources: dict[Path, str] = {}
    exports: dict[Path, set] = {}
    visiting: set = set()

    def visit(path: Path) -> None:
        if path in sources:
            return
        if path in visiting:
            raise BundleError(f"Import cycle involving {path}")
        visiting.add(path)

        source = _read(path)
        if _DYNAMIC_IMPORT.search(source):
            raise BundleError(f"{path}: dynamic import() is not supported")
        if _IMPORT_META.search(source):
            raise BundleError(f"{path}: import.meta is not supported")

        matched = list(_IMPORT.finditer(source))
        if len(matched) != len(_ANY_IMPORT.findall(source)):
            raise BundleError(f"{path}: only `import {{ names }} from \"./module.js\"` statements are supported")

        for match in matched:
            spec = match.group("spec")
            if not spec.startswith("."):
                raise BundleError(f"{path}: only relative imports are supported, found {spec!r}")
            visit((path.parent / spec).resolve())

        declared = {m.group("name") for m in _EXPORT_DECLARATION.finditer(source)}
        if len(_ANY_EXPORT.findall(source)) != len(_EXPORT_DECLARATION.findall(source)):
            raise BundleError(
                f"{path}: only `export function|class|const|let|var name` declarations are supported"
            )

        visiting.discard(path)
        sources[path] = source
        exports[path] = declared
        order.append(path)

    visit(entry)

    # Every imported name must exist in its target.
    for path in order:
        for match in _IMPORT.finditer(sources[path]):
            target = (path.parent / match.group("spec")).resolve()
            for name in _parse_names(match.group("names"), path):
                if name not in exports[target]:
                    raise BundleError(f"{path}: {target.name} does not export {name!r}")

    # Inlined modules share one scope, so their top-level names must be unique.
    owner: dict[str, Path] = {}
    for path in order:
        for match in _TOP_LEVEL.finditer(sources[path]):
            name = match.group("name")
            if name in owner and owner[name] != path:
                raise BundleError(f"Top-level name {name!r} is declared in both {owner[name]} and {path}")
            owner[name] = path

    parts = []
    for path in order:
        code = _IMPORT.sub("", sources[path])
        code = re.sub(r"^export\s+", "", code, flags=re.MULTILINE)
        code = _SOURCE_MAP.sub("", code)
        parts.append(f"/* ---- {path.name} ---- */\n{code.strip()}\n")

    body = "\n".join(parts)
    return BundledScript(code=f'(() => {{\n"use strict";\n{body}}})();\n', modules=tuple(order))
