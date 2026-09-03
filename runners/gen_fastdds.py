import argparse
from glob import glob
from os import listdir, makedirs, pardir, system
from os.path import abspath, isdir, join, relpath
from pathlib import Path
from shutil import rmtree, which
from typing import List, Tuple
from firehose.backends.aspn.utils import ASPN_PREFIX_LOWER, ASPN_VERSION

if which("fastddsgen") is None:
    print(
        "WARNING: You must have the fastddsgen command available on PATH to run this script",
        "This will likely fail shortly.",
    )

CMAKE_MIN_VERSION = "3.8"
FASTCDR_MIN_VERSION = "2.2"
FASTRPS_MIN_VERSION = "2.14"

MESON_BUILD_FILENAME = "meson.build"

PROJECT_NAME = f"{ASPN_PREFIX_LOWER}_dds"
PROJECT_NAMESPACE = f"{ASPN_PREFIX_LOWER}_dds"
VERSION_STR = ASPN_VERSION

TAB = " " * 4


DDS_MESON_TEMPLATE = f"""# See if fastrtps is already installed on the system with cmake
fastrtps_dep = dependency('fastrtps',
    required: false,
    disabler: true,
    method: 'cmake'
)
fastcdr_dep = dependency('fastcdr',
    required: false,
    disabler: true,
    method: 'cmake'
)
if fastrtps_dep.found() and fastcdr_dep.found()
  # Using version: '>={FASTCDR_MIN_VERSION}' in dependency() does not work as the fastrtps version
  # meson compares to does not represent the version installed to the system.
  # Seems to get the version of foonathan_memory instead of fastrtps.
  system_fastrtps_version = fastrtps_dep.get_variable(cmake: 'fastrtps_VERSION',
                                                      default_value: '')
  use_system_fastrtps = system_fastrtps_version.version_compare('>={FASTRPS_MIN_VERSION}')
  if not use_system_fastrtps
    message('Installed fastrtps version needs to be >= {FASTRPS_MIN_VERSION}')
    fastrtps_dep = disabler()
  endif
# If not not on system, try without cmake
# Won't be able to check version, but will respect an overridden dependency
else
    fastrtps_dep = dependency('fastrtps',
        required: false,
        disabler: true,
    )
    fastcdr_dep = dependency('fastcdr',
        required: false,
        disabler: true,
    )
endif
# If it still isn't found, fallback to subproject
if not fastrtps_dep.found() or not fastcdr_dep.found()
  cmake = import('cmake')
  fastdds_cmake_opts = cmake.subproject_options()
  fastdds_cmake_opts.add_cmake_defines({{'THIRDPARTY_fastcdr': 'ON'}})

  fastdds_cmake_subproj = cmake.subproject('fast-dds', options: fastdds_cmake_opts)
  if fastdds_cmake_subproj.found()
    fastrtps_dep = fastdds_cmake_subproj.dependency('fastrtps')
    fastcdr_dep = fastdds_cmake_subproj.dependency('fastcdr')
    meson.override_dependency('fastrtps', fastrtps_dep)
    meson.override_dependency('fastcdr', fastcdr_dep)
  else
    fastrtps_dep = disabler()
    fastcdr_dep = disabler()
  endif
endif

subdir('cpp')
"""


CPP_MESON_TEMPLATE = """lib_files = [
{cxx_files}
]

hxx_files = [
{hxx_files}
]

{project_name} = library(
    '{project_name}',
    lib_files,
    soversion: meson.project_version(),
    include_directories: ['.'],
    cpp_args : '-Wno-non-virtual-dtor', # known error in epros output
    dependencies: [fastrtps_dep, fastcdr_dep],
    install: true
)

{project_name}_dep  = declare_dependency(
    link_with: {project_name},
    include_directories: ['.'],
    dependencies: [fastrtps_dep, fastcdr_dep],
)

meson.override_dependency('{project_name}', {project_name}_dep)

# Install library headers
{project_name}_install_dir = get_option('includedir') / '{project_namespace}'
foreach hxx_file : hxx_files
    install_headers(hxx_file, install_dir: {project_name}_install_dir)
endforeach

# generate pkgconfig
pkg = import('pkgconfig')
pkg.generate({project_name},
  name: '{project_name}',
  description: 'Generated eprosima {project_name} code',
  version: meson.project_version()
)

"""


