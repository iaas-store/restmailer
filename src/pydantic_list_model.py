from typing import Any, MutableSequence, Iterable, Callable, Self, overload

from pydantic import RootModel


class ListModel[T](RootModel[list[T]], MutableSequence[T]):
    def __init__(self, *args, **data):
        if len(args) == 0 and len(data) == 0:
            super().__init__([])
            return

        super().__init__(*args, **data)

    def __iter__(self) -> Iterable[T]:
        yield from self.root

    def __getitem__(self, item: int | slice) -> T | list[T]:
        if isinstance(item, slice):
            return self.__class__(self.root[item])
        return self.root[item]

    def __len__(self) -> int:
        return len(self.root)

    def __setitem__(self, key: int | slice, value: T | Iterable[T]) -> None:
        self.root[key] = value

    def __delitem__(self, key: int | slice) -> None:
        del self.root[key]

    def __contains__(self, item: T) -> bool:
        return item in self.root

    def insert(self, index: int, value: T) -> None:
        self.root.insert(index, value)

    def append(self, value: T) -> None:
        self.root.append(value)

    def extend(self, values: Iterable[T]) -> None:
        self.root.extend(values)

    def pop(self, index: int = -1) -> T:
        return self.root.pop(index)

    def remove(self, value: T) -> None:
        self.root.remove(value)

    def clear(self) -> None:
        self.root.clear()

    def index(self, value: T, start: int = 0, end: int | None = None) -> int:
        return self.root.index(value, start, end or len(self.root))

    def count(self, value: T) -> int:
        return self.root.count(value)

    def sort(self, *, key: Callable[[T], Any] | None = None, reverse: bool = False) -> None:
        self.root.sort(key=key, reverse=reverse)

    def reverse(self) -> None:
        self.root.reverse()

    def __add__(self, other: list[T]) -> Self:
        return self.__class__(self.root + other)

    def __iadd__(self, other: Iterable[T]) -> Self:
        self.root += list(other)
        return self

    def __mul__(self, n: int) -> Self:
        return self.__class__(self.root * n)

    def __rmul__(self, n: int) -> Self:
        return self * n

    def __str__(self) -> str:
        return str(self.root)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}[{T}]({self.root!r})'
