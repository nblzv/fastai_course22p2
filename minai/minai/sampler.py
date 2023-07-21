# Autogenerated! Edit minai_nbs/sampler.ipynb instead

import itertools
import random

def chunkify(container, chunk_size):
    num_items = len(container)
    it = iter(container)

    full_chunks = num_items // chunk_size
    leftover = num_items - full_chunks*chunk_size

    chunks = [list(itertools.islice(it, chunk_size)) for _ in range(full_chunks)]
    if leftover: chunks.append(list(it))
    
    return chunks

class SamplerIter:
    def __init__(self, indices, batch_size, shuffle, drop_last):
        self.indices = indices
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.drop_last = drop_last

    def __iter__(self):
        if self.shuffle: random.shuffle(self.indices)

        batches = chunkify(self.indices, self.batch_size)
        need_extra = self.batch_size - len(batches[-1])
        if need_extra:
            if self.drop_last:
                batches.pop()
            else:
                batches[-1].extend(random.choices(self.indices, k=need_extra))

        yield from batches

class Sampler:
    def __init__(self, num_items):
        self.num_items = num_items

    def iter(self, batch_size, shuffle=False, drop_last=False):
        indices = list(range(self.num_items))
        return SamplerIter(indices, batch_size, shuffle, drop_last)