CMAKELISTS_TEMPLATE = f"""cmake_minimum_required(VERSION {CMAKE_MIN_VERSION})

project({PROJECT_NAME} VERSION {VERSION_STR})
message(STATUS "${{{{PROJECT_NAME}}}} version ${{{{PROJECT_VERSION}}}}")

find_package(fastcdr {FASTCDR_MIN_VERSION} REQUIRED)
find_package(fastrtps {FASTRPS_MIN_VERSION} REQUIRED)

set({PROJECT_NAME}_SOURCES
{{cxx_files}}
)

add_library(${{{{PROJECT_NAME}}}}
  ${{{{{PROJECT_NAME}_SOURCES}}}}
)

target_link_libraries(${{{{PROJECT_NAME}}}}
  PUBLIC
  fastrtps fastcdr
)

# Also set NOMINMAX so the min and max functions are not overwritten with macros.
IF(MSVC)
  add_definitions(-DNOMINMAX -DNOGDI)
ENDIF()

target_compile_features(${{{{PROJECT_NAME}}}} PRIVATE cxx_std_14)

set_property(TARGET ${{{{PROJECT_NAME}}}} PROPERTY POSITION_INDEPENDENT_CODE ON)

if(NOT MSVC)
  target_compile_options(${{{{PROJECT_NAME}}}} PRIVATE -Wall -Wextra -Wpedantic)
endif()

target_include_directories(${{{{PROJECT_NAME}}}}
  PUBLIC
  $<INSTALL_INTERFACE:include/>
  $<BUILD_INTERFACE:${{{{CMAKE_CURRENT_SOURCE_DIR}}}}/>
  PRIVATE
  ${{{{CMAKE_CURRENT_SOURCE_DIR}}}}/
)

# ##############################################################################
# # Install artifacts                                                         ##
# ##############################################################################
install(
  DIRECTORY {PROJECT_NAMESPACE}/
  INCLUDES DESTINATION include/{PROJECT_NAMESPACE}
  FILES_MATCHING PATTERN "*.h"
)

install(
  TARGETS ${{{{PROJECT_NAME}}}}
  EXPORT ${{{{PROJECT_NAME}}}}Targets
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

include(CMakePackageConfigHelpers)
write_basic_package_version_file(
  ${{{{PROJECT_NAME}}}}ConfigVersion.cmake
  COMPATIBILITY AnyNewerVersion
)

export(TARGETS ${{{{PROJECT_NAME}}}} FILE ${{{{PROJECT_NAME}}}}Targets.cmake)

install(EXPORT ${{{{PROJECT_NAME}}}}Targets
  FILE ${{{{PROJECT_NAME}}}}Targets.cmake
  DESTINATION lib/cmake/${{{{PROJECT_NAME}}}}
)

set(PKG_NAME ${{{{PROJECT_NAME}}}})
configure_package_config_file("cmake/${{{{PROJECT_NAME}}}}Config.cmake.in" "${{{{CMAKE_CURRENT_BINARY_DIR}}}}/${{{{PROJECT_NAME}}}}Config.cmake"
  INSTALL_DESTINATION lib/cmake/${{{{PROJECT_NAME}}}}
  PATH_VARS PKG_NAME
  NO_SET_AND_CHECK_MACRO
  NO_CHECK_REQUIRED_COMPONENTS_MACRO)

install(FILES "${{{{CMAKE_CURRENT_BINARY_DIR}}}}/${{{{PROJECT_NAME}}}}Config.cmake"
  "${{{{CMAKE_CURRENT_BINARY_DIR}}}}/${{{{PROJECT_NAME}}}}ConfigVersion.cmake"
  DESTINATION lib/cmake/${{{{PROJECT_NAME}}}}
)
"""

CMAKE_PACKAGE_CONFIG_TEMPLATE = f"""@PACKAGE_INIT@

include(CMakeFindDependencyMacro)
find_dependency(fastcdr)
find_dependency(fastrtps)

if(NOT TARGET {PROJECT_NAME})
    include("${{CMAKE_CURRENT_LIST_DIR}}/@PROJECT_NAME@Targets.cmake")
endif(NOT TARGET {PROJECT_NAME})
"""


