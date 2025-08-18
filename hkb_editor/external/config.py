import sys
from os import path
import yaml
from dataclasses import dataclass, field, asdict
from collections import deque


@dataclass
class Config:
    recent_files: deque[str] = field(default_factory=lambda: deque(maxlen=5))

    hklib_exe: str = None
    witchy_exe: str = None

    save_backup: bool = True
    convert_on_save: bool = False
    pack_on_save: bool = False
    reload_on_save: bool = False


config: Config = None


def load_config(config_path: str = None):
    global config
    
    if not config_path:
        config_path = path.join(path.dirname(sys.argv[0]), "config.yaml")

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    config = Config(**cfg)


def save_config(config_path: str = None):
    if not config_path:
        config_path = path.join(path.dirname(sys.argv[0]), "config.yaml")

    with open(config_path, "w") as f:
        yaml.safe_dump(asdict(config), f)


load_config()
