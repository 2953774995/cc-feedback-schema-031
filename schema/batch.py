"""Batch validation helpers for :class:`schema.Schema`.

`Schema.validate` raises on the first offending document, which makes it
awkward to validate a whole batch of responses and report where each one
failed.  This module keeps the existing single-document behavior untouched
and adds a thin loop on top of it::

    from schema import Schema
    from schema.batch import check_many

    result = check_many(Schema({"name": str, "age": int}), docs)
    result.failed        # indexes of documents that did not validate
    result.results[0]    # {"index": 0, "ok": True, "error_path": None, ...}

For a failing document ``error_path`` is a tuple of keys locating the first
problem (``("user", "name")`` for a nested failure, ``()`` when the failure
is on the document itself).  The tuple is derived from the error message
chain that ``Schema.validate`` already produces, so no core code changes.
"""

import ast
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from . import Schema, SchemaError

__all__ = ["BatchResult", "check_many"]


#: One entry of :attr:`BatchResult.results`.
CheckResult = Dict[str, Any]

_ERROR_PATH = Optional[Tuple[Any, ...]]

_KEY_RE = re.compile(r"^Key (.*) error:$")
_MISSING_RE = re.compile(r"^Missing keys?: (.*)$")
_WRONG_RE = re.compile(r"^Wrong keys? (.*?) in ")
_FORBIDDEN_RE = re.compile(r"^Forbidden key encountered: (.*?) in ")


def _unquote(value: str) -> str:
    """Strip one layer of matching quotes added by ``%s`` in error messages."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _first_key(value: str) -> Any:
    """Return the first key of a ``repr``-ed key list, e.g. ``'a', 'b'``."""
    try:
        keys = ast.literal_eval("(" + value + ",)")
    except (ValueError, SyntaxError):
        keys = ()
    if isinstance(keys, tuple) and keys:
        return keys[0]
    return _unquote(value.split(",")[0].strip())


def _extract_error_path(exc: SchemaError) -> Tuple[Any, ...]:
    """Locate the first failing field from a ``SchemaError`` message chain.

    ``Schema.validate`` prefixes nested failures with ``Key 'k' error:`` and
    ends the chain with a message such as ``Missing key: 'k'`` or
    ``Wrong key 'k' in ...``.  Walking those messages in order yields the
    path of the first offending field.
    """
    messages: List[str] = []
    for message in list(exc.autos) + list(exc.errors):
        if isinstance(message, str):
            messages.append(message)

    path: List[Any] = []
    for message in messages:
        for line in message.splitlines():
            line = line.strip()

            match = _KEY_RE.match(line)
            if match:
                path.append(_unquote(match.group(1)))
                continue

            match = _MISSING_RE.match(line)
            if match:
                path.append(_first_key(match.group(1)))
                return tuple(path)

            match = _WRONG_RE.match(line)
            if match:
                path.append(_first_key(match.group(1)))
                return tuple(path)

            match = _FORBIDDEN_RE.match(line)
            if match:
                path.append(_first_key(match.group(1)))
                return tuple(path)

    return tuple(path)


class BatchResult:
    """Outcome of :func:`check_many`.

    :ivar results: one dict per document, in input order, with keys
        ``index``, ``ok``, ``error_path`` and ``error``.
    :ivar failed: indexes of the documents that did not validate.
    """

    def __init__(self, results: List[CheckResult], failed: List[int]) -> None:
        self.results: List[CheckResult] = results
        self.failed: List[int] = failed

    @property
    def ok(self) -> bool:
        """Whether every document in the batch validated."""
        return not self.failed

    def __len__(self) -> int:
        return len(self.results)

    def __repr__(self) -> str:
        return "BatchResult(%d checked, %d failed)" % (
            len(self.results),
            len(self.failed),
        )


def check_many(schema: Union[Schema, Any], docs: Iterable[Any]) -> BatchResult:
    """Validate every document in ``docs`` against ``schema``.

    :param schema: a :class:`schema.Schema` instance, or a schema definition
        accepted by its constructor.
    :param docs: iterable of documents; each one is validated independently.
    :return: a :class:`BatchResult` with per-document outcomes and the list
        of failed indexes.
    """
    if not isinstance(schema, Schema):
        schema = Schema(schema)

    results: List[CheckResult] = []
    failed: List[int] = []
    for index, doc in enumerate(docs):
        try:
            schema.validate(doc)
        except SchemaError as exc:
            error_path: _ERROR_PATH = _extract_error_path(exc)
            results.append(
                {
                    "index": index,
                    "ok": False,
                    "error_path": error_path,
                    "error": exc.code,
                }
            )
            failed.append(index)
        else:
            results.append(
                {"index": index, "ok": True, "error_path": None, "error": None}
            )

    return BatchResult(results, failed)
