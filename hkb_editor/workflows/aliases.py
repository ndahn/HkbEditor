import re

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray
from hkb_editor.hkb.tagfile import Tagfile


class AliasMap:
    @classmethod
    def attribute_uri(
        self, path: str, type_id: str = None, object_id: str = None
    ) -> str:
        # object123#type123@my/aweseome/attribute
        return f"{object_id or ''}#{type_id or ''}@{path}"

    def __init__(self, *aliases: tuple[str | re.Pattern, str]):
        self.aliases: list[tuple[re.Pattern, str]] = list(aliases)

        for r, a in aliases:
            self.add(r, a)

    def add(
        self, alias: str, path: str, type_id: str = None, object_id: str = None
    ) -> None:
        if not type_id:
            type_id = ".*"

        if not object_id:
            object_id = ".*"

        pattern = self.attribute_uri(path, type_id, object_id)
        self.aliases.append((re.compile(pattern), alias))

    def match(self, record: HkbRecord, path: str) -> str:
        uri = self.attribute_uri(path, record.type_id, record.object_id)

        for pattern, alias in self.aliases:
            if re.fullmatch(pattern, uri):
                return alias

        return None


class AliasManager:
    def __init__(self):
        self.aliases: list[tuple[str, AliasMap]] = []

    def clear(self) -> None:
        self.aliases = []

    def get_attribute_alias(self, record: HkbRecord, path: str) -> str:
        for am in self.aliases:
            alias = am.match(record, path)
            if alias is not None:
                return alias

        return None

    def load_alias_file(self, file_path: str):
        # TODO
        pass
