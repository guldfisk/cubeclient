from __future__ import annotations

import typing as t

from abc import ABC, abstractmethod
import datetime

from magiccube.collections.cube import Cube

R = t.TypeVar('R', bound = 'RemoteModel')


class ApiClient(ABC):

    @abstractmethod
    def release(self, release_id: int) -> CubeRelease:
        pass

    @abstractmethod
    def versioned_cubes(self, offset: int = 0, limit: int = 10) -> PaginatedResponse[VersionedCube]:
        pass


# class LazyField(object):
#
#

class PaginatedResponse(t.Sequence[R]):

    def __init__(
        self,
        endpoint: t.Callable[[int, int], t.Any],
        serializer: t.Callable[[t.Any], R],
        offset: int = 0,
        limit: int = 50,
    ):
        self._endpoint = endpoint
        self._serializer = serializer
        self._limit = limit

        response = endpoint(offset, limit)

        self._count = response['count']
        self._items: t.List[t.Optional[R]] = [None for _ in range(self._count)]
        items = list(map(serializer, response['results']))
        self._items[offset:offset + len(items)] = items

    def _fetch_page(self, index: int) -> None:
        for offset_index, item in enumerate(
            map(
                self._serializer,
                self._endpoint(index, self._limit)['results'],
            )
        ):
            try:
                if self._items[index + offset_index] is None:
                    self._items[index + offset_index] = item
            except IndexError:
                break

    def __getitem__(self, index):
        if self._items[index] is None:
            self._fetch_page(index)
        return self._items[index]

    def __iter__(self) -> t.Iterator[R]:
        for index, item in enumerate(self._items):
            if item is None:
                self._fetch_page(index)
                yield self._items[index]
            else:
                yield item

    def __contains__(self, item) -> bool:
        return item in self.__iter__()

    def __len__(self):
        return self._count

    def _repr_iter(self) -> t.Iterator[str]:
        in_none = False
        for item in self._items:
            if item is None:
                if in_none:
                    continue
                in_none = True
                yield '...'
            else:
                in_none = False
                yield str(item)

    def __repr__(self):
        return '{}({}, [{}])'.format(
            self.__class__.__name__,
            self._count,
            ', '.join(self._repr_iter())
        )


class RemoteModel(ABC):

    def __init__(self, model_id: t.Union[str, int], client: ApiClient):
        self._id = model_id
        self._api_client = client

    @property
    def id(self) -> t.Union[str, int]:
        return self._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, self.__class__)
            and self._id == other._id
        )

    def __repr__(self):
        return '{}({})'.format(
            self.__class__.__name__,
            self._id,
        )


class VersionedCube(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        name: str,
        created_at: datetime.datetime,
        description: str,
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._name = name
        self._created_at = created_at
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def description(self) -> str:
        return self._description


class CubeReleaseMeta(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        created_at: datetime.datetime,
        name: str,
        intended_size: int,
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._created_at = created_at
        self._name = name
        self._intended_size = intended_size

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def name(self) -> str:
        return self._name

    @property
    def intended_size(self) -> int:
        return self._intended_size


class CubeRelease(CubeReleaseMeta):

    def __init__(
        self,
        model_id: t.Union[str, int],
        created_at: datetime.datetime,
        name: str,
        intended_size: int,
        cube: Cube,
        client: ApiClient,
    ):
        super().__init__(model_id, created_at, name, intended_size, client)
        self._cube = cube

    @property
    def cube(self) -> Cube:
        return self._cube
