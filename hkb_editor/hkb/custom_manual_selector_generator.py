from .generator import Generator


class CustomManualSelectorGenerator(Generator):
    def __init__(
        self,
        name: str,
        anim_id: int,
        enable_script: bool = True,
        enable_tae: bool = True,
        *generators: Generator
    ):
        super().__init__(name)

        self.anim_id = anim_id
        self.enable_script = enable_script
        self.enable_tae = enable_tae
        self.generators = list(generators)

    

