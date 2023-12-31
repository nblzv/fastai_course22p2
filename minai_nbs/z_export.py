def export():
    LIB_NAME = "minai"
    AUTHOR = "nblzv"
    VERSION = "0.1.1"

    # -------------

    from pathlib import Path
    import json
    import subprocess
    import mintils

    mintils.push_timing_scope()
    
    this_file = Path(__file__)
    source_dir = this_file.parent
    print_relative_to = source_dir.parent

    dest_dir = source_dir.parent / LIB_NAME / LIB_NAME; dest_dir.mkdir(exist_ok=True, parents=True)

    for source_file in source_dir.iterdir():
        if source_file == this_file: continue
        if source_file.is_dir(): continue

        mintils.push_timing_scope()

        source_filename = source_file.stem
        source_filesuffix = source_file.suffix

        dest_filename = source_filename.replace("+template", "") + ".py"

        if source_filename.startswith("setup"):
            dest_file = dest_dir.parent / dest_filename
        else:
            dest_file = dest_dir / dest_filename
        
        dest_file.touch()

        source_file_relativeto = source_file.relative_to(print_relative_to)
        dest_file_relativeto = dest_file.relative_to(print_relative_to)

        print(f"Processing {source_file_relativeto} -> {dest_file_relativeto}  |", end="")

        if source_filesuffix == ".ipynb":
            parsed = {}
            with open(source_file, "rt") as fd:
                parsed = json.load(fd)
            
            code = [f"# Autogenerated! Edit {source_file_relativeto} instead\n"]
            exported_count = 0
            for cell in parsed["cells"]:
                if cell["cell_type"] == "code":
                    code_lines = cell["source"]
                    if code_lines and code_lines[0].startswith("#e"):
                        code.append("".join(code_lines[1:]) + "\n")
                        exported_count += 1
            code.append("")
            
            dest_file_temp = dest_file.with_suffix(".temp.py")
            dest_file_temp.unlink(missing_ok=True)

            if len(code) == 2:
                dest_file.unlink(missing_ok=True)
                print(f"  nothing to export, {mintils.pop_string_timing_scope()}")
            else:
                code_joined = "\n".join(code)

                with open(dest_file, "r+t") as fd:
                    if mintils.have_same_conents(fd, code_joined):
                        print(f"  same contents, skipping, {mintils.pop_string_timing_scope()}")

                    else:
                        mintils.overwrite_file(fd, code_joined)
                        print(f"  {exported_count} cells exported, {mintils.pop_string_timing_scope()} ")

        elif source_filesuffix == ".py":
            code_joined = f"# Autogenerated! Edit {source_file_relativeto} instead\n\n"
            with open(source_file, "rt") as fd:
                code_joined += fd.read()

            if source_filename.endswith("+template"):
                code_joined = code_joined.replace("{LIB_NAME}", LIB_NAME).replace("{AUTHOR}", AUTHOR).replace("{VERSION}", VERSION)

            with open(dest_file, "r+t") as fd:
                if mintils.have_same_conents(fd, code_joined):
                    print(f"  same contents, skipping, {mintils.pop_string_timing_scope()}")

                else:
                    print(f"  copied contents, {mintils.pop_string_timing_scope()}")
                    mintils.overwrite_file(fd, code_joined)
        else:
            assert False

    print(f"\nAll done... {mintils.pop_string_timing_scope()}")
    print(f"  lib_name: {LIB_NAME}")
    print(f"  author: {AUTHOR}")
    print(f"  version: {VERSION}")

    if not (dest_dir.parent / f"{LIB_NAME}.egg-info").exists():
        print("\nTo install locally run:")
        print(f"  pip install -e {dest_dir.parent}")

if __name__ == "__main__":
    export()