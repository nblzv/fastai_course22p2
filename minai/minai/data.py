# Autogenerated! Edit minai_nbs/data.ipynb instead

import threading
import queue
import os
import math
import itertools
import copy

import datasets as hfds
import torch
import torchvision.transforms.functional as TF
import torchvision.io as TFIO

import minai.sampler as mins
import minai.datasets as minds

def simple_collate_func(array_of_results):
    xs = [r[0] for results in array_of_results for r in results]
    ys = [r[1] for results in array_of_results for r in results]
    return xs, ys

class HFCollate:
    def __init__(self, ds: hfds.Dataset, device=None):
        self.features = tuple(ds.features.keys())
        self.device = device

    def __call__(self, array_of_results):
        collated = [[] for _ in range(len(self.features))]
        for result in array_of_results:
            for i, feature in enumerate(self.features):
                collated[i].extend(result[feature])

        for i in range(len(collated)):
            if type(collated[i][0]) is not torch.Tensor:
                collated[i] = torch.tensor(collated[i]).to(self.device)
            else:
                collated[i] = torch.stack(collated[i]).to(self.device)

        return collated
    
    def __repr__(self):
        return f"HFCollate(features={self.features}, device={self.device})"

def clamp(a, x, b):
    return min(max(a, x), b)

WORK_TYPE_NONE = 0
WORK_TYPE_LOAD_BATCHES = 1
WORK_TYPE_GET_ITEMS = 2
WORK_TYPE_SHUTDOWN = 100

class WorkItem:
    def __init__(self, type):
        self.type = type

    #def __del__(self): print("work item dead", self.type, threading.get_native_id())

    def __repr__(self): return f"{self.__class__.__name__}({str(vars(self))})"

class WorkItemLoadBatches(WorkItem):
    def __init__(self, cached_iter: "Collator.CachedIter", num_batches):
        super().__init__(WORK_TYPE_LOAD_BATCHES)
        self.cached_iter = cached_iter
        self.num_batches = num_batches

    #def __del__(self): print("work item loadbatches dead", threading.get_native_id())

class WorkItemGetItems(WorkItem):
    def __init__(self, group: "WorkGroup", indices):
        super().__init__(WORK_TYPE_GET_ITEMS)
        self.group = group
        self.indices = indices
        self.results = None

        self.group.gi_work_array.append(self)

    #def __del__(self): print("work item getitems dead", threading.get_native_id())

