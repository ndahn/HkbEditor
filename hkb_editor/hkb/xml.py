from typing import TYPE_CHECKING
import logging
from lxml import etree as ET

if TYPE_CHECKING:
    from .tagfile import Tagfile


class GuardedElement(ET.ElementBase):
    def _warn_or_clone(self, el):
        if el.getparent() is not None:
            attrs = " ".join(f"{k}={v}" for k,v in el.attrib.items())
            logging.getLogger().warning(f"Element is about to be moved, this might be a bug: <{el.tag} {attrs}>")

    def append(self, el):
        self._warn_or_clone(el)
        return ET.ElementBase.append(self, el)

    def insert(self, i, el):
        self._warn_or_clone(el)
        return ET.ElementBase.insert(self, i, el)

    def extend(self, it):
        fixed = [self._warn_or_clone(e) for e in it]
        return ET.ElementBase.extend(self, fixed)

    def addnext(self, el):
        self._warn_or_clone(el)
        return ET.ElementBase.addnext(self, el)

    def addprevious(self, el):
        self._warn_or_clone(el)
        return ET.ElementBase.addprevious(self, el)


def get_xml_parser() -> ET.XMLParser:
    lookup = ET.ElementDefaultClassLookup(element=GuardedElement)
    
    # lxml keeps comments, which affect subelement counts and iterations.
    parser = ET.XMLParser(remove_comments=True)
    parser.set_element_class_lookup(lookup)
    
    return parser


def xml_from_str(xml: str) -> ET.Element:
    parser = get_xml_parser()
    return ET.fromstring(xml, parser=parser)


def xml_from_file(path: str) -> ET.Element:
    parser = get_xml_parser()
    return ET.parse(path, parser=parser)


def xml_to_str(xml: ET.Element) -> str:
    return ET.tostring(xml, pretty_print=True, encoding="unicode")


def add_type_comments(root: ET.Element, tagfile: "Tagfile") -> None:
    for el in root.findall(".//object"):
        oid = el.get("id")
        type_name = tagfile.objects[oid].type_name
        el.insert(0, ET.Comment(type_name))
