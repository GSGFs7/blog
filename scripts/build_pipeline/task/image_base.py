from dataclasses import dataclass
from typing import Iterable

from ..type import Runner, Task


@dataclass(frozen=True, slots=True)
class Config:
    name: str
    dockerfile: str
    target: str | None

    # TODO: message
    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("")
        if not isinstance(self.dockerfile, str) or not self.dockerfile:
            raise ValueError("")
        if self.target is not None and (
            not isinstance(self.target, str) or not self.target
        ):
            raise ValueError("")


class BaseImageTask(Task):
    def __init__(self, runner: Runner, images: Iterable[tuple[str, str, str | None]]):
        self.runner = runner
        self.images: list[Config] = []
        for name, dockerfile, target in images:
            config = Config(name=name, dockerfile=dockerfile, target=target)
            self.images.append(config)