class COPTS: # CollatorOpts
    def __init__(self,
                 *, 
                 num_threads = None, 
                 debug_out_queue: queue.SimpleQueue = None):
        self.num_threads = num_threads
        self.debug_out_queue = debug_out_queue
    
    def __repr__(self): return str(vars(self))

    def finalize(self):
        cpu_count = os.cpu_count()
        if self.num_threads is None: self.num_threads = max(1, cpu_count//2)
        self.num_threads = clamp(0, self.num_threads, cpu_count*10)

        return self

class COIOPTS: # Collator(Cached)IterOpts
    DEFAULT_DEVICE = None

    def __init__(self,
                 *,
                 sampler_iter: mins.SamplerIter = None,
                 cached_batch_count = 1,
                 sub_batch_size = None,
                 getitem_func = None,
                 collate_func = None,
                 collate_device = None):

        self.sampler_iter = sampler_iter
        self.cached_batch_count = cached_batch_count
        self.sub_batch_size = sub_batch_size
        self.getitem_func = getitem_func
        self.collate_func = collate_func
        self.collate_device = collate_device or self.DEFAULT_DEVICE

    def __repr__(self): return str(vars(self))

    def finalize(self, collator_opts: COPTS):
        if collator_opts.num_threads == 0:
            self.cached_batch_count = 0
            self.sub_batch_size = self.sampler_iter.opts.batch_size
        else:
            if self.sub_batch_size is None:
                self.sub_batch_size = math.ceil(self.sampler_iter.opts.batch_size / collator_opts.num_threads)
            elif self.sub_batch_size == 0:
                self.sub_batch_size = self.sampler_iter.opts.batch_size

        self.sub_batch_size = clamp(1, self.sub_batch_size, self.sampler_iter.opts.batch_size)

        return self


class Collator:
    class CachedIter:
        def __init__(self, serial, collator_iter_opts: COIOPTS):
            self.serial = serial
            self.opts = collator_iter_opts
            self.iter = iter(collator_iter_opts.sampler_iter)
            self.num_groups_total = collator_iter_opts.sampler_iter.num_batches
            self.num_groups_requested = 0
            self.num_groups_started = 0
            self.num_groups_finished = 0
            self.lock = threading.Lock()
            self.collated_queue = queue.SimpleQueue()

        #def __del__(self): print("cached iter dead", threading.get_native_id())

        def __repr__(self):
            return f"CachedIter(serial={self.serial}, total={self.num_groups_total}, requested={self.num_groups_requested}, started={self.num_groups_started}, finished={self.num_groups_finished}, opts={self.opts})"

    def __init__(self, copts: COPTS):
        self.opts = copts.finalize()

        self.threads_spawned = False
        self.work_queue = queue.SimpleQueue()
        self.current_iter_serial = 0
        self.shutdown_counter = None
        self.registered_dl_count = 0

    #def __del__(self): print("collator dead", threading.get_native_id())

    def __repr__(self): return str(vars(self))

    def start_new_iter(self, collator_iter_opts: COIOPTS):
        if not self.threads_spawned: 
            self.shutdown_counter = threading.Semaphore(self.opts.num_threads)
            for i in range(self.opts.num_threads): 
                threading.Thread(target=collator_threadproc, args=(i+1, self)).start()
                self.shutdown_counter.acquire()
            
            self.threads_spawned = True

        self.current_iter_serial += 1
        new_iter_serial = self.current_iter_serial
        if self.opts.debug_out_queue: self.opts.debug_out_queue.put(f"[0] New iter {new_iter_serial}")

        cached_iter = self.CachedIter(new_iter_serial, collator_iter_opts)
        
        return cached_iter
    
    def load_batches(self, cached_iter: CachedIter, num_batches):
        if not num_batches: return
        
        cached_iter.lock.acquire()
        to_request = min(num_batches, cached_iter.num_groups_total - cached_iter.num_groups_requested)
        cached_iter.num_groups_requested += to_request
        cached_iter.lock.release()

        if to_request:
            self.work_queue.put(WorkItemLoadBatches(cached_iter, to_request))
            if self.opts.debug_out_queue: self.opts.debug_out_queue.put(f"[0] Requesting {to_request} batches for iter {cached_iter.serial}")

            if self.opts.num_threads == 0:
                collator_threadproc(0, self)

    def register_dl(self): 
        self.registered_dl_count += 1
    def unregister_dl(self): 
        self.registered_dl_count -= 1
        if self.registered_dl_count == 0:
            self.shutdown()

    def shutdown(self):
        if self.threads_spawned:
            for _ in range(self.opts.num_threads): self.work_queue.put(WorkItem(WORK_TYPE_SHUTDOWN))
            
            def wait_for_threads_to_shutdown_and_empty_work_queue(num_threads, shutdown_counter, work_queue):
                for _ in range(num_threads): shutdown_counter.acquire()

                while not work_queue.empty(): 
                    got = work_queue.get()
                    if type(got) is WorkItemGetItems:
                        gi_work: WorkItemGetItems = got
                        if gi_work.group: gi_work.group.complete()
            
            threading.Thread(target=wait_for_threads_to_shutdown_and_empty_work_queue, 
                             args=(self.opts.num_threads, self.shutdown_counter, self.work_queue), daemon=True).start()


class WorkGroup:
    def __init__(self, cached_iter: "Collator.CachedIter", batch_serial, num_total):
        self.cached_iter = cached_iter
        self.batch_serial = batch_serial
        self.num_total = num_total
        self.gi_work_array: list[WorkItemGetItems] = []

        self.num_done_lock = threading.Lock()
        self.num_done = 0

    #def __del__(self): print("work group dead", threading.get_native_id())

    def __repr__(self): return f"{self.__class__.__name__}(iter_serial={self.cached_iter.serial}, batch_serial={self.batch_serial}, "\
                                    f"num_done={self.num_done}, num_total={self.num_total})"

    def complete(self):
        for gi_work in self.gi_work_array: 
            gi_work.group = None

        self.gi_work_array.clear()

class CollatedResult:
    def __init__(self, batch_serial, result):
        self.batch_serial = batch_serial
        self.result = result

    #def __del__(self): print("collatedresult dead")

    def __repr__(self): return f"{self.__class__.__name__}({str(vars(self))})"


def collator_process_one_work(thread_id, work_queue, shutdown_counter, debug_out_queue):
    work: WorkItem = work_queue.get()

    if debug_out_queue: debug_out_queue.put(f"[{thread_id}] Got {work}")
    work_type = work.type
    
    if work_type == WORK_TYPE_LOAD_BATCHES:
        lb_work: WorkItemLoadBatches = work
        
        cached_iter = lb_work.cached_iter
        
        cached_iter.lock.acquire()
        read_num_groups = cached_iter.num_groups_started
        
        cached_iter.num_groups_started += lb_work.num_batches
        array_of_batch_indices = list(itertools.islice(cached_iter.iter, lb_work.num_batches))
        cached_iter.lock.release()

        batches_spawned = 0
        for batch_indices in array_of_batch_indices:
            sub_batches = mins.chunkify(batch_indices, cached_iter.opts.sub_batch_size)
            assert len(sub_batches)

            batch_serial = read_num_groups + batches_spawned
            work_group = WorkGroup(cached_iter, batch_serial + 1, len(sub_batches))
            for sub_batch in sub_batches:
                work_queue.put(WorkItemGetItems(work_group, sub_batch))
                if debug_out_queue: debug_out_queue.put(f"[{thread_id}] Queued {work_group.gi_work_array[-1]}")

            batches_spawned += 1


    elif work_type == WORK_TYPE_GET_ITEMS:
        gi_work: WorkItemGetItems = work
        work_group = gi_work.group
        cached_iter = work_group.cached_iter

        gi_work.results = cached_iter.opts.getitem_func(gi_work.indices)

        work_group.num_done_lock.acquire()
        work_group.num_done += 1
        work_group.num_done_lock.release()
        assert work_group.num_done <= work_group.num_total
        
        if work_group.num_done == work_group.num_total:
            assert work_group.num_done == len(work_group.gi_work_array)
            if debug_out_queue: debug_out_queue.put(f"[{thread_id}] Completed group {work_group}")

            
            cached_iter.lock.acquire()
            cached_iter.num_groups_finished += 1
            is_last_group = cached_iter.num_groups_finished == cached_iter.num_groups_total
            cached_iter.lock.release()

            collated = cached_iter.opts.collate_func([gi_work.results for gi_work in work_group.gi_work_array])
            cached_iter.collated_queue.put(CollatedResult(work_group.batch_serial, collated))

            if is_last_group:
                if debug_out_queue: debug_out_queue.put(f"[{thread_id}] Completed iter {cached_iter.serial}")
                cached_iter.collated_queue.put(CollatedResult(0, None))

            work_group.complete()

            if thread_id == 0:
                return True


    elif work_type == WORK_TYPE_SHUTDOWN:
        shutdown_counter.release()
        return True

    else: assert False

    return False

def collator_threadproc(thread_id: int, ctx: Collator):
    work_queue = ctx.work_queue
    shutdown_counter = ctx.shutdown_counter
    debug_out_queue = ctx.opts.debug_out_queue
    
    if debug_out_queue: debug_out_queue.put(f"[{thread_id}] Started")

    while 1:
        should_exit = collator_process_one_work(thread_id, work_queue, shutdown_counter, debug_out_queue)
        if should_exit:
            break

    if debug_out_queue: debug_out_queue.put(f"[{thread_id}] Exiting")


class DataLoaderIter:
    def __init__(self, collator: Collator, cached_iter: Collator.CachedIter):
        self.collator = collator
        self.cached_iter = cached_iter
        
        self.buffer: list[CollatedResult] = []
        self.next_batch_index = 1

    #def __del__(self): print("dliter dead", threading.get_native_id())
    
    def __repr__(self):
        return f"DataLoaderIter({self.cached_iter})"

    def __iter__(self):
        self.collator.load_batches(self.cached_iter, self.cached_iter.opts.cached_batch_count + 1)

        while 1:
            collated: CollatedResult = self.cached_iter.collated_queue.get()
            if not collated.batch_serial:
                assert not self.buffer # batch_serial == 0 should strictly come last
                break

            self.buffer.append(collated)

            while 1:
                found_i = next((i for i, x in enumerate(self.buffer) if x.batch_serial == self.next_batch_index), -1)
                if found_i == -1:
                    break

                to_yield = self.buffer[found_i].result
                self.buffer[found_i] = self.buffer[-1]
                self.buffer.pop()
                self.next_batch_index += 1
                
                yield to_yield
                self.collator.load_batches(self.cached_iter, 1)

class DataLoader:
    def __init__(self, ds, collator: Collator, collator_iter_opts: COIOPTS):
        self.ds = ds
        self.collator = collator
        self.opts = collator_iter_opts
        
        self.opts.finalize(self.collator.opts)
        self.collator.register_dl()

    def __del__(self): 
        #print("dl dead", threading.get_native_id())
        self.collator.unregister_dl()
    
    def __repr__(self): return str(vars(self))

    def __iter__(self):
        cached_iter = self.collator.start_new_iter(self.opts)
        return iter(DataLoaderIter(self.collator, cached_iter))
    
    @classmethod
    def solo(cls, ds, collator_opts: COPTS, collator_iter_opts: COIOPTS):
        collator = Collator(collator_opts)
        return cls(ds, collator, collator_iter_opts)

    @classmethod
    def simple(cls, simple_ds: minds.SimpleDataset, sampler_iter_opts: mins.SIO = None, collator_opts: COPTS = None, collator_iter_opts: COIOPTS = None):
        sampler_iter_opts = sampler_iter_opts or mins.SIO()
        collator_opts = collator_opts or COPTS()
        collator_iter_opts = collator_iter_opts or COIOPTS()

        collator_iter_opts.sampler_iter = mins.Sampler(len(simple_ds)).iter(sampler_iter_opts)
        collator_iter_opts.getitem_func = simple_ds.__getitem__
        collator_iter_opts.collate_func = simple_collate_func
        return cls.solo(simple_ds, collator_opts, collator_iter_opts)

    @classmethod
    def hf(cls, hf_ds: hfds.Dataset, sampler_iter_opts: mins.SIO = None, collator_opts: COPTS = None, collator_iter_opts: COIOPTS = None):
        assert type(hf_ds) is hfds.Dataset, f"Dataset expected, not {type(hf_ds).__name__}"
        sampler_iter_opts = sampler_iter_opts or mins.SIO()
        collator_opts = collator_opts or COPTS()
        collator_iter_opts = collator_iter_opts or COIOPTS()
        
        collator_iter_opts.sampler_iter = mins.Sampler(len(hf_ds)).iter(sampler_iter_opts)
        collator_iter_opts.getitem_func = hf_ds.__getitem__
        collator_iter_opts.collate_func = HFCollate(hf_ds, collator_iter_opts.collate_device).__call__
        return cls.solo(hf_ds, collator_opts, collator_iter_opts)
    
    @classmethod
    def hf_dsd(cls, hf_ds: hfds.Dataset, collator: Collator, sampler_iter_opts: mins.SIO = None, collator_iter_opts: COIOPTS = None):
        assert type(hf_ds) is hfds.Dataset, f"Dataset expected, not {type(hf_ds).__name__}"
        sampler_iter_opts = sampler_iter_opts or mins.SIO()
        collator_iter_opts = collator_iter_opts or COIOPTS()
        
        collator_iter_opts.sampler_iter = mins.Sampler(len(hf_ds)).iter(sampler_iter_opts)
        collator_iter_opts.getitem_func = hf_ds.__getitem__
        collator_iter_opts.collate_func = HFCollate(hf_ds, collator_iter_opts.collate_device).__call__
        return cls(hf_ds, collator, collator_iter_opts)

class HFTransform:
    def __init__(self, features, transform, **extra_args):
        assert type(features) is hfds.features.features.Features
        self.features = tuple(features)
        self.transform = transform

        for k, v in extra_args.items():
            super().__setattr__(k ,v)

    def __call__(self, results):
        return self.transform(self, results)
    
    def __repr__(self):
        return f"HFTransform(features={list(self.features)})"

    @classmethod
    def ff_img_to_tensor(cls, features, n_channels=3): # first_feature
        def tf(ctx: HFTransform, results):
            xs = results[ctx.features[0]]
            for i in range(len(xs)):
                decoded = TF.to_tensor(xs[i])
                xs[i] = decoded.expand(ctx.n_channels, *decoded.shape[1:])
            return results
        
        return cls(features, tf, n_channels=n_channels)
    
    @classmethod
    def ff_img_decode_to_tensor(cls, features, n_channels=3, half=False): # first_feature
        def tf(ctx: HFTransform, results):
            xs = results[ctx.features[0]]
            for i in range(len(xs)):
                raw = torch.frombuffer(xs[i]["bytes"], dtype=torch.uint8)
                decoded = TFIO.decode_image(raw)
                decoded = decoded.expand(ctx.n_channels, *decoded.shape[1:])
                if ctx.half: decoded = decoded.half()
                else: decoded = decoded.float()
                xs[i] = decoded / 255.0
            return results
        
        return cls(features, tf, n_channels=n_channels, half=half)

def first(iterable):
    return next(iter(iterable))

def first_value(iterable):
    return next(iter(iterable.values()))

class DataLoaderDict(dict):
    def __init__(self, collator: Collator, dataloaders_dict: dict[str, DataLoader]):
        self.collator = collator
        super().__init__(dataloaders_dict)

    def __getitem__(self, key) -> DataLoader:
        return super().__getitem__(key)
        
    def __repr__(self):
        return f"DataLoaders({list(self.keys())})"

    @classmethod
    def hf(cls, dsd: hfds.DatasetDict, 
           collator_opts: COPTS = None, 
           sampler_iter_opts: dict[str, mins.SIO] = {}, 
           collator_iter_opts: dict[str, COIOPTS] = {}):
        
        collator_opts = collator_opts or COPTS()
        collator = Collator(collator_opts)

        if type(sampler_iter_opts) is mins.SIO:
            sio_default = sampler_iter_opts
            sampler_iter_opts = {}
        else:
            sio_default = mins.SIO()

        if type(collator_iter_opts) is COIOPTS:
            coiopts_default = collator_iter_opts
            collator_iter_opts = {}
        else:
            coiopts_default = COIOPTS()

        dls = {}
        for k in dsd:
            sio = sampler_iter_opts.get(k, copy.copy(sio_default))
            coiopts = collator_iter_opts.get(k, copy.copy(coiopts_default))

            if k == "train":
                sio.shuffle = True
            else: 
                sio.batch_size *= 2

            dls[k] = DataLoader.hf_dsd(dsd[k], collator, sio, coiopts)

        return cls(collator, dls)

