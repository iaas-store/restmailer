from typing import Iterable, Self, MutableMapping, Iterator

from pydantic import RootModel


class DictModel[KeyT, ValueT](RootModel[dict[KeyT, ValueT]], MutableMapping[KeyT, ValueT]):
    def __init__(self, *args, **data):
        if len(args) == 0 and len(data) == 0:
            super().__init__({})
            return

        super().__init__(*args, **data)

    def __iter__(self) -> Iterator[KeyT]:
        return iter(self.root)

    def __getitem__(self, key: KeyT | Iterable[KeyT]) -> ValueT | dict[KeyT, ValueT]:
        if isinstance(key, Iterable) and not isinstance(key, str):
            return self.__class__({k: self.root[k] for k in key})
        return self.root[key]

    def __len__(self) -> int:
        return len(self.root)

    def __setitem__(self, key: KeyT, value: ValueT) -> None:
        self.root[key] = value

    def __delitem__(self, key: KeyT) -> None:
        del self.root[key]

    def __contains__(self, key: object) -> bool:
        return key in self.root

    def get(self, key: KeyT, default: ValueT | None = None) -> ValueT | None:
        return self.root.get(key, default)

    def keys(self) -> Iterable[KeyT]:
        return self.root.keys()

    def values(self) -> Iterable[ValueT]:
        return self.root.values()

    def items(self) -> Iterable[tuple[KeyT, ValueT]]:
        return self.root.items()

    def pop(self, key: KeyT, default: ValueT | None = None) -> ValueT:
        return self.root.pop(key, default)

    def popitem(self) -> tuple[KeyT, ValueT]:
        return self.root.popitem()

    def clear(self) -> None:
        self.root.clear()

    def update(self, other: dict[KeyT, ValueT] | Iterable[tuple[KeyT, ValueT]] = (), /, **kwargs: ValueT) -> None:
        self.root.update(other, **kwargs)

    def setdefault(self, key: KeyT, default: ValueT | None = None) -> ValueT:
        return self.root.setdefault(key, default)

    def __or__(self, other: dict[KeyT, ValueT]) -> Self:
        return self.__class__(self.root | other)

    def __ior__(self, other: dict[KeyT, ValueT] | Iterable[tuple[KeyT, ValueT]]) -> Self:
        self.root |= other
        return self

    def __str__(self) -> str:
        return str(self.root)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}[{KeyT}, {ValueT}]({self.root!r})'
