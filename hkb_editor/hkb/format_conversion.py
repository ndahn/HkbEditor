from lxml import etree


def hk2018_to_2014(er_xml: str) -> str:
    root = etree.fromstring(er_xml.encode())

    out = etree.Element("hktagfile", version="2",
                        sdkversion="hk_2014.1.0-r1", maxpredicate="21", predicates="20")

    type_map: dict[str, str] = {
        t.get("id"): t.find("name").get("value", "")
        for t in root.findall("type")
        if t.find("name") is not None
    }

    # Emit <class> stubs for record types (format 7)
    for t in root.findall("type"):
        fmt = t.find("format")
        if fmt is None or fmt.get("value") != "7":
            continue
        name_el = t.find("name")
        if name_el is None:
            continue
        cls = etree.SubElement(out, "class", name=name_el.get("value", ""), version="0")
        for f in t.findall("fields/field"):
            etree.SubElement(cls, "member", name=f.get("name", ""), type="int")

    def convert_value(parent: etree._Element, name: str | None, v: etree._Element) -> None:
        """Append the DS3 element for ER value node `v` onto `parent`."""
        tag = v.tag
        attrib = {"name": name} if name else {}

        if tag == "integer":
            etree.SubElement(parent, "int", **attrib).text = v.get("value", "0")
        elif tag == "string":
            etree.SubElement(parent, "string", **attrib).text = v.get("value", "")
        elif tag == "bool":
            etree.SubElement(parent, "byte", **attrib).text = (
                "1" if v.get("value", "false").lower() == "true" else "0"
            )
        elif tag == "real":
            etree.SubElement(parent, "real", **attrib).text = v.get("value", "0")
        elif tag == "pointer":
            ref_id = v.get("id", "")
            if ref_id and ref_id != "object0":
                etree.SubElement(parent, "ref", **attrib).text = (
                    "#" + ref_id.removeprefix("object")
                )
        elif tag == "array":
            arr = etree.SubElement(parent, "array", size=v.get("count", "0"), **attrib)
            for item in v:
                convert_value(arr, None, item)
        elif tag == "record":
            struct = etree.SubElement(parent, "struct", **attrib)
            for field in v.findall("field"):
                children = list(field)
                if children:
                    convert_value(struct, field.get("name", ""), children[0])

    for obj in root.findall("object"):
        record = obj.find("record")
        if record is None:
            continue
        obj_id = "#" + obj.get("id", "").removeprefix("object")
        type_name = type_map.get(obj.get("typeid", ""), obj.get("typeid", ""))
        out_obj = etree.SubElement(out, "object", id=obj_id, type=type_name)
        for field in record.findall("field"):
            children = list(field)
            if children:
                convert_value(out_obj, field.get("name", ""), children[0])

    return etree.tostring(out, encoding="unicode", pretty_print=True)


def hk2014_to_2018(ds3_xml: str) -> str:
    root = etree.fromstring(ds3_xml.encode())

    out = etree.Element("hktagfile", version="3")

    type_counter = [1]

    def next_tid() -> str:
        tid = f"type{type_counter[0]}"
        type_counter[0] += 1
        return tid

    class_to_typeid: dict[str, str] = {}

    def get_or_make_typeid(type_name: str) -> str:
        if type_name not in class_to_typeid:
            tid = next_tid()
            class_to_typeid[type_name] = tid
            t_el = etree.SubElement(out, "type", id=tid)
            etree.SubElement(t_el, "name", value=type_name)
            etree.SubElement(t_el, "format", value="7")
            etree.SubElement(t_el, "fields", count="0")
        return class_to_typeid[type_name]

    for cls in root.findall("class"):
        cname = cls.get("name", "")
        tid = next_tid()
        class_to_typeid[cname] = tid
        t_el = etree.SubElement(out, "type", id=tid)
        etree.SubElement(t_el, "name", value=cname)
        etree.SubElement(t_el, "format", value="7")
        version = cls.get("version", "0")
        if version != "0":
            etree.SubElement(t_el, "version", value=version)
        members = cls.findall("member")
        fields_el = etree.SubElement(t_el, "fields", count=str(len(members)))
        for m in members:
            etree.SubElement(fields_el, "field", name=m.get("name", ""), typeid="", flags="36")

    def convert_child(parent: etree._Element, child: etree._Element) -> None:
        """Append an ER <field> for DS3 element `child` onto `parent`."""
        tag = child.tag
        name = child.get("name", "")
        # Named fields get a <field> wrapper; unnamed items (inside arrays) write directly.
        field = etree.SubElement(parent, "field", name=name) if name else parent

        if tag == "int":
            etree.SubElement(field, "integer", value=child.text or "0")
        elif tag == "byte":
            etree.SubElement(field, "bool",
                             value="true" if child.text == "1" else "false")
        elif tag == "string":
            etree.SubElement(field, "string", value=child.text or "")
        elif tag == "real":
            etree.SubElement(field, "real", value=child.text or "0")
        elif tag == "ref":
            ref_text = (child.text or "").strip()
            obj_id = "object" + ref_text.lstrip("#") if ref_text else "object0"
            etree.SubElement(field, "pointer", id=obj_id)
        elif tag == "array":
            arr = etree.SubElement(field, "array",
                                   count=child.get("size", "0"),
                                   elementtypeid="type43")
            for item in child:
                convert_child(arr, item)
        elif tag == "struct":
            record = etree.SubElement(field, "record")
            for item in child:
                convert_child(record, item)

    for obj in root.findall("object"):
        raw_id = obj.get("id", "").lstrip("#")
        type_name = obj.get("type", "")
        typeid = get_or_make_typeid(type_name)
        out_obj = etree.SubElement(out, "object", id=f"object{raw_id}", typeid=typeid)
        record = etree.SubElement(out_obj, "record")
        for child in obj:
            convert_child(record, child)

    return etree.tostring(out, encoding="unicode", pretty_print=True)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ER_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<hktagfile version="3">
<object id="object819" typeid="type199">
  <record>
    <field name="userData"><integer value="19464200" /></field>
    <field name="name"><string value="Ridden_Enemy_Fall_Loop_CMSG" /></field>
    <field name="generators">
      <array count="1" elementtypeid="type43">
        <pointer id="object1074" />
      </array>
    </field>
    <field name="animId"><integer value="7000" /></field>
    <field name="enableScript"><bool value="true" /></field>
    <field name="enableTae"><bool value="true" /></field>
    <field name="role">
      <record>
        <field name="role"><integer value="0" /></field>
        <field name="flags"><integer value="0" /></field>
      </record>
    </field>
  </record>
</object>
</hktagfile>"""

    DS3_SAMPLE = """<?xml version="1.0" encoding="ascii"?>
<hktagfile version="2" sdkversion="hk_2014.1.0-r1" maxpredicate="21" predicates="20">
<object id="#6757" type="hkbVariableBindingSet">
    <array name="bindings" size="1">
        <struct>
            <string name="memberPath">selectedGeneratorIndex</string>
            <int name="variableIndex">128</int>
            <int name="bitIndex">-1</int>
        </struct>
    </array>
    <int name="indexOfBindingToEnable">-1</int>
</object>
</hktagfile>"""

    print("=== ER → DS3 ===")
    ds3 = hk2018_to_2014(ER_SAMPLE)
    print(ds3)

    print("=== DS3 → ER ===")
    er = hk2014_to_2018(DS3_SAMPLE)
    print(er)

    print("=== ER → DS3 → ER roundtrip ===")
    print(hk2014_to_2018(hk2018_to_2014(ER_SAMPLE)))