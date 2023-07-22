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

class SIO: # SamplerIterOpts
    def __init__(self, batch_size=64, shuffle=True, drop_last=False):
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.drop_last = drop_last

    def __repr__(self):
        return f"SIO(batch_size={self.batch_size}, shuffle={self.shuffle}, drop_last={self.drop_last})"

class SamplerIter:
    def __init__(self, indices, sampler_iter_opts: SIO):
        self.indices = indices
        self.opts = sampler_iter_opts

    def __iter__(self):
        if self.opts.shuffle: random.shuffle(self.indices)

        batches = chunkify(self.indices, self.opts.batch_size)
        need_extra = self.opts.batch_size - len(batches[-1])
        if need_extra:
            if self.opts.drop_last:
                batches.pop()
            else:
                batches[-1].extend(random.choices(self.indices, k=need_extra))

        yield from batches

class Sampler:
    def __init__(self, num_items):
        self.num_items = num_items

    def iter(self, sampler_iter_opts=None):
        sampler_iter_opts = sampler_iter_opts or SIO()
        indices = list(range(self.num_items))
        return SamplerIter(indices, sampler_iter_opts)

