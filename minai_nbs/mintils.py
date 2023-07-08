import time

_timing_scopes = []

def get_timestamp():
    return time.time()

def push_timing_scope():
    _timing_scopes.append(get_timestamp())

def pop_timing_scope():
    return _timing_scopes.pop()

def pop_timing_scope_diff():
    return get_timestamp() - pop_timing_scope()

def pop_and_string_timing_scope(prefix="took ", format="0.3f", suffix="s"):
    return f"{prefix}{pop_timing_scope_diff():{format}}{suffix}"

def pop_and_print_timing_scope(**kwargs):
    print(pop_and_string_timing_scope(**kwargs))


def have_same_conents(fd, contents):
    read = fd.read()
    return read == contents

def overwrite_file(fd, contents):
    fd.seek(0, 0)
    fd.write(contents)
    fd.truncate()
