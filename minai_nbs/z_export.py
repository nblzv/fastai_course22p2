def export():
    lib_name = "minai"
    version = "0.1.0"
    author = "nblzv"

    #------------

    from pathlib import Path
    import json
    import subprocess

    this_file = Path(__file__)
    source_dir = this_file.parent
    dest_dir = source_dir.parent / lib_name / lib_name; dest_dir.mkdir(exist_ok=True, parents=True)

    for source_file in source_dir.iterdir():
        if source_file.name.startswith("_"): continue
        if source_file == this_file: continue
        assert not source_file.is_dir(), "Directories are currently not supported"

        dest_filename = f"{source_file.name[:source_file.name.rindex('.')]}.py"
        dest_file = dest_dir / dest_filename; dest_file.touch()
        print(f"Processing {source_file.name} -> {dest_file}")

        parsed = {}
        with open(source_file, "rt") as fd:
            parsed = json.load(fd)
        
        code = []
        exported_count = 0
        for cell in parsed["cells"]:
            if cell["cell_type"] == "code":
                src = cell["source"]
                if src and src[0].startswith("#") and "e" in src[0]:
                    code.append("".join(src[1:]))
                    exported_count += 1

        if not exported_count:
            print(f"  no cells to export")
            continue

        code.append("")
        code_joined = "\n".join(code)
        with open(dest_file, "r+t") as fd:
            contents = fd.read()

            if contents == code_joined:
                print(f"  same contents, skipping")

            else:
                loc = len(code_joined.split("\n"))
                print(f"  exporting {exported_count} cells, {loc} loc")

                dest_file_temp = dest_file.with_suffix(".temp.py")
                with open(dest_file_temp, "wt") as tfd:
                    tfd.write(code_joined)
                
                res = subprocess.run(["python", dest_file_temp], capture_output=True, text=True)
                dest_file_temp.unlink()
                if res.returncode or res.stdout or res.stderr:
                    print(res.stderr)
                    print("Problem during file export, exiting")
                    print(f"stdout: {bool(res.stdout)}, stderr: {bool(res.stderr)}, returncode: {res.returncode}")
                    quit(-1)

                fd.seek(0, 0)
                fd.write(code_joined)
                fd.truncate()

    init_file = dest_dir / "__init__.py"; init_file.touch()
    init_file_source = f'__version__ = "{version}"\n'
    with open(init_file, "rt+") as fd:
        fd.write(init_file_source)
        fd.truncate()

    setup_py_file = dest_dir.parent / "setup.py"; setup_py_file.touch()
    setup_py_file_source = f"""\
    from setuptools import setup, find_packages

    setup(
        name="{lib_name}",
        author="{author}",
        version="{version}",
        packages=find_packages()
    )
    """

    print(f"Creating setup.py -> {setup_py_file}")
    print(f"  lib_name: {lib_name}")
    print(f"  author: {author}")
    print(f"  version: {version}")
    with open(setup_py_file, "rt+") as fd:
        fd.write(setup_py_file_source)
        fd.truncate()

    print("\nAll good!")
    if not (dest_dir.parent / f"{lib_name}.egg-info").exists():
        print("To install locally run:")
        print(f"  pip install -e {dest_dir.parent}")

if __name__ == "__main__":
    export()