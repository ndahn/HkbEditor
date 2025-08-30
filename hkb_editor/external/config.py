import sys
from os import path
import yaml
from dataclasses import dataclass, field, asdict


@dataclass
class Config:
    recent_files: list[str] = field(default_factory=list)

    hklib_exe: str = None
    witchy_exe: str = None

    invert_zoom: bool = False
    single_branch_mode: bool = True
    save_backups: bool = True
    reload_on_save: bool = False

    def add_recent_file(self, behavior_path: str) -> None:
        behavior_path = path.normpath(path.abspath(behavior_path))
        if behavior_path in self.recent_files:
            self.recent_files.remove(behavior_path)

        self.recent_files.insert(0, behavior_path)
        self.recent_files = self.recent_files[:10]

    def save(self, config_path: str = None) -> None:
        if not config_path:
            config_path = get_default_config_path()

        with open(config_path, "w") as f:
            yaml.safe_dump(asdict(self), f)


_config: Config = None


def get_default_config_path() -> str:
    return path.join(path.dirname(sys.argv[0]), "config.yaml")


def get_config() -> Config:
    return _config


def load_config(config_path: str = None) -> Config:
    global _config
    
    if not config_path:
        config_path = get_default_config_path()

    if path.isfile(config_path):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        
        _config = Config(**cfg)
    else:
        # TODO print warning
        _config = Config()
        _config.save(config_path)

    return _config
