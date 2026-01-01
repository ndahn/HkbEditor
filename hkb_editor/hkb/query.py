from typing import Iterable, Generator, Callable, TYPE_CHECKING
from abc import ABC, abstractmethod
import re
from lark import Lark, Transformer, Token
from lxml import etree
from fnmatch import fnmatch
from rapidfuzz import fuzz

if TYPE_CHECKING:
    from hkb_editor.hkb import HkbRecord


lucene_grammar = r"""
    ?start: or_expr

    ?or_expr: and_expr (KW_OR and_expr)*        -> or_
    ?and_expr: not_expr (KW_AND not_expr)* 
             | not_expr not_expr+               -> and_
    ?not_expr: KW_NOT not_expr                  -> not_
             | atom

    ?atom: field
         | bare_value
         | "(" or_expr ")"

    field: PATH_OR_STR "=" VALUE_TOKEN          -> field
    bare_value: VALUE_TOKEN                     -> value

    ESCAPED_STRING: SINGLE_QUOTED_STRING | DOUBLE_QUOTED_STRING
    SINGLE_QUOTED_STRING: "'" ( /[^'\\]/ | /\\./ )* "'"
    DOUBLE_QUOTED_STRING: "\"" ( /[^"\\]/ | /\\./ )* "\""
    PATH_OR_STR: PATH | ESCAPED_STRING

    KW_AND: /(?i:AND)\b/
    KW_OR:  /(?i:OR)\b/
    KW_NOT: /(?i:NOT)\b/

    VALUE_TOKEN: RANGE | FUZZY | ESCAPED_STRING | NONKEYWORD
    PATH      : /[A-Za-z_][A-Za-z0-9_.:*\/]*/
    RANGE     : /\[[^\[\]]+\.\.[^\[\]]+\]/
    FUZZY     : /~[^\s()]+/
    NONKEYWORD: /(?![Aa][Nn][Dd]\b|[Oo][Rr]\b|[Nn][Oo][Tt]\b)[^\s()]+/

    %import common.WS
    %ignore WS
"""


lucene_url = "https://lucene.apache.org/core/2_9_4/queryparsersyntax.html"


lucene_help_text = """\
Supports Lucene-style search queries (<field>=<value>). 

- Fields are used verbatim, with the only excception that array indices may be replaced by a * wildcard.
- Values may be specified using fields, wildcards, fuzzy searches, ranges.
- Terms may be combined using grouping, OR, NOT. 
- Terms separated by a space are assumed to be AND.

You may run queries over the following fields:
- id
- object_id (same as id)
- type_id
- type_name
- name
- parent
- any attribute path

Examples:
- id=*588 OR type_name:hkbStateMachine
- bindings:0/memberPath=selectedGeneratorIndex
- NOT animId=[100000..200000]
- name=~AddDamageFire
"""


class _Condition(ABC):
    @abstractmethod
    def evaluate(self, obj: "HkbRecord") -> bool: ...


class _FieldCondition(_Condition):
    def __init__(self, field_path: str, value: str):
        self.field_path = field_path.strip("\"'")
        self.value = value.strip("\"'")

    def _get_field_values(self, obj: "HkbRecord") -> list[str]:
        if self.field_path in ("id", "objectid", "object_id"):
            return [obj.object_id]

        if self.field_path in ("type", "typename", "type_name", "typeid", "type_id"):
            return [obj.type_id, obj.type_name]

        return _get_field_value(obj.element, self.field_path)

    def evaluate(self, obj: "HkbRecord") -> bool:
        actual_values = self._get_field_values(obj)
        return any(_match_value(val, self.value) for val in actual_values)

    def __repr__(self):
        return f"field({self.field_path}={self.value})"


class _ValueCondition(_Condition):
    def __init__(self, value: str):
        self.value = value.strip("\"'")

    def _candidates(self, obj: "HkbRecord") -> Generator[str, None, None]:
        if "name" in obj.fields:
            yield obj["name"].get_value()

        yield obj.type_name
        yield obj.object_id
        yield obj.type_id

    def evaluate(self, obj: "HkbRecord") -> bool:
        return any(_match_value(val, self.value) for val in self._candidates(obj))

    def __repr__(self):
        return f"value({self.value})"


class _OrCondition(_Condition):
    def __init__(self, conditions: list[_Condition]):
        self.conditions = conditions

    def evaluate(self, obj: "HkbRecord") -> bool:
        return any(c.evaluate(obj) for c in self.conditions)

    def __repr__(self):
        return f"OR({', '.join(map(str, self.conditions))})"


