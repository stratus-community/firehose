#!/usr/bin/env python3

import argparse
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List
from glob import glob
from os.path import join
import inspect
from importlib import import_module

from firehose.backends.aspn.utils import ASPN_PREFIX_LOWER

FIREMAN = r"""

                                     █████████
                                 █████████   ███
                               ██████████ ███████
                              █████ █████ ████  ██
                             ██ ██   ████  ███  ███  █████                                           ████
                            ██  ██    ████    ██████████                                            ███
                            ██  ███    █████████████                                          ██
                            ██   ██  ███████      ███                                      ████
                            ██  ███████           ███                                  █████
                          ██████████         ██   ███                               █████              ██████
                       ██████ ██  ███             ███                            ████          ████
                               ██  ███           ███                          ████      █████████         █████
                                ███  ██         ██                    ███  ████    ███████                 ██
                                █████ ███    █████                ████████     █████
                               ███  ███████████  ███             ███    ██    █
                             ███                   ███       ███████    ███    █████████████████████    ██   ████
                            ███            ██       ███████████   ███    ███                                   █
                            ██                   █████████   █████████ █████ ████████████
                            ██     ████████████████   ██      ████  █████             ████████████
                            ██      ████ ███  ███    ████     ██                                ███     ██
                            ███       ██  ██  ████████ ████████                                        ████
                             ███      ███ ██████   ███   ████
                              ████     ███████      ███████                              ██
                            ███████████████████    ███                                   ███
                          ███    ██████████   ████████
                        ██    █████     ██    ███  ███
                      ███  █████  ████████████████████                                    ███
                     ██   ███ ██                    ██                             █     █████
                    ██  ███   ██           ███      ██                            ███   ███  ██     ██
                    ██  ██    ██                    ██                                  ██    ██    ██
                   ██  ██     ████████████████████████                                 ██     ███
                   ██  ██      ██                  ██                                  ██      ███
                   ██ ███      ██         █        ██                               ██ ██        ████
                   ██ ███      ██         ██       ██                              ██  ██         █████
                   ██  ██      ██         ██       ██                             ███        █       ███
                   ███ ███     ██         ██       ██                             ██        ████      ██
                    ██  ██     ██         ██       ██                             ██       ██  ██      ██
                     ██  ███   ██████████████████████                             ██    ████    ██     ██
                      ███ ████ ██         ██       ██                             ███   ███     ███    ██
                       ███   █████████████████████████████████████████             ██    █       ██   ██
                         █████ ████████████████████████          ███ ██             ███              ██
                            █████         ██       █████████████ ██  ██              ████         ████
                        ██    ███         ██       ███████████████████████████████████████████████████████████████████████
                       ███████████        ██       ███████████████████████████████████████████████████████████████████  ██
                               ██████████████████████
                                                              ██                                               ██

 __/\\\\\\\\\\\\\\\___/\\\\\\\\\\\_____/\\\\\\\\\_______/\\\\\\\\\\\\\\\___/\\\________/\\\________/\\\\\___________/\\\\\\\\\\\_____/\\\\\\\\\\\\\\\_
 _\/\\\///////////___\/////\\\///____/\\\///////\\\____\/\\\///////////___\/\\\_______\/\\\______/\\\///\\\_______/\\\/////////\\\__\/\\\///////////__
  _\/\\\__________________\/\\\______\/\\\_____\/\\\____\/\\\______________\/\\\_______\/\\\____/\\\/__\///\\\____\//\\\______\///___\/\\\_____________
   _\/\\\\\\\\\\\__________\/\\\______\/\\\\\\\\\\\/_____\/\\\\\\\\\\\______\/\\\\\\\\\\\\\\\___/\\\______\//\\\____\////\\\__________\/\\\\\\\\\\\_____
    _\/\\\///////___________\/\\\______\/\\\//////\\\_____\/\\\///////_______\/\\\/////////\\\__\/\\\_______\/\\\_______\////\\\_______\/\\\///////______
     _\/\\\__________________\/\\\______\/\\\____\//\\\____\/\\\______________\/\\\_______\/\\\__\//\\\______/\\\___________\////\\\____\/\\\_____________
      _\/\\\__________________\/\\\______\/\\\_____\//\\\___\/\\\______________\/\\\_______\/\\\___\///\\\__/\\\______/\\\______\//\\\___\/\\\_____________
       _\/\\\_______________/\\\\\\\\\\\__\/\\\______\//\\\__\/\\\\\\\\\\\\\\\__\/\\\_______\/\\\_____\///\\\\\/______\///\\\\\\\\\\\/____\/\\\\\\\\\\\\\\\_
        _\///_______________\///////////___\///________\///___\///////////////___\///________\///________\/////__________\///////////______\///////////////__


"""

