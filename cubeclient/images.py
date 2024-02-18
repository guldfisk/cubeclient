import logging
import typing as t
from concurrent.futures import Executor
from concurrent.futures.thread import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import urljoin

import requests
from mtgimg import pipeline
from mtgimg.base import BaseImageLoader
from mtgimg.interface import Imageable, ImageFetchException, ImageRequest
from mtgorp.models.interfaces import Printing
from PIL import Image
from promise import Promise
from yeetlong.taskawaiter import EventWithValue, TaskAwaiter


class ClientFetcher(object):
    _fetching: TaskAwaiter[ImageRequest, Image.Image] = TaskAwaiter()

    @classmethod
    def _get_identifier(cls, image_request: ImageRequest) -> str:
        if image_request.pictured_name is not None:
            return image_request.pictured_name
        return str(image_request.pictured.id)

    @classmethod
    def _fetch_image(
        cls,
        url: str,
        image_request: ImageRequest,
        event: EventWithValue[ImageRequest, Image.Image],
    ) -> Image.Image:
        with event as event:
            response = requests.get(
                urljoin(url, "/api/images/") + cls._get_identifier(image_request) + "/",
                params={
                    "size_slug": image_request.size_slug.name.lower(),
                    "cropped": image_request.crop,
                    "back": image_request.back,
                    "type": image_request.pictured_type.__name__,
                },
                stream=True,
            )
            response.raise_for_status()
            image = Image.open(response.raw)
            event.set_value(image)
            return image

    @classmethod
    def get_image(cls, url: str, image_request: ImageRequest) -> Image.Image:
        event, in_progress = cls._fetching.get_condition(image_request)

        if in_progress:
            event.wait()
            return event.value

        return cls._fetch_image(url, image_request, event)


class ImageClient(BaseImageLoader):
    def __init__(
        self,
        url: str,
        *,
        executor: t.Union[Executor, int] = None,
        imageables_executor: t.Union[Executor, int] = None,
        image_cache_size: t.Optional[int] = 64,
        use_scryfall_when_available: bool = True,
        allow_save_to_disk: bool = False,
        allow_load_from_disk: bool = False,
        allow_local_fallback: bool = False,
    ):
        if imageables_executor is not None and not allow_local_fallback:
            logging.warning("separate executor only required when allow_local_fallback is True")

        super().__init__(image_cache_size=image_cache_size)

        self._url = "http://" + url if not url.startswith("http") else url
        self._executor = (
            executor
            if executor is isinstance(executor, Executor)
            else ThreadPoolExecutor(max_workers=executor if isinstance(executor, int) else 8)
        )

        self._imageables_executor = (
            (
                imageables_executor
                if executor is isinstance(imageables_executor, Executor)
                else ThreadPoolExecutor(max_workers=executor if isinstance(imageables_executor, int) else 4)
            )
            if allow_local_fallback
            else None
        )

        self._use_scryfall_when_available = use_scryfall_when_available
        self._allow_save_to_disk = allow_save_to_disk
        self._allow_load_from_disk = allow_load_from_disk
        self._allow_local_fallback = allow_local_fallback

        if image_cache_size is not None:
            self._open_image = lru_cache(image_cache_size)(self._open_image)

    def _open_image(self, image_request: ImageRequest) -> Image.Image:
        if image_request.allow_disk_cached:
            try:
                return self.load_image_from_disk(image_request.path)
            except ImageFetchException:
                image_request = image_request.spawn(allow_disk_cached=False)

        if self._use_scryfall_when_available and issubclass(image_request.pictured_type, Printing):
            return pipeline.get_pipeline(image_request).get_image(image_request, self)

        try:
            return ClientFetcher.get_image(self._url, image_request)
        except Exception as e:
            if self._allow_local_fallback and isinstance(image_request.pictured, Imageable):
                return pipeline.get_pipeline(image_request).get_image(image_request, self)
            else:
                raise ImageFetchException(e)

    def _get_image(self, image_request: ImageRequest = None) -> Promise[Image.Image]:
        if not self._allow_save_to_disk or not self._allow_load_from_disk:
            image_request = image_request.spawn(
                save=False if not self._allow_save_to_disk else image_request.save,
                allow_disk_cached=False if not self._allow_load_from_disk else image_request.allow_disk_cached,
            )
        return Promise.resolve(
            (
                self._imageables_executor
                if self._allow_local_fallback and isinstance(image_request.pictured, Imageable)
                else self._executor
            ).submit(self._open_image, image_request)
        )

    def stop(self) -> None:
        if self._imageables_executor is not None:
            self._imageables_executor.shutdown(wait=False)
        self._executor.shutdown(wait=False)
