from typing import Iterable, Generator, Callable, TYPE_CHECKING
from abc import ABC, abstractmethod
from lark import Lark, Transformer, Token
from lxml import etree
from fnmatch import fnmatch
from rapidfuzz import fuzz
import re

if TYPE_CHECKING:
    from hkb_editor.hkb import Tagfile, HkbRecord


lucene_grammar = r"""
    ?start: or_expr

    ?or_expr: and_expr (KW_OR and_expr)*        -> or_
    ?and_expr: not_expr (KW_AND not_expr)*      -> and_
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

    // tokens
    KW_AND: /(?i:AND)/
    KW_OR:  /(?i:OR)/
    KW_NOT: /(?i:NOT)/

    VALUE_TOKEN: RANGE | FUZZY | WILDCARD | NONKEYWORD | ESCAPED_STRING
    PATH      : /[A-Za-z_][A-Za-z0-9_.:*\/]*/
    RANGE     : /\[[^\[\]]+ TO [^\[\]]+\]/
    FUZZY     : /~[^\s()]+/
    WILDCARD  : /[^\s()]+[*]/
    NONKEYWORD: /(?![Aa][Nn][Dd]\b|[Oo][Rr]\b|[Nn][Oo][Tt]\b)[^\s()]+/

    %import common.WS
    %ignore WS
"""



class Condition(ABC):
    @abstractmethod
    def evaluate(self, obj_elem: etree._Element) -> bool: ...


class FieldCondition(Condition):
    def __init__(self, field_path: str, value: str):
        self.field_path = field_path.strip("\"'")
        self.value = value.strip("\"'")

    def evaluate(self, obj_elem: etree._Element) -> bool:
        actual_values = get_field_value(obj_elem, self.field_path)
        return any(match_value(val, self.value) for val in actual_values)

    def __repr__(self):
        return f"FieldCondition({self.field_path}={self.value})"


class ValueCondition(Condition):
    def __init__(self, value: str):
        self.value = value.strip("\"'")

    def evaluate(self, obj_elem: etree._Element) -> bool:
        all_text = " ".join(obj_elem.itertext())
        return match_value(all_text, self.value)

    def __repr__(self):
        return f"ValueCondition({self.value})"


class OrCondition(Condition):
    def __init__(self, conditions: list[Condition]):
        self.conditions = conditions

    def evaluate(self, obj_elem: etree._Element) -> bool:
        return any(c.evaluate(obj_elem) for c in self.conditions)

    def __repr__(self):
        return f"OR({', '.join(map(str, self.conditions))})"


class AndCondition(Condition):
    def __init__(self, conditions: list[Condition]):
        self.conditions = conditions

    def evaluate(self, obj_elem: etree._Element) -> bool:
        return all(c.evaluate(obj_elem) for c in self.conditions)

    def __repr__(self):
        return f"AND({', '.join(map(str, self.conditions))})"


class NotCondition(Condition):
    def __init__(self, condition: Condition):
        self.condition = condition

    def evaluate(self, obj_elem: etree._Element) -> bool:
        return not self.condition.evaluate(obj_elem)

    def __repr__(self):
        return f"NOT({self.condition})"


class QueryTransformer(Transformer):
    def _conds(self, args):
        # drop KW_AND / KW_OR / KW_NOT tokens
        return [a for a in args if not isinstance(a, Token)]
    
    def field(self, args):
        path, value = str(args[0]), str(args[1]).strip("\"'")
        return FieldCondition(path, value)

    def value(self, args):
        value = str(args[0]).strip("\"'")
        return ValueCondition(value)

    def or_(self, args):
        return OrCondition(self._conds(args))

    def and_(self, args):
        return AndCondition(self._conds(args))

    def not_(self, args):
        return NotCondition(self._conds(args)[0])


def parse_query(query_string: str) -> Condition:
    parser = Lark(lucene_grammar, parser="earley")
    tree = parser.parse(query_string)
    return QueryTransformer().transform(tree)


