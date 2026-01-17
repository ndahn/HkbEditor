import sys
from os import path
import yaml
import inspect
from dataclasses import dataclass, field, asdict


@dataclass
class Config:
    recent_files: list[str] = field(default_factory=list)

    hklib_exe: str = None
    witchy_exe: str = None

    invert_zoom: bool = False
    single_branch_mode: bool = True
    save_backups: bool = True
    session_backup: bool = True
    undo_history: int = 100

    def add_recent_file(self, file_path: str) -> None:
        file_path = path.normpath(path.abspath(file_path))
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)

        self.recent_files.insert(0, file_path)
        self.recent_files = self.recent_files[:10]

    def remove_recent_file(self, file_path: str) -> None:
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)

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
        
        sig = inspect.signature(Config.__init__)
        kw = {}
        
        # Match the args from the config to the current implementation in case it changed
        for key, val in cfg.items():
            if key in sig.parameters:
                kw[key] = val

        _config = Config(**kw)
    else:
        print(f"Creating new config in {config_path}")
        _config = Config()
        _config.save(config_path)

    return _config
