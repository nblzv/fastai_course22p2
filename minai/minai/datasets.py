# Autogenerated! Edit minai_nbs/datasets.ipynb instead

from pathlib import Path
from urllib.request import urlretrieve
import gzip
import pickle

import torch

DATASETS_CACHE_BASE_PATH = Path("~/.cache/minai/datasets").expanduser()


def load_mnist():
    MNIST_URL = "https://github.com/mnielsen/neural-networks-and-deep-learning/raw/master/data/mnist.pkl.gz"
    
    path_data = DATASETS_CACHE_BASE_PATH / "MNIST"
    path_data.mkdir(exist_ok=True, parents=True)
    path_zip = path_data / "mnist.zip"

    if not path_zip.exists(): 
        print(f"Downloading file to {path_zip}")
        urlretrieve(MNIST_URL, path_zip)

    with gzip.open(path_zip) as f: 
        (x_train, y_train), (x_val, y_val), (x_test, y_test) = pickle.load(f, encoding="latin-1")
        x_train, y_train, x_val, y_val, x_test, y_test = map(torch.tensor, (x_train, y_train, x_val, y_val, x_test, y_test))
    
    return x_train, y_train, x_val, y_val, x_test, y_test