def get_cpp_files(cpp_dir: str) -> Tuple[List[str], List[str]]:
    meson_dir = join(cpp_dir, pardir)
    cxx_files = []
    hxx_files = []
    for f in sorted(
        glob(join(cpp_dir, "*")), key=str.casefold
    ):  # sort for output consistency
        if f.endswith(".c") or f.endswith(".cpp") or f.endswith(".cxx"):
            cxx_files.append(relpath(f, meson_dir))
        elif f.endswith(".h") or f.endswith(".hpp") or f.endswith(".hxx"):
            hxx_files.append(relpath(f, meson_dir))
    return cxx_files, hxx_files


def get_root_dds_dir(idl_dir, cpp_dir):
    path1_parts = Path(abspath(idl_dir)).parts
    path2_parts = Path(abspath(cpp_dir)).parts

    shared_parts = []
    for part1, part2 in zip(path1_parts, path2_parts):
        if part1 == part2:
            shared_parts.append(part1)
        else:
            break

    return join(*shared_parts)


def generate_cpp_meson(cpp_dir: str) -> None:
    cxx_files, hxx_files = get_cpp_files(cpp_dir)

    cxx_files = [f"{TAB}'{f}'," for f in cxx_files[:-1]] + [
        f"{TAB}'{cxx_files[-1]}'"
    ]
    hxx_files = [f"{TAB}'{f}'," for f in hxx_files[:-1]] + [
        f"{TAB}'{hxx_files[-1]}'"
    ]

    cxx_files = "\n".join(cxx_files)
    hxx_files = "\n".join(hxx_files)

    cpp_meson = CPP_MESON_TEMPLATE.format(
        cxx_files=cxx_files,
        hxx_files=hxx_files,
        project_name=PROJECT_NAME,
        project_namespace=PROJECT_NAMESPACE,
    )
    with open(join(cpp_dir, pardir, MESON_BUILD_FILENAME), "w") as f:
        f.write(cpp_meson)


def generate_root_meson(aspn_icd_dir: str) -> None:
    with open(join(aspn_icd_dir, MESON_BUILD_FILENAME), "w") as f:
        f.write(DDS_MESON_TEMPLATE)


def generate_cpp_cmakelists(cpp_dir: str) -> None:
    cxx_files, _ = get_cpp_files(cpp_dir)

    cxx_files = f"\n{TAB}".join(cxx_files)
    cxx_files = TAB + cxx_files

    cmakelists = CMAKELISTS_TEMPLATE.format(cxx_files=cxx_files)
    with open(join(cpp_dir, pardir, "CMakeLists.txt"), "w") as f:
        f.write(cmakelists)

    cmake_dir = join(cpp_dir, pardir, "cmake")
    makedirs(cmake_dir, exist_ok=True)
    with open(join(cmake_dir, f"{PROJECT_NAME}Config.cmake.in"), "w") as f:
        f.write(CMAKE_PACKAGE_CONFIG_TEMPLATE)


def generate_cpp(idl_dir: str, cpp_dir: str, extra_args: str) -> None:
    if isdir(cpp_dir) and listdir(cpp_dir):
        rmtree(cpp_dir, ignore_errors=True)
    makedirs(cpp_dir, exist_ok=True)
    cmd = [
        "fastddsgen",
        "-flat-output-dir",
        "-I",
        abspath(join(idl_dir, pardir)),
        "-I",
        abspath(idl_dir),
        "-d",
        abspath(cpp_dir),
    ]
    cmd.extend(extra_args.split())
    cmd.append(join(abspath(idl_dir), "*.idl"))

    system(" ".join(cmd))


def main(idl_dir: str, cpp_dir: str, extra_args: str) -> None:
    root_dds_dir = get_root_dds_dir(idl_dir, cpp_dir)

    # Generate the cxx files from the IDLs
    generate_cpp(idl_dir, cpp_dir, extra_args)

    # Create the root dds meson.build file
    generate_root_meson(root_dds_dir)

    # Create the cxx specific meson.build file
    generate_cpp_meson(cpp_dir)

    # Generate the cxx cmakelists
    generate_cpp_cmakelists(cpp_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--idl_dir",
        help="The root idl directory the idl files live inside of.",
    )
    parser.add_argument(
        "--cpp_dir", help="The output directory for the generated files."
    )
    parser.add_argument(
        "--extra_fastddsgen_args",
        type=str,
        default="",
        help="Extra arguments to pass directly to fastddsgen (enclose in single quotes).",
    )

    args = parser.parse_args()

    main(args.idl_dir, args.cpp_dir, args.extra_fastddsgen_args)
