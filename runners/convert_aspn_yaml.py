import argparse
import re
from glob import glob
from os.path import basename, join, splitext
import yaml
from typing import List, Dict
from site import getsitepackages
from pathlib import Path
from firehose.backends import (
    AspnCBackend,
    AspnCppBackend,
    AspnJsonBackend,
    AspnPyBackend,
    AspnCMarshalingBackend,
    AspnYamlToDDS,
    AspnYamlToLCM,
    AspnYamlToROS,
    AspnYamlToROSTranslations,
    AspnYamlToXMI,
    AspnYamlToLCMTranslations,
    Backend,
)
from firehose.backends.aspn.utils import (
    ASPN_PREFIX,
    CODEGEN_MAPPINGS,
    name_to_enum_field,
    name_to_enum_value,
)


def generate_doc_string(yaml_field, codegen_class, is_enum):
    if codegen_class in ('AspnYamlToLCM', 'AspnYamlToROS') and not is_enum:
        description = yaml_field.get('description', '').strip('\n')
        units = yaml_field.get('units', 'none').strip('\n')
        length = yaml_field.get('length', None)
        docstr = f'Description: {description}\nUnits: {units}'
        if length is not None:
            docstr += f'\nLength: {length}'
        return docstr
    elif codegen_class in ('AspnJsonBackend') and not is_enum:
        description = yaml_field.get('description', '')
        units = yaml_field.get('units', None)
        length = yaml_field.get('length', None)
        docstr = description
        if units is not None:
            docstr += f' Units: {units}'
        if length is not None:
            docstr += f' Length: {length}'
        return docstr
    else:
        return yaml_field.get('description', '')


def process_enum(
    code_gen: Backend, fname: str, enum_fields: List[Dict], doc_str: str
):
    enum_name = name_to_enum_value(code_gen, fname)
    enum_values = []
    val_doc_strs = []
    for key_val in enum_fields:
        for enum_val, docs in key_val.items():
            enum_values.append(
                name_to_enum_field(code_gen, fname, str(enum_val))
            )
            val_doc_strs.append(docs)
    code_gen.process_enum(fname, enum_name, enum_values, doc_str, val_doc_strs)


def process_struct_field(
    code_gen: Backend, field_type: str, field_name: str, doc_str
):
    """
    Process a field in a struct for an ASPN specification field

    Args
        code_gen (Backend): Aspn code generator instance
        field_type (str): ASPN field type
        field_name (str): ASPN field name
    """

    is_simple_field = False

    type_mappings, naming_generator = CODEGEN_MAPPINGS.get(
        code_gen.__class__.__name__, {}
    )

    nullable = False
    if '?' in field_type:
        field_type = field_type.strip().strip('?')
        nullable = True

    # string is special case
    if field_type == "string":
        code_gen.process_string_field(field_name, doc_str)
        return

    # Simplest case- we have a 1-to-1 matching of an
    # ASPN type directly to a C type
    simple_type = type_mappings.get(field_type, None)
    if simple_type is not None:
        code_gen.process_simple_field(
            field_name, simple_type, doc_str, nullable=nullable
        )
        return

    for aspn_t, c_t in type_mappings.items():
        if aspn_t in field_type:
            field_type = field_type.replace(aspn_t, c_t)
            break

    if field_type.startswith('type_'):
        is_simple_field = True
        f_type = field_type
        suffix = ''
        if '[' in field_type:
            i = field_type.index('[')
            f_type = field_type[0:i]
            suffix = field_type[i:]

        field_type = f"{naming_generator(f_type)}{suffix}"

    # Handle matrices.  [N,M] -> [N][M]
    # N and M can be either integers or strings of C variable names
    pattern = r'\[(\w+|\d+),\s*(\w+|\d+)\]$'
    match = re.search(pattern, field_type)
    if match:
        x = match.group(1)
        y = match.group(2)
        try:
            x = int(x)
            y = int(y)
        except ValueError:
            pass
        i = field_type.index("[")
        f_type = field_type[:i]
        if field_name == "covariance" and x == y:
            try:
                data_len = int(x)
            except ValueError:
                doc_str += f" Dimensions of covariance must be {x}²"
        code_gen.process_matrix_field(
            field_name, f_type, x, y, doc_str, nullable=nullable
        )
        return

    # If the type ends in [N] where N is a digit or [some_c_variable_name]
    # Then we will process a data pointer field
    match = re.search(r'\[(\w+|\d+)]$', field_type)
    if match:
        data_len = match.group(1)
        f_type = field_type.rsplit("[", 1)[0]
        try:
            data_len = int(data_len)
        except ValueError:
            pass
        code_gen.process_data_pointer_field(
            field_name, f_type, data_len, doc_str, nullable=nullable
        )
        return

    # If the type is an ASPN type it can be passed but will need further processing
    if is_simple_field:
        code_gen.process_simple_field(
            field_name, field_type, doc_str, nullable=nullable
        )
        return

    # If we have made it this far, it is not being handled properly.
    print(f"Field type {field_type} with name {field_name} not handled!")
    raise NotImplementedError