# Default directory paths
FIREHOSE_ROOT = os.path.abspath(os.path.dirname(__file__))
DEFAULT_STAGING_INPUT_DIR = join(FIREHOSE_ROOT, "staging")
DEFAULT_OUTPUT_DIR = join(FIREHOSE_ROOT, "output")

# Runners
ASPN_CODEGEN_RUNNER = join(FIREHOSE_ROOT, "runners", "convert_aspn_yaml.py")
FASTDDS_RUNNER = join(FIREHOSE_ROOT, "runners", "gen_fastdds.py")

# Add some PYTHONPATH entries necessary for the runners to work
os.environ["PYTHONPATH"] = os.pathsep.join(
    [FIREHOSE_ROOT, os.environ.get("PYTHONPATH", "")]
)


class FirehoseArgParse(argparse.ArgumentParser):
    def print_help(self, *args, **kwargs):
        print(FIREMAN)
        super().print_help(*args, **kwargs)


class FirehoseTarget:
    def __init__(
        self,
        name,
        runner,
        cmd_args,
        dependencies=None,
        post_run=None,
        post_run_args=[],
    ):
        self.name = name
        self.runner = runner
        self.cmd_args = cmd_args  # List of command arguments
        self.dependencies = dependencies or []
        self.post_run = post_run
        self.post_run_args = post_run_args or []

    @property
    def cmd(self):
        return [sys.executable, self.runner] + self.cmd_args

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


def delete_directory_contents(directory):
    """
    Deletes all contents of the specified directory.

    Parameters:
    - directory (str): The directory whose contents are to be deleted.
    """
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        except Exception as e:
            print(f"Failed to delete '{item_path}': {e}")
            sys.exit(1)


