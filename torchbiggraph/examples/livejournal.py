#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE.txt file in the root directory of this source tree.

import argparse
import random
from itertools import chain
from pathlib import Path

import attr
import pkg_resources

from torchbiggraph.config import add_to_sys_path, ConfigFileLoader
from torchbiggraph.converters.import_from_tsv import convert_input_data
from torchbiggraph.converters.utils import convert_path, download_url, extract_gzip
from torchbiggraph.eval import do_eval
from torchbiggraph.train import train
from torchbiggraph.util import (
    set_logging_verbosity,
    setup_logging,
    SubprocessInitializer,
)


URL = 'https://snap.stanford.edu/data/soc-LiveJournal1.txt.gz'
FILENAMES = {
    'train': 'train.txt',
    'test': 'test.txt',
}
TRAIN_FRACTION = 0.75

# Figure out the path where the sample config was installed by the package manager.
# This can be overridden with --config.
DEFAULT_CONFIG = pkg_resources.resource_filename("torchbiggraph.examples",
                                                 "configs/livejournal_config.py")


def random_split_file(fpath: Path) -> None:
    train_file = fpath.parent / FILENAMES['train']
    test_file = fpath.parent / FILENAMES['test']

    if train_file.exists() and test_file.exists():
        print("Found some files that indicate that the input data "
              "has already been shuffled and split, not doing it again.")
        print(f"These files are: {train_file} and {test_file}")
        return

    print('Shuffling and splitting train/test file. This may take a while.')

    print(f"Reading data from file: {fpath}")
    with fpath.open("rt") as in_tf:
        lines = in_tf.readlines()

    # The first few lines are comments
    lines = lines[4:]
    print('Shuffling data')
    random.shuffle(lines)
    split_len = int(len(lines) * TRAIN_FRACTION)

    print('Splitting to train and test files')
    with train_file.open("wt") as out_tf_train:
        for line in lines[:split_len]:
            out_tf_train.write(line)

    with test_file.open("wt") as out_tf_test:
        for line in lines[split_len:]:
            out_tf_test.write(line)


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description='Example on Livejournal')
    parser.add_argument('--config', default=DEFAULT_CONFIG,
                        help='Path to config file')
    parser.add_argument('-p', '--param', action='append', nargs='*')
    parser.add_argument('--data_dir', type=Path, default='data',
                        help='where to save processed data')

    args = parser.parse_args()

    if args.param is not None:
        overrides = chain.from_iterable(args.param)  # flatten
    else:
        overrides = None

    # download data
    data_dir = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    fpath = download_url(URL, data_dir)
    fpath = extract_gzip(fpath)
    print('Downloaded and extracted file.')

    # random split file for train and test
    random_split_file(fpath)

    loader = ConfigFileLoader()
    config = loader.load_config(args.config, overrides)
    set_logging_verbosity(config.verbose)
    subprocess_init = SubprocessInitializer()
    subprocess_init.register(setup_logging, config.verbose)
    subprocess_init.register(add_to_sys_path, loader.config_dir.name)
    edge_paths = [data_dir / name for name in FILENAMES.values()]

    convert_input_data(
        config.entities,
        config.relations,
        config.entity_path,
        edge_paths,
        lhs_col=0,
        rhs_col=1,
        rel_col=None,
        dynamic_relations=config.dynamic_relations,
    )

    train_path = [str(convert_path(data_dir / FILENAMES['train']))]
    train_config = attr.evolve(config, edge_paths=train_path)

    train(train_config, subprocess_init=subprocess_init)

    eval_path = [str(convert_path(data_dir / FILENAMES['test']))]
    eval_config = attr.evolve(config, edge_paths=eval_path)

    do_eval(eval_config, subprocess_init=subprocess_init)


if __name__ == "__main__":
    main()