def gen_struct(code_gen: Backend, yaml_data: dict):
    doc_str = yaml_data.get('description', '<Missing C Docstring>')
    code_gen.process_class_docstring(doc_str)

    for field in yaml_data['fields']:
        fname = field['name'].lower()
        ftype = field.get('type')
        enum_fields = field.get('enum')
        is_enum = enum_fields is not None
        doc_str = generate_doc_string(
            field, code_gen.__class__.__name__, is_enum
        )
        if ftype is None and is_enum:
            process_enum(code_gen, fname, enum_fields, doc_str)
        else:
            process_struct_field(code_gen, ftype, fname, doc_str)


def get_aspn_icd_root() -> str:
    for directory in getsitepackages():
        if (Path(directory) / 'aspn-2023.dist-info').is_dir():
            return directory
    raise Exception(
        f'Could not find ASPN ICD root directory in any of the following directories {getsitepackages()}'
    )


def main():
    ASPN_ICD_DIRS = ["types", "metadata", "measurements", "events"]

    BACKENDS: dict[str, list[Backend]] = {
        'c': AspnCBackend,
        'cpp': AspnCppBackend,
        'dds': AspnYamlToDDS,
        'lcm': AspnYamlToLCM,
        'lcmtranslations': AspnYamlToLCMTranslations,
        'ros': AspnYamlToROS,
        'ros_translations': AspnYamlToROSTranslations,
        'json': AspnJsonBackend,
        'py': AspnPyBackend,
        'xmi': AspnYamlToXMI,
        'marshal_lcm_c': AspnCMarshalingBackend,
    }

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--output_directory",
        required=True,
        type=str,
        default=None,
        help="Path to folder for output files",
    )
    parser.add_argument(
        "-o",
        "--output_format",
        required=True,
        type=str,
        choices=BACKENDS.keys(),
        help="Chose the output format from the available list.",
    )
    parser.add_argument(
        "-e",
        "--extra_icd_dirs",
        action='append',
        help="Extra icd dirs to include",
        default=[],
    )
    parser.add_argument(
        "-m",
        "--metadata_ext",
        action='store_true',
        help="Pass extra metadata to backend",
    )
    args = parser.parse_args()

    backend: Backend = BACKENDS[args.output_format]()

    backend.set_output_root_folder(args.output_directory)

    # Prepend so user specified can override defaults if necessary
    ASPN_ICD_DIRS[:0] = args.extra_icd_dirs
    yaml_files = []
    base_filenames = []

    for directory in ASPN_ICD_DIRS:
        yamls_in_dir = glob(join(get_aspn_icd_root(), directory, '*.yaml'))
        yamls_in_dir.sort()
        # Don't add duplicate types. First in wins.
        for yaml_in_dir in yamls_in_dir:
            base_filename = splitext(basename(yaml_in_dir))
            if base_filename not in base_filenames:
                base_filenames += [base_filename]
                yaml_files += [yaml_in_dir]

    for yaml_path in yaml_files:
        with open(yaml_path) as f:
            yaml_data = yaml.safe_load(f)

            # Add type enum to header so it can be used as a base object.
            if (
                args.output_format in ['c', 'cpp']
                and yaml_data['name'] == 'type_header'
            ):
                type_field = {
                    'name': 'message_type',
                    'type': f'{ASPN_PREFIX}MessageType',
                    'description': 'An enum that specifies which message struct this object can be downcast to.',
                }
                if yaml_data['fields'][0] != type_field:
                    yaml_data['fields'] = [type_field] + yaml_data['fields']
            if isinstance(
                backend, (AspnYamlToLCMTranslations, AspnYamlToROSTranslations)
            ):
                backend.begin_struct(yaml_data['name'], True)
                gen_struct(backend, yaml_data)
                backend.begin_struct(yaml_data['name'], False)
                gen_struct(backend, yaml_data)
                continue

            # Pass extra type metadata to struct
            if args.metadata_ext:
                backend.begin_struct(yaml_data['name'], yaml_data)
                gen_struct(backend, yaml_data)
                continue

            backend.begin_struct(yaml_data['name'])
            gen_struct(backend, yaml_data)

    backend.generate()
    print(
        f"Aspn code generation complete!  Browse files in {args.output_directory}"
    )


if __name__ == "__main__":
    main()