def clean_output_directory(output_dir: str) -> None:
    """
    Checks if the given directory is the root of a Git repository.

    - If not, deletes all contents of the directory.
    - If it is, checks if the working directory is clean (porcelain).
      - If clean, continues.
      - If not, exits with an error message.

    Parameters:
    - output_dir (str): The path to the directory to check.
    """
    # Expand user tilde and get absolute path
    output_dir = os.path.abspath(os.path.expanduser(output_dir))

    if not os.path.isdir(output_dir):
        print(f"The directory '{output_dir}' does not exist.")
        sys.exit(1)

    # Change to the target directory
    original_dir = os.getcwd()
    os.chdir(output_dir)

    try:
        # Check if it's inside a Git repository
        is_inside_git_repo = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if is_inside_git_repo.returncode != 0:
            # Not inside a Git repository; delete all contents
            print(
                f"'{output_dir}' is not inside a Git repository. Deleting all contents."
            )
            delete_directory_contents(output_dir)
            return
        else:
            # Get the top-level directory of the Git repository
            git_toplevel = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if git_toplevel.returncode != 0:
                print(
                    f"Error determining Git repository root: {git_toplevel.stderr}"
                )
                sys.exit(1)

            git_root = git_toplevel.stdout.strip()

            if git_root != output_dir:
                # The directory is a subdirectory within a Git repository; delete contents
                print(
                    f"'{output_dir}' is not the root of the Git repository. Deleting all contents."
                )
                delete_directory_contents(output_dir)
                return
            else:
                # The directory is the root of a Git repository; check if it's clean
                git_status = subprocess.run(
                    ['git', 'status', '--porcelain'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                if git_status.returncode != 0:
                    print(f"Error checking Git status: {git_status.stderr}")
                    sys.exit(1)

                if git_status.stdout.strip() == '':
                    # Working directory is clean
                    print("Git repository is clean. Continuing.")
                    return
                else:
                    # Working directory has uncommitted changes
                    print(
                        "Error: Git repository has uncommitted changes. Please commit or stash them before proceeding."
                    )
                    sys.exit(1)
    finally:
        # Return to the original directory
        os.chdir(original_dir)


def configure_extra_icds(
    aspn_icd_dir: str, extra_icd_files_dir: str | None
) -> None:
    """
    Adds any additional YAML files from extra_icd_files_dir to aspn_icd_dir.
    """

    # Define the lookup dictionary for file prefixes and target folders
    prefix_to_folder = {
        "measurement_": "measurements",
        "metadata_": "metadata",
        "type_": "types",
    }

    # Create the temporary directory structure
    if extra_icd_files_dir is not None:
        if extra_icd_files_dir:
            for file_path in glob(
                join(extra_icd_files_dir, '**', '*.yaml'), recursive=True
            ):
                file_name = os.path.basename(file_path)
                for prefix, folder in prefix_to_folder.items():
                    if file_name.startswith(prefix):
                        dst_dir = join(aspn_icd_dir, folder)
                        print(
                            f"Copying custom extension file '{file_path}' to '{dst_dir}'"
                        )
                        shutil.copy(file_path, dst_dir)
                        break
                else:
                    print(
                        f"Error: Unknown file type for {file_name}. File was not copied."
                    )


def collect_all_targets(targets_to_generate, targets_list):
    all_targets = {}
    visited = set()

    def visit(target):
        if target.name in visited:
            return
        visited.add(target.name)
        for dep_name in target.dependencies:
            if dep_name not in targets_list:
                raise ValueError(
                    f"Dependency '{dep_name}' for target '{target.name}' not found."
                )
            dep_target = targets_list[dep_name]
            visit(dep_target)
        all_targets[target.name] = target

    for target in targets_to_generate:
        visit(target)

    return all_targets


def topological_sort_levels(targets):
    """
    Performs a topological sort and returns a list of levels.
    Each level contains targets that can be run in parallel.
    """
    from collections import defaultdict, deque

    # Build adjacency list and in-degree count
    adj = defaultdict(list)  # target_name -> list of dependent target names
    in_degree = defaultdict(int)  # target_name -> number of dependencies

    for target in targets.values():
        in_degree[target.name] = len(target.dependencies)
        for dep in target.dependencies:
            adj[dep].append(target.name)

    # Initialize queue with targets that have in-degree zero
    zero_in_degree = deque(
        [name for name, deg in in_degree.items() if deg == 0]
    )

    levels = []  # List of levels, each level is a list of target names

    while zero_in_degree:
        level = []
        for _ in range(len(zero_in_degree)):
            target_name = zero_in_degree.popleft()
            level.append(target_name)
            for dependent in adj[target_name]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    zero_in_degree.append(dependent)
        levels.append(level)

    if any(deg > 0 for deg in in_degree.values()):
        raise ValueError("Cyclic dependencies detected among targets.")

    return levels  # List of levels, each level is a list of target names


def generate_target(target: FirehoseTarget):
    print(f"Running target: {target.name}")
    subprocess.check_call(target.cmd)

    if target.post_run:
        if target.post_run_args:
            target.post_run(*target.post_run_args)
        else:
            target.post_run()


def run_generation_targets(targets_to_generate, all_targets):
    """
    Runs code generation targets, respecting dependencies and running in parallel where possible.
    """
    # Collect all targets including dependencies
    all_targets_dict = collect_all_targets(targets_to_generate, all_targets)

    # Perform topological sort to get levels
    levels = topological_sort_levels(all_targets_dict)
    for level in levels:
        # level is a list of target names
        targets_in_level = [all_targets_dict[name] for name in level]
        print(f"Running targets in parallel: {[name for name in level]}")

        max_processes = min(len(levels), 2 * multiprocessing.cpu_count())
        pool = multiprocessing.Pool(processes=max_processes)
        pool.map(generate_target, targets_in_level)
        pool.close()
        pool.join()


def run_lcm_gen(output_dir: str) -> None:
    """
    Runs the LCM code generation commands.
    This must only be run AFTER the LCM ICD files have been generated.
    """
    output_paths: Dict[str, str] = {
        "python": join(output_dir, "lcm", "python"),
        "java": join(output_dir, "lcm", "java"),
        "cpp": join(output_dir, "lcm", "cpp"),
        "c": join(output_dir, "lcm", "c"),
    }
    lcm_files = sorted(
        glob(f"{output_dir}/aspn-lcm/*.lcm"), key=str.casefold
    )  # sort for output consistency

    # Run the subprocess with the expanded list of files
    subprocess.run(
        ['lcm-gen', "-p", *lcm_files, "--ppath", output_paths["python"]],
        check=True,
    )

    subprocess.run(
        ['lcm-gen', "-j", *lcm_files, "--jpath", output_paths["java"]],
        check=True,
    )
    subprocess.run(
        ['lcm-gen', "-x", *lcm_files, "--cpp-hpath", output_paths["cpp"]],
        check=True,
    )

    os.makedirs(join(output_paths["c"], "src"), exist_ok=True)
    os.makedirs(join(output_paths["c"], "include"), exist_ok=True)
    subprocess.run(
        [
            'lcm-gen',
            "-c",
            *lcm_files,
            "--c-cpath",
            join(output_paths["c"], "src"),
            "--c-hpath",
            join(output_paths["c"], "include"),
        ],
        check=True,
    )


from site import getsitepackages
from pathlib import Path


def _get_path_to_lcm_jar() -> str:
    for directory in getsitepackages():
        candidate = Path(directory) / 'share' / 'java' / 'lcm.jar'
        if (candidate).exists():
            return candidate.as_posix()
    raise Exception(
        f'Could not find lcm.jar root directory in any of the following directories {getsitepackages()}'
    )


def _build_lcm_jar(lcm_staging_dir: str) -> None:
    """
    Builds the LCM JAR file using Gradle.
    """
    cwd = os.getcwd()
    try:
        os.chdir(lcm_staging_dir)
        env = os.environ.copy()
        env['LCM_JAR_PATH'] = _get_path_to_lcm_jar()
        subprocess.run(["gradle"], check=True, env=env)
        subprocess.run(["gradle", "compileJava"], check=True, env=env)
        subprocess.run(["gradle", "jar"], check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"Error building LCM JAR: {e}")
        raise e
    finally:
        # Make sure we are changing directory back to the original one
        os.chdir(cwd)


def _write_fingerprints(classes, struct_type: str, file) -> None:
    file.write('| name | fingerprint | \n')
    file.write('| ---- | ----------- | \n')
    for name, aspn_class in classes:
        if name.startswith(struct_type):
            file.write(f'| {name} | {aspn_class().get_hash()} |\n')


def _generate_lcm_fingerprint_table(output_dir: str) -> None:
    sys.path.append(output_dir)
    aspn_lcm = import_module(f'{ASPN_PREFIX_LOWER}_lcm')

    classes = inspect.getmembers(aspn_lcm, inspect.isclass)
    with open(join(output_dir, 'fingerprints.md'), 'w') as file:
        file.write('# ASPN-LCM (Python) Fingerprints\n')
        file.write('\n## Measurements\n\n')
        _write_fingerprints(classes, 'measurement', file)
        file.write('\n## Metadata\n\n')
        _write_fingerprints(classes, 'metadata', file)
        file.write('\n## Types\n\n')
        _write_fingerprints(classes, 'type', file)


def _generate_legacy_submodule(lcm_python_output: str) -> None:
    """
    Clones a specific revision of the aspn-generated repository and uses it to create a submodule
    containing previous major release of LCM Python.
    """
    git_url = 'https://github.com/stratus-community/stratus-aspn-generated.git'
    git_revision = '9d0eecc9a841e5fc3dd9a9abe601054d37e6bbba'
    dest_path = join(lcm_python_output, 'aspn23_lcm', 'legacy')

    print(
        f'Creating legacy ASPN-LCM Python submodule from {git_url} at revision {git_revision}...'
    )

    # Create a temporary directory for cloning
    with tempfile.TemporaryDirectory() as tmpdir:
        # Clone the repository with shallow clone
        subprocess.run(
            ['git', 'clone', '--depth', '1', git_url, tmpdir],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Fetch the specific revision
        subprocess.run(
            [
                'git',
                '-C',
                tmpdir,
                'fetch',
                '--depth',
                '1',
                'origin',
                git_revision,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Checkout the specific revision
        subprocess.run(
            ['git', '-C', tmpdir, 'checkout', git_revision],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Copy the contents of the source directory to the destination
        source_dir = join(tmpdir, 'lcm/python/aspn23_lcm')
        if not os.path.exists(source_dir):
            raise FileNotFoundError(
                f'Source directory {source_dir} not found in cloned repository'
            )

        # Create destination directory if it doesn't exist
        os.makedirs(dest_path, exist_ok=True)

        # Copy all files from source to destination
        for item in os.listdir(source_dir):
            src_item = join(source_dir, item)
            dst_item = join(dest_path, item)
            if os.path.isdir(src_item):
                shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
            else:
                shutil.copy2(src_item, dst_item)

    # Add legacy submodule to main __init__.py
    init_file_path = join(lcm_python_output, 'aspn23_lcm', '__init__.py')
    with open(init_file_path, 'a') as f:
        f.write('\nfrom . import legacy\n')


# Generate the LCM code after the aspn lcm files are generated
def post_aspn_lcm(output_dir: str, staging_dir: str) -> None:
    # Run the lcm codegen
    run_lcm_gen(output_dir)

    lcm_output = join(output_dir, "lcm")

    # Build the LCM JAR and then clean up
    _build_lcm_jar(f"{staging_dir}/lcm")
    shutil.rmtree(join(lcm_output, "gradle"), ignore_errors=True)
    shutil.rmtree(join(staging_dir, "lcm", ".gradle"), ignore_errors=True)

    # Generate table of fingerprints
    lcm_python_output = join(lcm_output, "python")
    _generate_lcm_fingerprint_table(lcm_python_output)

    # Add legacy submodule
    _generate_legacy_submodule(lcm_python_output)


def stage_files(staging_input_dir: str, output_dir: str) -> None:
    """
    Stages non-generated files into the output directory.
    """
    shutil.copytree(staging_input_dir, output_dir, dirs_exist_ok=True)


def print_targets_status(
    targets: List[FirehoseTarget],
    selected_targets: List[FirehoseTarget],
    skipped_targets: List[FirehoseTarget],
):
    sys.stdout.write("\033[H\033[J")  # Clears the terminal screen
    sys.stdout.write("Target list:\n")
    for target in targets:
        if target in selected_targets:
            sys.stdout.write(
                f"\033[92m{target}\033[0m\n"
            )  # Green for selected
        elif target in skipped_targets:
            sys.stdout.write(f"\033[91m{target}\033[0m\n")  # Red for skipped
        else:
            sys.stdout.write(f"{target}\n")  # Default color for unselected
    sys.stdout.flush()


def prompt_for_targets(targets: List[FirehoseTarget]) -> List[FirehoseTarget]:
    """
    Prompts the user to select which targets to generate, showing the full list of targets
    and recoloring them based on selection.
    """
    selected_targets = []
    skipped_targets = []

    for target in targets:
        while True:
            print_targets_status(targets, selected_targets, skipped_targets)
            choice = (
                input(
                    f"\nDo you want to generate {target}? [y/n] (default=yes): "
                )
                .strip()
                .lower()
            )
            if choice.startswith("y") or choice == "":
                selected_targets.append(target)
                break
            elif choice in ["n", "no"]:
                skipped_targets.append(target)
                break
            else:
                print("Please enter 'y' or 'n'.")

    # Final display of selections
    print_targets_status(targets, selected_targets, skipped_targets)

    return [targets[t] for t in selected_targets]


def get_args() -> argparse.Namespace:
    def normalized_path(path: str) -> str:
        """
        Normalizes a path (including ~ expansion).
        """
        return os.path.abspath(os.path.expanduser(path))

    def normalized_and_created_path(path: str) -> str:
        """
        Normalizes a path and creates it if it does not exist.
        """
        normal_path = normalized_path(path)
        os.makedirs(normal_path, exist_ok=True)
        return normal_path

    def normalized_and_checked_path(path: str) -> str:
        """
        Normalizes a path (including ~ expansion) and optionally creates it if it does not exist.
        """
        normal_path = normalized_path(path)
        if not os.path.exists(path):
            print(f"Path {path} does not exist!")
            sys.exit(1)
        return normal_path

    parser = FirehoseArgParse(
        description=(
            "Convenience script for generating code from ASPN ICD files and "
            "optionally staging the output for use in aspn-generated"
        )
    )

    parser.add_argument(
        "--aspn-icd-dir",
        metavar="",
        help=("Directory containing input Aspn YAML files for generation."),
        type=normalized_path,
    )
    parser.add_argument(
        "--extra-icd-files-dir",
        default=None,
        metavar="",
        help=(
            "Directory containing any additional input Aspn YAML files for "
            "generation. Defaults to None"
        ),
        type=normalized_and_checked_path,
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        metavar="",
        help=(
            "Directory to place generated output files. Defaults to "
            f"{DEFAULT_OUTPUT_DIR}"
        ),
        type=normalized_and_created_path,
    )
    parser.add_argument(
        "-s",
        "--staging-input-dir",
        default=DEFAULT_STAGING_INPUT_DIR,
        metavar="",
        help=(
            "Staging directory containing any additional non-generated files to "
            f"push to aspn-generated. Defaults to {DEFAULT_STAGING_INPUT_DIR}"
        ),
        type=normalized_and_created_path,
    )
    parser.add_argument(
        "-a", "--all", action="store_true", help="Generate all output formats"
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="Show a list of all available targets to generate",
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        metavar="",
        help=(
            "List of specific targets to generate. Alternatively use "
            "--interactive to select one by one"
        ),
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode to select output formats",
    )

    return parser.parse_args()


def create_targets(args: argparse.Namespace) -> dict[str, FirehoseTarget]:
    # Now define the targets
    targets = [
        FirehoseTarget(
            name="aspn_c",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=["-d", join(args.output_dir, "aspn-c"), "-o", "c"],
        ),
        FirehoseTarget(
            name="aspn_cpp",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=["-d", join(args.output_dir, "aspn-cpp"), "-o", "cpp"],
        ),
        FirehoseTarget(
            name="aspn_lcm",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=["-d", join(args.output_dir, "aspn-lcm"), "-o", "lcm"],
            post_run=post_aspn_lcm,
            post_run_args=[args.output_dir, args.staging_input_dir],
        ),
        FirehoseTarget(
            name="aspn_dds_idl",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=[
                "-d",
                join(
                    args.output_dir, "dds", "idl", f"{ASPN_PREFIX_LOWER}_dds"
                ),
                "-o",
                "dds",
            ],
        ),
        FirehoseTarget(
            name="aspn_lcm_translations",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=[
                "-d",
                join(
                    args.output_dir,
                    f"{ASPN_PREFIX_LOWER}_lcm_conversions",
                    f"{ASPN_PREFIX_LOWER}_lcm_conversions",
                ),
                "-o",
                "lcmtranslations",
            ],
        ),
        FirehoseTarget(
            name="aspn_json",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=[
                "-d",
                join(args.output_dir, "aspn-json"),
                "-o",
                "json",
                "-m",
            ],
        ),
        FirehoseTarget(
            name="aspn_py",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=["-d", join(args.output_dir, "aspn-py"), "-o", "py"],
        ),
        FirehoseTarget(
            name="aspn_dds_cpp",
            runner=FASTDDS_RUNNER,
            cmd_args=[
                "--idl_dir",
                join(
                    args.output_dir, "dds", "idl", f"{ASPN_PREFIX_LOWER}_dds"
                ),
                "--cpp_dir",
                join(
                    args.output_dir, "dds", "cpp", f"{ASPN_PREFIX_LOWER}_dds"
                ),
            ],
            dependencies=["aspn_dds_idl"],
        ),
        FirehoseTarget(
            name="aspn_ros",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=[
                "-d",
                join(
                    args.output_dir,
                    "aspn-ros",
                    "src",
                    f"{ASPN_PREFIX_LOWER}_ros_interfaces",
                ),
                "-o",
                "ros",
            ],
        ),
        FirehoseTarget(
            name="aspn_ros_translations",
            runner=ASPN_CODEGEN_RUNNER,
            cmd_args=[
                "-d",
                join(
                    args.output_dir,
                    "aspn-ros",
                    "src",
                    f"{ASPN_PREFIX_LOWER}_ros_utils",
                    f"{ASPN_PREFIX_LOWER}_ros_utils",
                ),
                "-o",
                "ros_translations",
            ],
            dependencies=["aspn_ros"],
        ),
    ]

    # Create a mapping from target names to FirehoseTarget instances
    return {target.name: target for target in targets}


def main() -> None:
    """
    Main entrypoint to run the code generation and build process.
    """
    args = get_args()
    all_targets = create_targets(args)

    targets_to_generate = []

    if args.list_targets:
        print("Available targets:")
        for name in all_targets.keys():
            print(f"  {name}")
        return

    if args.all:
        targets_to_generate = list(all_targets.values())
    elif not args.interactive and args.targets:
        # Map the selected target names back to FirehoseTarget instances
        for name in args.targets:
            if name not in all_targets:
                print(f"Unknown target: {name}")
                print(f"Must be one of: {list(all_targets.keys())}")
                sys.exit(1)
            targets_to_generate.append(all_targets[name])
    else:
        # Default to all targets if none specified
        targets_to_generate = prompt_for_targets(all_targets)

    clean_output_directory(args.output_dir)

    configure_extra_icds(args.aspn_icd_dir, args.extra_icd_files_dir)

    run_generation_targets(targets_to_generate, all_targets)

    print("Staging files...")
    stage_files(args.staging_input_dir, args.output_dir)


if __name__ == "__main__":
    main()
