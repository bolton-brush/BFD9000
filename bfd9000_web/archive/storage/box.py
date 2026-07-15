"""Storage backend implementation for Box"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, override

from archive.storage.storage import FileTimeInfo, StorageBackend
from box_sdk_gen import (
    BoxAPIError,
    CreateFolderParent,
    FileBaseTypeField,
    FolderBaseTypeField,
    ResponseByteStream,
    UploadFileAttributes,
    UploadFileAttributesParentField,
    UploadFileVersionAttributes,
)
from cachetools import LRUCache, cached
from cachetools.keys import hashkey

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from archive.storage.boxtypes import BoxAuthType
    from box_sdk_gen import BoxClient

logger = logging.getLogger(__name__)


@dataclass
class _ItemData:
    id: str
    name: str | None
    is_folder: bool


@dataclass
class _SessionEntry:
    client: BoxClient
    parent_id: str
    filename: str
    file_id: str | None


class BoxStorageBackend(StorageBackend[Path, int]):
    """Modern Box.com storage backend.

    Generics map:
      - FileHandle: `str` (A unique session token mapping to an active Box asset)
      - Error: `str` (Textual descriptive diagnostic messages)
    """

    CHUNKED_UPLOAD_THRESHOLD: int = 20 * 1024**2
    CHUNK_SIZE: int = 64 * 1024

    def __init__(self, box_auth: BoxAuthType, box_folder_id: str) -> None:
        """Create a Box storage backend with authentication and a base directory

        Args:
            box_auth: The authentication to use
            box_folder_id: The folder to store items within

        """
        # Local stateful registry to track session tracking maps
        self._session_registry: dict[int, _SessionEntry] = {}
        self._session_counter: int = 0

        # self._item_cache: dict[tuple[str, str], _ItemData] = {}
        self._box_auth: BoxAuthType = box_auth
        self._box_folder_id: str = box_folder_id

    @staticmethod
    @cached(
        cache=LRUCache(maxsize=1024),
        key=lambda _, parent_id, name, is_folder: hashkey(  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
            parent_id,  # pyright: ignore[reportUnknownArgumentType]
            name,  # pyright: ignore[reportUnknownArgumentType]
            is_folder,  # pyright: ignore[reportUnknownArgumentType]
        ),
    )
    def _get_item(
        client: BoxClient,
        parent_id: str,
        name: str,
        is_folder: bool,
    ) -> _ItemData | None:
        """Queries the Box API to find an item by its name and type configuration.

        Args:
            client: The Box client to use
            parent_id: The Box folder ID where the search executes.
            name: The target filename or subfolder name.
            is_folder: True if searching for a folder, False for a file.

        Returns:
            The found item if found, or None

        """
        items = client.folders.get_folder_items(parent_id)
        wanted_item_type = (
            FolderBaseTypeField.FOLDER if is_folder else FileBaseTypeField.FILE
        )
        found_item = next(
            (
                item
                for item in items.entries or []
                if item.name == name and item.type == wanted_item_type
            ),
            None,
        )
        if found_item:
            return _ItemData(
                id=found_item.id, name=found_item.name, is_folder=is_folder
            )
        return None

    @staticmethod
    def _mkdir(client: BoxClient, parent_id: str, name: str) -> _ItemData:
        """Makes a directory within a parent_id given a name

        Args:
            client: The Box client to use
            parent_id: The parent to make the directory in
            name: The name of the directory to make

        Returns:
            The id of the returned directory

        """
        ret_folder = client.folders.create_folder(
            name=name, parent=CreateFolderParent(id=parent_id)
        )
        return _ItemData(id=ret_folder.id, name=ret_folder.name, is_folder=True)

    def _resolve_path_to_id(
        self,
        client: BoxClient,
        path: Path,
        is_folder: bool,
        mk_parent: bool = False,
        mkdir: bool = False,
    ) -> _ItemData:
        """Traverses a virtual Path structure starting at your root BOX_FOLDER_ID.

        Args:
            client: The Box client to use
            path: The path to resolve
            is_folder: If we are resolving a directory
            mk_parent: If directory not found, make directories
            mkdir: If searching for a directory and not found, create it

        Returns:
            Item Data of the resolved object

        Raises:
            FileNotFoundError: If any node was not found

        """
        current_id = self._box_folder_id
        parts = path.parts

        if not parts:
            return _ItemData(current_id, name=None, is_folder=True)

        # Separate the file name/leaf node from directory parts
        directory_parts = parts[:-1]
        target_name = parts[-1]

        # Traverse directory layout tree
        for folder_name in directory_parts:
            next_item = self._get_item(client, current_id, folder_name, is_folder=True)
            if not next_item:
                if mk_parent:
                    next_item = self._mkdir(client, current_id, folder_name)
                else:
                    raise FileNotFoundError(
                        f"Folder {folder_name} was not found in {current_id}"
                    )

            current_id = next_item.id

        ret_item = self._get_item(client, current_id, target_name, is_folder=is_folder)
        if not ret_item:
            if mkdir and is_folder:
                ret_item = self._mkdir(client, current_id, target_name)
            else:
                raise FileNotFoundError(
                    f"Target {target_name} was not found in {current_id}"
                )

        return ret_item

    @override
    def exists(self, path: Path) -> bool:
        client = self._box_auth.get_client()
        parent_dir = self._resolve_path_to_id(client, path.parent, is_folder=True)
        return (
            self._get_item(client, parent_dir.id, name=path.name, is_folder=False)
            is not None
        )

    @override
    def _raw_open(self, path: Path) -> int:
        """Resolves the path string and builds a handle

        Args:
            path: The path to resolve

        Returns:
            A handle to the file

        """
        client = self._box_auth.get_client()
        self._session_counter += 1
        handle = self._session_counter

        parent_dir = self._resolve_path_to_id(client, path.parent, is_folder=True)
        filename = path.name
        f = self._get_item(client, parent_dir.id, name=filename, is_folder=False)

        # Look up if the exact file target entity already exists
        file_id = f.id if f else None

        # Record this structural session map into state
        self._session_registry[handle] = _SessionEntry(
            client,
            parent_dir.id,
            filename,
            file_id,
        )

        return handle

    @override
    def _raw_close(self, handle: int) -> bool:
        """Evicts handle reference and closes file

        Args:
            handle: The handle to close

        Returns:
            True if closed successfully

        """
        if handle in self._session_registry:
            _ = self._session_registry.pop(handle)
            return True
        return False

    @override
    def delete(self, path: Path) -> bool:
        """Deletes target file from Box

        Args:
            path: The path to the file to delete

        Returns:
            True if file existed and was deleted

        """
        client = self._box_auth.get_client()
        parent_dir = self._resolve_path_to_id(client, path.parent, is_folder=True)

        item = self._get_item(client, parent_dir.id, path.name, is_folder=False)

        if not item:
            return False

        client.files.delete_file_by_id(item.id)
        self._get_item.cache_clear()

        return True

    @override
    def list(self, path: Path) -> tuple[Sequence[Path], Sequence[Path]]:
        """Lists directory contents of a path

        Args:
            path: The path to directory to list

        Returns:
            A list of full pathes to items within that directory

        """
        client = self._box_auth.get_client()
        parent_dir = self._resolve_path_to_id(client, path, is_folder=True)

        items = client.folders.get_folder_items(parent_dir.id).entries or []
        return (
            [
                path / entry.name
                for entry in items
                if entry.type == FolderBaseTypeField.FOLDER and entry.name
            ],
            [
                path / entry.name
                for entry in items
                if entry.type == FileBaseTypeField.FILE and entry.name
            ],
        )

    @override
    def mkdir(
        self, path: Path, parents_ok: bool = True, exists_ok: bool = True
    ) -> None:
        """Makes a directory at the given path

        Args:
            path: The path to create
            parents_ok: Is okay to create directory parent
            exists_ok: Is okay to ignore if the directory already exists

        """
        client = self._box_auth.get_client()
        _ = self._resolve_path_to_id(
            client, path.parent, True, mk_parent=parents_ok, mkdir=exists_ok
        )

    @override
    def rmdir(self, path: Path) -> bool:
        """Removes a directory given a path

        Args:
            path: The directory to delete

        Returns:
            True if deleted, False if does not exist

        """
        client = self._box_auth.get_client()
        parent_dir = self._resolve_path_to_id(client, path.parent, True)
        folder = self._get_item(client, parent_dir.id, path.name, is_folder=True)
        if not folder:
            return False
        client.folders.delete_folder_by_id(folder.id)
        self._get_item.cache_clear()
        return True

    @override
    def _raw_read_stream(self, handle: int) -> Iterator[bytes]:
        """Reads a file and streams contents given a handle

        Args:
            handle: The handle to read

        Yields:
            Raw bytes of the read file

        Raises:
            KeyError: If file was not open or does not exist
            FileNotFoundError: If Box could not return the file contents

        """
        session = self._session_registry.get(handle)
        if not session or not session.file_id:
            raise KeyError("File does not yet exist")

        client = session.client
        download_response = client.downloads.download_file(file_id=session.file_id)

        if not download_response:
            raise FileNotFoundError("Requested file not found on Box")

        while True:
            chunk = download_response.read(self.CHUNK_SIZE)
            if not chunk:
                break
            yield chunk

    @override
    def _raw_write_stream(
        self, handle: int, stream: Iterator[bytes], size: int, allow_override: bool
    ) -> None:
        """Streams chunk blocks to Box to a path

        If file exists and is small, a new version will be created.
        If allow_override is true and file is large, then the old file will be deleted

        Args:
            handle: The file to write to
            stream: The content to write
            size: The size in bytes of the file to write
            allow_override: Allow deleting old file

        Raises:
            KeyError: If handle does not exist
            FileExistsError: If the file exists and overriding is not permitted

        """
        session = self._session_registry.get(handle)
        if not session:
            raise KeyError("Active write session handle context missing.")

        is_big = size > 20 * 1024**2

        # If file already exists, delete it first to allow clean overwrite
        if session.file_id:
            if allow_override:
                if is_big:
                    try:
                        session.client.files.delete_file_by_id(session.file_id)
                        self._get_item.cache_clear()
                    except BoxAPIError:
                        pass
            else:
                raise FileExistsError(
                    "The requested file already exists, and override is not permitted"
                )

        # Execute upload block payload
        safe_stream = ResponseByteStream(stream)
        # Overload the len attribute to explicitly mark size
        safe_stream.len = size  # pyright: ignore[reportAttributeAccessIssue]

        if size > self.CHUNKED_UPLOAD_THRESHOLD:
            result = session.client.chunked_uploads.upload_big_file(
                file_name=session.filename,
                file_size=size,
                parent_folder_id=session.parent_id,
                file=safe_stream,
            )
        elif session.file_id:
            res = session.client.uploads.upload_file_version(
                session.file_id,
                UploadFileVersionAttributes(session.filename),
                file=safe_stream,
            ).entries
            result = res[0] if res else None
        else:
            res = session.client.uploads.upload_file(
                UploadFileAttributes(
                    session.filename,
                    UploadFileAttributesParentField(id=session.parent_id),
                ),
                file=safe_stream,
            ).entries
            result = res[0] if res else None

        # Refresh handle and cache
        self._session_registry[handle] = _SessionEntry(
            session.client,
            session.parent_id,
            session.filename,
            result.id if result else None,
        )

        if self._get_item.cache:
            self._get_item.cache.pop(
                hashkey(
                    session.parent_id,
                    session.filename,
                    False,
                )
            )

    @override
    def get_times(self, path: Path) -> FileTimeInfo:
        client = self._box_auth.get_client()
        f = self._resolve_path_to_id(client, path, is_folder=False)
        file = client.files.get_file_by_id(f.id)

        return FileTimeInfo(
            file.modified_at or dt.datetime.now(dt.UTC),
            file.created_at or dt.datetime.now(dt.UTC),
            file.modified_at or dt.datetime.now(dt.UTC),
        )

    @override
    def size(self, path: Path) -> int:
        client = self._box_auth.get_client()
        f = self._resolve_path_to_id(client, path, is_folder=False)
        file = client.files.get_file_by_id(f.id)
        return file.size or 0

    @override
    def health(self) -> None:
        """Tries accessing the root folder.

        Raises:
            Exception: Error string if folder is not accessible

        """
        try:
            client = self._box_auth.get_client()
            _ = client.folders.get_folder_by_id(self._box_folder_id)
        except Exception as exc:
            raise Exception(f"Box service connection broken: {exc}") from exc
