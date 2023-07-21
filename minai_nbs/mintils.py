import time

_timing_scopes = []
def get_timestamp():
    return time.perf_counter_ns()

def push_timing_scope():
    _timing_scopes.append(get_timestamp())

def pop_timing_scope():
    return _timing_scopes.pop()

def pop_diff_timing_scope():
    return (get_timestamp() - pop_timing_scope()) / 1e9

def pop_string_timing_scope(prefix="took ", format="0.3f", suffix="s"):
    return f"{prefix}{pop_diff_timing_scope():{format}}{suffix}"

def pop_print_timing_scope(prefix="took ", format="0.3f", suffix="s"):
    print(pop_string_timing_scope(prefix, format, suffix))

class timing_scope:
    def __enter__(self):
        push_timing_scope()
    
    def __exit__(self, *args):
        pop_print_timing_scope()


def have_same_conents(fd, contents):
    read = fd.read()
    return read == contents

def overwrite_file(fd, contents):
    fd.seek(0, 0)
    fd.write(contents)
    fd.truncate()