def get_field_value(obj_elem: etree._Element, field_path: str) -> list[str]:
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
    #print("xpath:", xpath)
    elements = obj_elem.xpath(xpath)
    values: list[str] = []

    def get_value(elem: etree._Element):
        if elem.get("value") is not None:
            return elem.get("value")
        
        if elem.get("id") is not None:
            return elem.get("id")
        
        return elem

    for elem in elements:
        if elem.tag == "array":
            for child in elem.getchildren():
                values.append(get_value(child))
        else:
            values.append(get_value(elem))

    return values


def match_value(actual_value: str, search_value: str) -> bool:
    if search_value == "*":
        return actual_value is not None

    if search_value.startswith("~"):
        fuzzy_term = search_value[1:]
        return fuzz.partial_ratio(actual_value.lower(), fuzzy_term.lower()) > 80

    elif "*" in search_value:
        return fnmatch(actual_value.lower(), search_value.lower())

    elif search_value.startswith("[") and " TO " in search_value:
        try:
            m = re.match(r"\[(\S+)\s+TO\s+(\S+)\]", search_value)
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
    query: str,
    candidates: Iterable["HkbRecord"],
    object_filter: Callable[["HkbRecord"], bool] = None,
) -> Generator["HkbRecord", None, None]:
    try:
        condition = parse_query(query)
        for obj in candidates:
            if object_filter and not object_filter(obj):
                continue

            if condition.evaluate(obj.element):
                yield obj
        
    except Exception as e:
        raise ValueError(f"Query failed for '{query}'") from e




def search_xml_objects(
    xml_content: bytes | str, query_string: str
) -> list[etree._Element]:
    try:
        if isinstance(xml_content, str) and xml_content.strip().startswith("<?xml"):
            root = etree.fromstring(xml_content.encode("utf-8"))
        elif isinstance(xml_content, str):
            root = etree.fromstring(xml_content.encode("utf-8"))
        else:
            root = etree.fromstring(xml_content)

        condition = parse_query(query_string)
        return [obj for obj in root.xpath(".//object") if condition.evaluate(obj)]
    except Exception as e:
        print(f"Error searching XML: {e}")
        return []




# Example usage
if __name__ == "__main__":
    # Sample XML content
    xml_content = """<root>
        <object id="object2592" typeid="type316">
            <record>
                <field name="name">
                    <string value="DiveJump Selector"/>
                </field>
                <field name="selectedGeneratorIndex">
                    <integer value="0"/>
                </field>
                <field name="generators">
                    <array count="2" elementtypeid="type41">
                        <pointer id="object4066"/>
                        <pointer id="object4067"/>
                        <record>
                            <field name="name">
                                <string value="Array Generator"/>
                            </field>
                            <field name="selectedGeneratorIndex">
                                <integer value="3"/>
                            </field>
                        </record>
                    </array>
                </field>
                <field name="userData">
                    <integer value="0"/>
                </field>
            </record>
        </object>
        <object id="object1234" typeid="type100">
            <record>
                <field name="name">
                    <string value="Test Generator"/>
                </field>
                <field name="selectedGeneratorIndex">
                    <integer value="5"/>
                </field>
            </record>
        </object>
    </root>"""

    # Example queries
    queries = [
        'name="DiveJump Selector"',
        "selectedGeneratorIndex=0",
        "name=*Jump*",
        "selectedGeneratorIndex=[0 TO 3]",
        "generators=*",
        "generators=* AND name=*Selector*",
        "NOT name='Test Generator' OR selectedGeneratorIndex=5",
        'generators:*/name="Array Generator"',
        "NOT selectedGeneratorIndex=5",
    ]

    with open("/home/dfki.uni-bremen.de/ndahn/devel/workspaces/my_workspace/freetime/HkbEditor/test/c0000_player.xml") as f:
        xml_content = f.read()

    for query in queries:
        print(f"\nQuery: {query}")
        try:
            condition = parse_query(query)
            print(f"Condition: {condition}")
        except Exception as e:
            print(f"Parse error: {e}")
            continue

        results = search_xml_objects(xml_content, query)
        print(f"[{len(results)}] matching objects")