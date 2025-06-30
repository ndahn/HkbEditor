from .tagfile import Tagfile
from .hkb_types import HkbArray


def load_boneweight_array(tagfile: Tagfile, skeleton_path: str) -> HkbArray:
    skeleton_beh = Tagfile(skeleton_path)
    skeleton_type_id = skeleton_beh.type_registry.find_first_type_by_name("hkaSkeleton")
    skeletons = list(skeleton_beh.find_objects_by_type(skeleton_type_id))

    if not skeletons:
        raise ValueError(f"Could not find any objects of type {skeleton_type_id} (hkaSkeleton) in {skeleton_path}")

    if len(skeletons) > 1:
        raise ValueError(f"{skeleton_path} contained multiple objects of type {skeleton_type_id} (hkaSkeleton)")

    return skeletons[0]["bones"]
