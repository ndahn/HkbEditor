import re

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray
from hkb_editor.hkb.behavior import HavokBehavior


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
            print(pattern, uri)
            if re.fullmatch(pattern, uri):
                return alias

        return None


class AliasManager:
    def __init__(self):
        self.aliases: dict[str, AliasMap] = {}

    def get_attribute_alias(self, record: HkbRecord, path: str) -> str:
        for am in self.aliases.keys():
            alias = am.match(record, path)
            if alias is not None:
                return alias

        return None

    def load_alias_file(self, file_path: str):
        # TODO
        pass

    def load_bone_names(self, file_path: str):
        # TODO might have to abolish the global type registry for this
        skeleton_beh = HavokBehavior(file_path)
        skeleton_type_id = skeleton_beh.type_registry.find_type_by_name("hkaSkeleton")
        skeletons = skeleton_beh.find_objects_by_type(skeleton_type_id)

        if not skeletons:
            raise ValueError(f"Could not find any objects of type {skeleton_type_id} (hkaSkeleton) in {file_path}")

        if len(skeletons) > 1:
            raise ValueError(f"{file_path} contained multiple objects of type {skeleton_type_id} (hkaSkeleton)")

        bone_array: HkbArray = skeletons[0].bones

        boneweights_type_id = self.beh.type_registry.find_type_by_name(
            "hkbBoneWeightArray"
        )
        basepath = "boneWeights"
        aliases = AliasMap()

        for idx, bone in enumerate(bone_array):
            aliases.add(bone.name, f"{basepath}:{idx}", boneweights_type_id, None)

        # Insert left so that these aliases take priority
        self.aliases.insert(0, aliases)
