#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE.txt file in the root directory of this source tree.

import json
import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import ContextManager, Dict, List, Optional, Type

import h5py
import numpy as np
import torch
from torch_extensions.tensorlist.tensorlist import TensorList

from torchbiggraph.edgelist import EdgeList
from torchbiggraph.entitylist import EntityList
from torchbiggraph.plugin import URLPluginRegistry
from torchbiggraph.util import CouldNotLoadData


logger = logging.getLogger("torchbiggraph")


class AbstractEntityStorage(ABC):

    @abstractmethod
    def __init__(self, url: str) -> None:
        pass

    @abstractmethod
    def prepare(self) -> None:
        pass

    @abstractmethod
    def has_count(self, entity_name: str, partition: int) -> bool:
        pass

    @abstractmethod
    def save_count(self, entity_name: str, partition: int, count: int) -> None:
        pass

    @abstractmethod
    def load_count(self, entity_name: str, partition: int) -> int:
        pass

    @abstractmethod
    def has_names(self, entity_name: str, partition: int) -> bool:
        pass

    @abstractmethod
    def save_names(self, entity_name: str, partition: int, names: List[str]) -> None:
        pass

    @abstractmethod
    def load_names(self, entity_name: str, partition: int) -> List[str]:
        pass


class AbstractRelationTypeStorage(ABC):

    @abstractmethod
    def __init__(self, url: str) -> None:
        pass

    @abstractmethod
    def prepare(self) -> None:
        pass

    @abstractmethod
    def has_count(self) -> None:
        pass

    @abstractmethod
    def save_count(self, count: int) -> None:
        pass

    @abstractmethod
    def load_count(self) -> int:
        pass

    @abstractmethod
    def has_names(self) -> bool:
        pass

    @abstractmethod
    def save_names(self, names: List[str]) -> None:
        pass

    @abstractmethod
    def load_names(self) -> List[str]:
        pass


class AbstractEdgeAppender(ABC):

    @abstractmethod
    def append_edges(self, edges: EdgeList) -> None:
        pass


class AbstractEdgeStorage(ABC):

    @abstractmethod
    def __init__(self, url: str) -> None:
        pass

    @abstractmethod
    def prepare(self) -> None:
        pass

    @abstractmethod
    def has_edges(self, lhs_p: int, rhs_p: int) -> bool:
        pass

    def load_edges(self, lhs_p: int, rhs_p: int) -> EdgeList:
        return self.load_chunk_of_edges(lhs_p, rhs_p, chunk_idx=0, num_chunks=1)

    @abstractmethod
    def load_chunk_of_edges(
        self,
        lhs_p: int,
        rhs_p: int,
        chunk_idx: int,
        num_chunks: int,
    ) -> EdgeList:
        pass

    def save_edges(self, lhs_p: int, rhs_p: int, edges: EdgeList) -> None:
        with self.save_edges_by_appending(lhs_p, rhs_p) as appender:
            appender.append_edges(edges)

    @abstractmethod
    def save_edges_by_appending(
        self,
        lhs_p: int,
        rhs_p: int,
    ) -> ContextManager[AbstractEdgeAppender]:
        pass


ENTITY_STORAGES = URLPluginRegistry[AbstractEntityStorage]()
RELATION_TYPE_STORAGES = URLPluginRegistry[AbstractRelationTypeStorage]()
EDGE_STORAGES = URLPluginRegistry[AbstractEdgeStorage]()


def save_count(path: Path, count: int) -> None:
    with path.open("wt") as tf:
        tf.write(f"{count}\n")


def load_count(path: Path) -> int:
    try:
        with path.open("rt") as tf:
            return int(tf.read().strip())
    except FileNotFoundError as err:
        raise CouldNotLoadData() from err


def save_names(path: Path, names: List[str]) -> None:
    with path.open("wt") as tf:
        json.dump(names, tf, indent=4)


def load_names(path: Path) -> List[str]:
    try:
        with path.open("rt") as tf:
            return json.load(tf)
    except FileNotFoundError as err:
        raise CouldNotLoadData() from err


