import logging
from lxml import etree as ET


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
    # TODO we should handle comments properly at some point so they are kept,
    # but for now this is easier
    parser = ET.XMLParser(remove_comments=True)
    parser.set_element_class_lookup(lookup)
    
    return parser
