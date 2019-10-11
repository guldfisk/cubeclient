from __future__ import annotations

import typing as t

from abc import ABC, abstractmethod
import datetime

from magiccube.collections.cube import Cube
from magiccube.collections.meta import MetaCube
from magiccube.update.cubeupdate import VerboseCubePatch


R = t.TypeVar('R', bound = 'RemoteModel')


class ApiClient(ABC):

    @abstractmethod
    def release(self, release: t.Union[CubeRelease, str, int]) -> CubeRelease:
        pass

    @abstractmethod
    def versioned_cubes(self, offset: int = 0, limit: int = 10) -> PaginatedResponse[VersionedCube]:
        pass

    @abstractmethod
    def versioned_cube(self, versioned_cube_id: t.Union[str, int]) -> VersionedCube:
        pass

    @abstractmethod
    def patch(self, patch_id: t.Union[str, int]) -> PatchModel:
        pass

    @abstractmethod
    def patches(
        self,
        versioned_cube: t.Union[VersionedCube, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> PaginatedResponse[PatchModel]:
        pass

    @abstractmethod
    def preview_patch(self, patch: t.Union[PatchModel, int, str]) -> MetaCube:
        pass

    @abstractmethod
    def verbose_patch(self, patch: t.Union[PatchModel, int, str]) -> VerboseCubePatch:
        pass

    # @abstractmethod
    # def patch_report(self, patch: t.Union[PatchModel, int, str]) -> UpdateReport:
    #     pass


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
        releases: t.List[CubeRelease],
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._name = name
        self._created_at = created_at
        self._description = description
        self._releases = releases

        self._patches: t.Optional[PaginatedResponse[PatchModel]] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def description(self) -> str:
        return self._description

    @property
    def releases(self) -> t.Sequence[CubeRelease]:
        return self._releases

    @property
    def patches(self) -> PaginatedResponse[PatchModel]:
        if self._patches is None:
            self._patches = self._api_client.patches(self)
        return self._patches


class CubeRelease(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        created_at: datetime.datetime,
        name: str,
        intended_size: int,
        cube: t.Optional[Cube],
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._created_at = created_at
        self._name = name
        self._intended_size = intended_size
        self._cube = cube

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def name(self) -> str:
        return self._name

    @property
    def intended_size(self) -> int:
        return self._intended_size

    @property
    def cube(self) -> Cube:
        if self._cube is None:
            self._cube = self._api_client.release(self).cube
        return self._cube


class PatchModel(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        created_at: datetime.datetime,
        name: str,
        description: str,
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._created_at = created_at
        self._name = name
        self._description = description

        self._preview: t.Optional[MetaCube] = None
        self._verbose: t.Optional[VerboseCubePatch] = None

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def preview(self) -> MetaCube:
        if self._preview is None:
            self._preview = self._api_client.preview_patch(self)
        return self._preview

    @property
    def verbose(self):
        if self._verbose is None:
            self._verbose = self._api_client.verbose_patch(self)
        return self._verbose