@ENTITY_STORAGES.register_as("")  # No scheme
@ENTITY_STORAGES.register_as("file")
class FileEntityStorage(AbstractEntityStorage):

    def __init__(self, path: str) -> None:
        if path.startswith("file://"):
            path = path[len("file://"):]
        self.path = Path(path).resolve(strict=False)

    def get_count_file(self, entity_name: str, partition: int) -> Path:
        return self.path / f"entity_count_{entity_name}_{partition}.txt"

    def get_names_file(self, entity_name: str, partition: int) -> Path:
        return self.path / f"entity_names_{entity_name}_{partition}.json"

    def prepare(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    def has_count(self, entity_name: str, partition: int) -> bool:
        return self.get_count_file(entity_name, partition).is_file()

    def save_count(self, entity_name: str, partition: int, count: int) -> None:
        save_count(self.get_count_file(entity_name, partition), count)

    def load_count(self, entity_name: str, partition: int) -> int:
        return load_count(self.get_count_file(entity_name, partition))

    def has_names(self, entity_name: str, partition: int) -> bool:
        return self.get_names_file(entity_name, partition).is_file()

    def save_names(self, entity_name: str, partition: int, names: List[str]) -> None:
        save_names(self.get_names_file(entity_name, partition), names)

    def load_names(self, entity_name: str, partition: int) -> List[str]:
        return load_names(self.get_names_file(entity_name, partition))


@RELATION_TYPE_STORAGES.register_as("")  # No scheme
@RELATION_TYPE_STORAGES.register_as("file")
class FileRelationTypeStorage(AbstractRelationTypeStorage):

    def __init__(self, path: str) -> None:
        if path.startswith("file://"):
            path = path[len("file://"):]
        self.path = Path(path).resolve(strict=False)

    def get_count_file(self) -> Path:
        return self.path / "dynamic_rel_count.txt"

    def get_names_file(self) -> Path:
        return self.path / f"dynamic_rel_names.json"

    def prepare(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    def has_count(self) -> None:
        return self.get_count_file().is_file()

    def save_count(self, count: int) -> None:
        save_count(self.get_count_file(), count)

    def load_count(self) -> int:
        return load_count(self.get_count_file())

    def has_names(self) -> bool:
        return self.get_names_file().is_file()

    def save_names(self, names: List[str]) -> None:
        save_names(self.get_names_file(), names)

    def load_names(self) -> List[str]:
        return load_names(self.get_names_file())


# Names and values of metadata attributes for the HDF5 files.
FORMAT_VERSION_ATTR = "format_version"
FORMAT_VERSION = 1


def torch_to_numpy_dtype(dtype):
    return torch.empty((), dtype=dtype).numpy().dtype


class BufferedDataset:

    DATA_TYPE = torch.long  # int64, 8 bytes
    BUFFER_SIZE = 2 ** 20 // 8  # 1MiB

    def __init__(self, hf: h5py.File, dataset_name: str) -> None:
        self.hf: h5py.File = hf
        self.dataset_name: str = dataset_name
        self.dataset: h5py.Dataset = self.hf.create_dataset(
            name=self.dataset_name,
            dtype=torch_to_numpy_dtype(self.DATA_TYPE),
            shape=(0,),
            chunks=(self.BUFFER_SIZE,),
            maxshape=(None,),
        )
        self.buffer: torch.Tensor = torch.empty((self.BUFFER_SIZE,), dtype=self.DATA_TYPE)
        self.buffer_offset: int = 0
        self.total_data: int = 0

    def flush_buffer(self, _last: bool = False) -> None:
        if not _last:
            assert self.buffer_offset == self.BUFFER_SIZE
        elif self.buffer_offset == 0:
            return
        logger.info(f"Flushing one chunk of {self.buffer_offset} elements "
                    f"to dataset {self.dataset_name!r} of file {self.hf.filename}")
        self.dataset.resize(self.dataset.shape[0] + self.buffer_offset, axis=0)
        self.dataset[-self.buffer_offset:] = self.buffer[:self.buffer_offset].numpy()
        self.buffer_offset = 0

    def append(self, tensor: torch.Tensor) -> None:
        tensor_size, = tensor.shape
        tensor_offset = 0
        while True:
            tensor_left = tensor_size - tensor_offset
            buffer_left = self.BUFFER_SIZE - self.buffer_offset
            if tensor_left >= buffer_left:
                self.buffer[self.buffer_offset:self.buffer_offset + buffer_left] = \
                    tensor[tensor_offset:tensor_offset + buffer_left]
                tensor_offset += buffer_left
                self.buffer_offset += buffer_left
                self.flush_buffer()
                continue
            else:
                self.buffer[self.buffer_offset:self.buffer_offset + tensor_left] = \
                    tensor[tensor_offset:tensor_offset + tensor_left]
                tensor_offset += tensor_left
                self.buffer_offset += tensor_left
                break
        self.total_data += tensor_size


class FileEdgeAppender(AbstractEdgeAppender):

    def __init__(self, hf: h5py.File) -> None:
        self.hf: h5py.File = hf
        self.datasets: Dict[str, BufferedDataset] = {}

    def __enter__(self) -> "FileEdgeAppender":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        for dataset in self.datasets.values():
            dataset.flush_buffer(_last=True)
        self.hf.close()

    def append_tensor(self, name: str, tensor: torch.Tensor) -> None:
        if name not in self.datasets:
            self.datasets[name] = BufferedDataset(self.hf, name)
        self.datasets[name].append(tensor)

    def append_tensor_list(self, name: str, tensor_list: TensorList) -> None:
        offsets_name = f"{name}_offsets"
        data_name = f"{name}_data"
        if offsets_name not in self.datasets:
            self.datasets[offsets_name] = BufferedDataset(self.hf, offsets_name)
            self.datasets[offsets_name].append(torch.tensor([0], dtype=torch.long))
        if data_name not in self.datasets:
            self.datasets[data_name] = BufferedDataset(self.hf, data_name)
        offsets = tensor_list.offsets[1:] + self.datasets[data_name].total_data
        data = tensor_list.data
        self.datasets[offsets_name].append(offsets)
        self.datasets[data_name].append(data)

    def append_edges(self, edgelist: EdgeList) -> None:
        self.append_tensor("lhs", edgelist.lhs.tensor)
        self.append_tensor("rhs", edgelist.rhs.tensor)
        self.append_tensor("rel", edgelist.rel)
        if len(edgelist.lhs.tensor_list.data) != 0:
            self.append_tensor_list("lhsd", edgelist.lhs.tensor_list)
        if len(edgelist.rhs.tensor_list.data) != 0:
            self.append_tensor_list("rhsd", edgelist.rhs.tensor_list)


@EDGE_STORAGES.register_as("")  # No scheme
@EDGE_STORAGES.register_as("file")
class FileEdgeStorage(AbstractEdgeStorage):
    """Reads partitioned edgelists from disk, in the format
    created by edge_downloader.py.

    Edge lists are stored as hdf5 allowing partial reads (for multi-pass).

    Currently simple implementation but should eventually be multi-threaded /
    pipelined.
    """

    def __init__(self, path: str) -> None:
        if path.startswith("file://"):
            path = path[len("file://"):]
        self.path = Path(path).resolve(strict=False)

    def get_edges_file(self, lhs_p: int, rhs_p: int) -> Path:
        return self.path / f"edges_{lhs_p}_{rhs_p}.h5"

    def prepare(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    def has_edges(
        self,
        lhs_p: int,
        rhs_p: int,
    ) -> bool:
        return self.get_edges_file(lhs_p, rhs_p).is_file()

    def load_chunk_of_edges(
        self,
        lhs_p: int,
        rhs_p: int,
        chunk_idx: int = 0,
        num_chunks: int = 1,
    ) -> EdgeList:
        file_path = self.get_edges_file(lhs_p, rhs_p)
        if not file_path.is_file():
            raise RuntimeError(f"{file_path} does not exist")
        with h5py.File(file_path, 'r') as hf:
            if hf.attrs.get(FORMAT_VERSION_ATTR, None) != FORMAT_VERSION:
                raise RuntimeError(f"Version mismatch in edge file {file_path}")
            lhs_ds = hf['lhs']
            rhs_ds = hf['rhs']
            rel_ds = hf['rel']

            num_edges = rel_ds.len()
            begin = int(chunk_idx * num_edges / num_chunks)
            end = int((chunk_idx + 1) * num_edges / num_chunks)
            chunk_size = end - begin

            lhs = torch.empty((chunk_size,), dtype=torch.long)
            rhs = torch.empty((chunk_size,), dtype=torch.long)
            rel = torch.empty((chunk_size,), dtype=torch.long)

            # Needed because https://github.com/h5py/h5py/issues/870.
            if chunk_size > 0:
                lhs_ds.read_direct(lhs.numpy(), source_sel=np.s_[begin:end])
                rhs_ds.read_direct(rhs.numpy(), source_sel=np.s_[begin:end])
                rel_ds.read_direct(rel.numpy(), source_sel=np.s_[begin:end])

            lhsd = self.read_dynamic(hf, 'lhsd', begin, end)
            rhsd = self.read_dynamic(hf, 'rhsd', begin, end)

            return EdgeList(EntityList(lhs, lhsd),
                            EntityList(rhs, rhsd),
                            rel)

    @staticmethod
    def read_dynamic(
        hf: h5py.File,
        key: str,
        begin: int,
        end: int,
    ) -> TensorList:
        try:
            offsets_ds = hf[f"{key}_offsets"]
            data_ds = hf[f"{key}_data"]
        except LookupError:
            # Empty tensor_list representation
            return TensorList(
                offsets=torch.zeros((), dtype=torch.long).expand(end - begin + 1),
                data=torch.empty((0,), dtype=torch.long))

        offsets = torch.empty((end - begin + 1,), dtype=torch.long)
        offsets_ds.read_direct(offsets.numpy(), source_sel=np.s_[begin:end + 1])
        data_begin = offsets[0].item()
        data_end = offsets[-1].item()
        data = torch.empty((data_end - data_begin,), dtype=torch.long)
        # Needed because https://github.com/h5py/h5py/issues/870.
        if data_end - data_begin > 0:
            data_ds.read_direct(data.numpy(), source_sel=np.s_[data_begin:data_end])

        offsets -= int(offsets[0])

        return TensorList(offsets, data)

    @contextmanager
    def save_edges_by_appending(
        self,
        lhs_p: int,
        rhs_p: int,
    ) -> ContextManager[AbstractEdgeAppender]:
        file_path = self.get_edges_file(lhs_p, rhs_p)
        tmp_file_path = file_path.parent / f"{file_path.stem}.tmp{file_path.suffix}"
        if tmp_file_path.is_file():
            tmp_file_path.unlink()
        with h5py.File(tmp_file_path, "x") as hf, FileEdgeAppender(hf) as appender:
            hf.attrs[FORMAT_VERSION_ATTR] = FORMAT_VERSION
            yield appender
        tmp_file_path.rename(file_path)
