from typing import Any, Generator, Callable, Iterable, TYPE_CHECKING
import fnmatch
from lark import Lark, Transformer, LarkError
from rapidfuzz import fuzz

if TYPE_CHECKING:
    from .hkb_types import HkbRecord, HkbArray


# See https://lucene.apache.org/core/2_9_4/queryparsersyntax.html
lucene_grammar = r"""
    ?start: or_expr

    ?or_expr: and_expr ("OR" and_expr)*     -> or_
    ?and_expr: not_expr+                    -> and_
    ?not_expr: "NOT" not_expr               -> not_
             | atom

    ?atom: field
         | bare_value
         | "(" or_expr ")"

    field: PATH_OR_STR ":" VALUE_TOKEN      -> field
    bare_value: VALUE_TOKEN                 -> value

    PATH_OR_STR: PATH | ESCAPED_STRING
    VALUE_TOKEN: RANGE | FUZZY | WILDCARD | WORD | ESCAPED_STRING
    PATH      : /[A-Za-z_][A-Za-z0-9_.]*/
    RANGE     : /\[[^\[\]]+ TO [^\[\]]+\]/
    FUZZY     : /~[^\s()]+/
    WILDCARD  : /[^\s()]+[*]/
    WORD      : /[^\s()]+/

    %import common.ESCAPED_STRING
    %import common.WS
    %ignore WS
"""


lucene_url = "https://lucene.apache.org/core/2_9_4/queryparsersyntax.html"


lucene_help_text = """\
Supports Lucene-style search queries (<field>:<value>). 

- Fields are used verbatim, with the only excception that array indices may be replaced by a * wildcard.
- Values may be specified using fields, wildcards, fuzzy searches, ranges.
- Terms may be combined using grouping, OR, NOT. 
- Termas separated by a space are assumed to be AND.

You may run queries over the following fields:
- id
- object_id (same as id)
- type_id
- type_name
- name
- any attribute path

Examples:
- id:*588 OR type_name:hkbStateMachine
- "bindings:0/memberPath":selectedGeneratorIndex
- animId:[100000 TO 200000]
- name:~AddDamageFire
"""


parser = Lark(
    lucene_grammar, start="start", propagate_positions=False, maybe_placeholders=False
)


class QueryTransformer(Transformer):
    def __init__(self, record: "HkbRecord"):
        self.record = record

    # logic nodes
    def or_(self, args: list[str]) -> bool:
        return any(args)

    def and_(self, args: list[str]) -> bool:
        return all(args)

    def not_(self, args: list[str]) -> bool:
        return not args[0]

    # terminals
    def field(self, args: list[str]) -> bool:
        path, token = str(args[0]), str(args[1])
        return self._match(path, token)

    def value(self, args: list[str]) -> bool:
        # Called when no fields are specified
        token = str(args[0])

        return any(
            self._match(path, token)
            for path in ("object_id", "name", "type_name", "type_id")
        )

    def _is_matching(self, value: Any, token: str) -> bool:
        # fuzzy
        if token.startswith("~"):
            return fuzz.partial_ratio(value, token[1:]) >= 50

        # wildcard
        if "*" in token:
            return fnmatch.fnmatch(value, token)

        # range
        if token.startswith("[") and " TO " in token:
            lo, hi = token.strip("[]").split(" TO ")
            try:
                return float(lo) <= float(value) <= float(hi)
            except ValueError:
                return False

        # Exact match
        if not isinstance(value, str):
            value = str(value)

        return value == token

    # common matching function
    def _match(self, path: str, token: str) -> bool:
        from hkb_editor.hkb.hkb_types import XmlValueHandler

        if (path.startswith("'") and path.endswith("'")) or (
            path.startswith('"') and path.endswith('"')
        ):
            path = path[1:-1]

        if (token.startswith("'") and token.endswith("'")) or (
            token.startswith('"') and token.endswith('"')
        ):
            token = token[1:-1]

        # Alias
        if path == "id":
            path = "object_id"

        try:
            if "/" in path:
                # It's an actual item path
                if ":*" in path:
                    # Handle array item wildcard
                    # TODO only supports a single array wildcard for now
                    loc = path.index(":*")
                    frags = path[:loc], path[loc + 2 :]
                    array: HkbArray = self.record.get_path_value(frags[0])

                    for i in range(len(array)):
                        item_path = f"{frags[0]}:{i}{frags[1]}"
                        if self._match(item_path, token):
                            # Return True if any of the items match
                            return True

                    return False
                else:
                    # Still need to match against a string!
                    actual = str(self.record.get_path_value(path, resolve=True))
            else:
                actual = self.record.get_field(path)
        except (AttributeError, KeyError, ValueError) as e:
            # Will retrieve stuff like object_id, type_name, etc
            actual = getattr(self.record, path, None)
            if actual is None:
                return False

        if isinstance(actual, XmlValueHandler):
            actual = actual.get_value()

        try:
            return self._is_matching(actual, token)
        except:
            return False


def query_objects(
    candidates: Iterable["HkbRecord"],
    query_str: str,
    object_filter: Callable[["HkbRecord"], bool] = None,
) -> Generator["HkbRecord", None, None]:
    try:
        subset = filter(object_filter, candidates)

        if not query_str or query_str == "*":
            yield from subset
            return

        tree = parser.parse(query_str)
        for obj in subset:
            if QueryTransformer(obj).transform(tree):
                yield obj
    except LarkError as e:
        raise ValueError(f"Query failed for '{query_str}'") from e