class _AndCondition(_Condition):
    def __init__(self, conditions: list[_Condition]):
        self.conditions = conditions

    def evaluate(self, obj: "HkbRecord") -> bool:
        return all(c.evaluate(obj) for c in self.conditions)

    def __repr__(self):
        return f"AND({', '.join(map(str, self.conditions))})"


class _NotCondition(_Condition):
    def __init__(self, condition: _Condition):
        self.condition = condition

    def evaluate(self, obj: "HkbRecord") -> bool:
        # Special-case: NOT on a field requires the field to exist
        if isinstance(self.condition, _FieldCondition):
            vals = self.condition._get_field_values(obj)
            if not vals:
                # No match if the field isn't present
                return False

            return not any(_match_value(v, self.condition.value) for v in vals)

        return not self.condition.evaluate(obj)

    def __repr__(self):
        return f"NOT({self.condition})"


class _QueryTransformer(Transformer):
    def _conds(self, args):
        # drop KW_AND / KW_OR / KW_NOT tokens
        return [a for a in args if not isinstance(a, Token)]

    def field(self, args):
        path, value = str(args[0]), str(args[1]).strip("\"'")
        return _FieldCondition(path, value)

    def value(self, args):
        value = str(args[0]).strip("\"'")
        return _ValueCondition(value)

    def or_(self, args):
        return _OrCondition(self._conds(args))

    def and_(self, args):
        return _AndCondition(self._conds(args))

    def not_(self, args):
        return _NotCondition(self._conds(args)[0])


def _parse_query(query_string: str) -> _Condition:
    parser = Lark(lucene_grammar, parser="earley")
    tree = parser.parse(query_string)
    return _QueryTransformer().transform(tree)


def _get_field_value(obj_elem: etree._Element, field_path: str) -> list[str]:
    path_parts = field_path.split("/")
    xpath_parts = []

    for part in path_parts:
        if ":" in part:
            field_name, index = part.split(":", 1)
            if index == "*":
                xpath_parts.append(f"field[@name='{field_name}']/array/*")
            else:
                try:
                    idx = int(index) + 1  # XPath is 1-indexed
                    xpath_parts.append(f"field[@name='{field_name}']/array/*[{idx}]")
                except ValueError:
                    return []
        else:
            xpath_parts.append(f"field[@name='{part}']/*")

    xpath = ".//" + "//".join(xpath_parts)
    # print("xpath:", xpath)
    elements = obj_elem.xpath(xpath)
    values: list[str] = []

    def get_value(elem: etree._Element):
        if elem is None:
            return ""
        
        val = elem.get("value")
        if val is not None:
            return val

        val = elem.get("dec")
        if val is not None:
            return val

        val = elem.get("id")
        if val is not None:
            return val

        return elem.text or ""

    for elem in elements:
        if elem.tag == "array":
            for child in elem.getchildren():
                values.append(get_value(child))
        else:
            values.append(get_value(elem))

    return values


def _match_value(actual_value: str, search_value: str) -> bool:
    if search_value == "*":
        return actual_value is not None

    if search_value.startswith("~"):
        fuzzy_term = search_value[1:]
        return fuzz.partial_ratio(actual_value.lower(), fuzzy_term.lower()) > 80

    elif "*" in search_value:
        return fnmatch(actual_value.lower(), search_value.lower())

    elif (
        search_value.startswith("[")
        and search_value.endswith("]")
        and ".." in search_value
    ):
        try:
            m = re.match(r"\[(\S+)\.\.(\S+)\]", search_value)
            if m:
                start, end = m.groups()
                val = float(actual_value)
                return float(start) <= val <= float(end)
        except ValueError:
            return False

        return False

    else:
        return actual_value.lower() == search_value.lower()


def query_objects(
    candidates: Iterable["HkbRecord"],
    query: str,
    object_filter: Callable[["HkbRecord"], bool] = None,
) -> Generator["HkbRecord", None, None]:
    if not query:
        yield from filter(object_filter, candidates)
        return

    condition = None

    try:
        condition = _parse_query(query)
        for obj in candidates:
            if object_filter and not object_filter(obj):
                continue

            if condition.evaluate(obj):
                yield obj

    except Exception as e:
        s = str(condition) if condition else query
        raise ValueError(f"Query {s} failed") from e
