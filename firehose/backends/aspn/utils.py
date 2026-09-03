import re
from textwrap import dedent
from subprocess import check_call, PIPE, run
from enum import Enum
from os.path import splitext
from typing import List

ASPN_VERSION = '23'
ASPN_PREFIX_UNVERSIONED = "Aspn"
ASPN_PREFIX_UNVERSIONED_UPPER = ASPN_PREFIX_UNVERSIONED.upper()
ASPN_PREFIX_UNVERSIONED_LOWER = ASPN_PREFIX_UNVERSIONED.lower()
ASPN_PREFIX = ASPN_PREFIX_UNVERSIONED + ASPN_VERSION
ASPN_PREFIX_LOWER = ASPN_PREFIX_UNVERSIONED_LOWER + ASPN_VERSION
ASPN_PREFIX_UPPER = ASPN_PREFIX_UNVERSIONED_UPPER + ASPN_VERSION
ASPN_NULLABILITY_MACRO_START = 'ASPN_ASSUME_NONNULL_BEGIN'
ASPN_NULLABILITY_MACRO_END = 'ASPN_ASSUME_NONNULL_END'
ASPN_NULLABLE_MACRO = 'ASPN_NULLABLE'
ASPN_DISABLE_NULLABILITY = 'ASPN_DISABLE_NULLABILITY'
C_MULTILINE_TEMPLATE = dedent('''
    {indent}/**
    {indent} * {docstr}
    {indent} */
    ''')
PY_MULTILINE_TEMPLATE = dedent('''
    {indent}"""
    {indent}{docstr}
    {indent}"""
    ''')
PREFIX_MAP = {'//': '// ', '#': '# ', '/**': ' * ', '"""': ''}
INDENT = 4 * " "
JSON_INDENT = 2 * " "

# Mappings of ASPN specification types to C types
ASPN_TO_C_MAPPINGS = {
    'bool': 'bool',
    'float32': 'float',
    'float64': 'double',
    'uint8': 'uint8_t',
    'uint16': 'uint16_t',
    'uint32': 'uint32_t',
    'uint64': 'uint64_t',
    'int8': 'int8_t',
    'int16': 'int16_t',
    'int32': 'int32_t',
    'int64': 'int64_t',
    f'{ASPN_PREFIX}MessageType': f'{ASPN_PREFIX}MessageType',
}

# Eprosima DDS type mappings
ASPN_TO_DDS_MAPPINGS = {
    'bool': 'boolean',
    'float32': 'float',
    'float64': 'double',
    'uint8': 'uint8',
    'uint16': 'uint16',
    'uint32': 'uint32',
    'uint64': 'uint64',
    'int8': 'int8',
    'int16': 'int16',
    'int32': 'int32',
    'int64': 'int64',
}

# Mappings of ASPN specification types to JSON types  # TODO: add value limits
ASPN_TO_JSON_MAPPINGS = {
    'bool': 'boolean',
    'float32': 'number',
    'float64': 'number',
    'uint8': 'integer',
    'uint16': 'integer',
    'uint32': 'integer',
    'uint64': 'integer',
    'int8': 'integer',
    'int16': 'integer',
    'int32': 'integer',
    'int64': 'integer',
}

# Mappings of ASPN specification types to LCM IDL types
ASPN_TO_LCM_MAPPINGS = {
    'bool': 'boolean',
    'float32': 'float',
    'float64': 'double',
    'uint8': 'int16_t',
    'uint16': 'int32_t',
    'uint32': 'int64_t',
    'uint64': 'int64_t',
    'int8': 'int8_t',
    'int16': 'int16_t',
    'int32': 'int32_t',
    'int64': 'int64_t',
}

# Using numpy types
ASPN_TO_PYTHON_MAPPINGS = {
    'bool': 'bool',
    'float32': 'float',
    'float64': 'float',
    'uint8': 'int',
    'uint16': 'int',
    'uint32': 'int',
    'uint64': 'int',
    'int8': 'int',
    'int16': 'int',
    'int32': 'int',
    'int64': 'int',
}

# Mappings of ASPN specification types to ROS msg datatypes
ASPN_TO_ROS_MAPPINGS = {
    'bool': 'bool',
    'float32': 'float32',
    'float64': 'float64',
    'uint8': 'uint8',
    'uint16': 'uint16',
    'uint32': 'uint32',
    'uint64': 'uint64',
    'int8': 'int8',
    'int16': 'int16',
    'int32': 'int32',
    'int64': 'int64',
}

# Lookup mappings for each backend:
# (type_mappings, Struct/Class name)
CODEGEN_MAPPINGS = {
    'AspnCBackend': (
        ASPN_TO_C_MAPPINGS,
        lambda x: f'{ASPN_PREFIX}{snake_to_pascal(x)}',
    ),
    'AspnCppBackend': (
        ASPN_TO_C_MAPPINGS,
        lambda x: f'{ASPN_PREFIX}{snake_to_pascal(x)}',
    ),
    'AspnCMarshalingBackend': (
        ASPN_TO_C_MAPPINGS,
        lambda x: f'{ASPN_PREFIX}{snake_to_pascal(x)}',
    ),
    'AspnYamlToLCM': (ASPN_TO_LCM_MAPPINGS, lambda x: x),
    'AspnYamlToLCMTranslations': (
        ASPN_TO_PYTHON_MAPPINGS,
        lambda x: snake_to_pascal(x),
    ),
    'AspnYamlToROS': (ASPN_TO_ROS_MAPPINGS, lambda x: snake_to_pascal(x)),
    'AspnYamlToROSTranslations': (
        ASPN_TO_PYTHON_MAPPINGS,
        lambda x: snake_to_pascal(x),
    ),
    'AspnYamlToDDS': (ASPN_TO_DDS_MAPPINGS, lambda x: snake_to_pascal(x)),
    'AspnYamlToPython': (
        ASPN_TO_PYTHON_MAPPINGS,
        lambda x: snake_to_pascal(x),
    ),
    'AspnJsonBackend': (ASPN_TO_JSON_MAPPINGS, lambda x: x),
}

MatrixType = Enum(
    'MatrixType', ['XTENSOR', 'XTENSOR_PY', 'EIGEN', 'STL', 'NONE']
)


def is_length_field(field_name: str) -> bool:
    # Starts with "num_"
    if len(field_name) > 3 and field_name[0:4] == 'num_':
        # Special case: num_signal_types is an independent field
        if field_name in ['num_signal_types']:
            return False
        return True

    # Custom list of known length field names
    if field_name in ['image_data_length', 'descriptor_size']:
        return True

    # If it doesn't fall into any of the above categories,
    # it's not a length field
    return False


def char_limit_docstr(
    string: str, indent: str = "", limit: int = 100, prefix='*'
) -> str:
    lines = []
    current_line = f"{indent}"
    words = string.split()

    for word in words:
        if len(current_line) + len(word) <= limit:
            current_line += word + " "
        else:
            lines.append(current_line.strip())
            current_line = word + " "

    if current_line:
        lines.append(current_line.strip())

    return f"\n{indent}{prefix}".join(lines)


def format_docstring(
    string: str, indent: str = '', char_limit: int = 100, style='/**'
) -> str:
    prefix = PREFIX_MAP[style]
    # Wrap each long line, but preserve original newlines
    docstr = f'\n{indent}{prefix}'.join(
        char_limit_docstr(line, indent, char_limit, prefix)
        for line in string.splitlines()
    )
    # Simple double slash or pound prefixed comment style
    if style in ('//', '#'):
        return f'{indent}{prefix}' + docstr
    # C/C++/javascript/etc multiline comment
    elif style == '/**':
        return C_MULTILINE_TEMPLATE.format(indent=indent, docstr=docstr)
    # Python triple quote multi-line comment
    elif style == '"""':
        return PY_MULTILINE_TEMPLATE.format(indent=indent, docstr=docstr)
    return ''


def name_to_enum_field(
    codegen_instance, enum_name: str, enum_field: str
) -> str:
    struct_name = None
    if hasattr(codegen_instance, 'current_struct'):
        struct_name = codegen_instance.current_struct.struct_name
    else:
        struct_name = codegen_instance.struct_name

    if codegen_instance.__class__.__name__ in ['AspnYamlToLCM']:
        return f'{enum_name}_{enum_field}'.upper()
    elif codegen_instance.__class__.__name__ in [
        'AspnYamlToPython',
        'AspnJsonBackend',
    ]:
        return enum_field.upper()
    else:
        # Right now struct names should always already be in snake case.
        # This check for an underscore seems like it's not very bulletproof in confirming
        # snake case, but I'm not sure of downsides yet.  Maybe just be wary here for Backends
        # that land here and don't have special cases.  I think I am going to make a separate
        # MR that that fixes this issue
        if '_' not in struct_name:
            struct_name = f"{pascal_to_snake(struct_name, True)}"
        return f"{ASPN_PREFIX_UPPER}_{struct_name}_{enum_name}_{enum_field}".upper()


def name_to_enum_value(codegen_instance, enum_name: str) -> str:
    if codegen_instance.__class__.__name__ in [
        'AspnYamlToLCM',
        'AspnYamlToLCMTranslations',
        'AspnYamlToROS',
        'AspnYamlToROSTranslations',
    ]:
        return enum_name
    elif codegen_instance.__class__.__name__ in ['AspnYamlToDDS']:
        return (
            f"{codegen_instance.struct_name}{snake_to_pascal(enum_name)}Value"
        )
    elif codegen_instance.__class__.__name__ in ['AspnJsonBackend']:
        return snake_to_camel(enum_name)
    else:
        pascal_enum = snake_to_pascal(enum_name)
        struct_name = codegen_instance.struct_name
        if hasattr(codegen_instance, 'current_struct'):
            struct_name = codegen_instance.current_struct.struct_name
        add_aspn_prefix = codegen_instance.__class__.__name__ not in [
            'AspnYamlToPython'
        ]
        pascal_struct_name = name_to_struct(
            codegen_instance.struct_name, add_aspn_prefix
        )
        struct_name = snake_to_pascal(struct_name)
        return f"{pascal_struct_name}{pascal_enum}"


def name_to_struct(str_name: str, insert_aspn_prefix: bool = True) -> str:
    if insert_aspn_prefix:
        return f"{ASPN_PREFIX}{snake_to_pascal(str_name)}"
    else:
        return snake_to_pascal(str_name)


def pascal_to_snake(str_name: str, screaming: bool = False) -> str:
    out = re.sub(r'(?<!^)(?=[A-Z])', '_', str_name).lower()

    cases = {
        'imu': 'IMU',
        'tdoa1_tx2_rx': 'TDOA_1Tx_2Rx',
        'tdoa2_tx1_rx': 'TDOA_2Tx_1Rx',
        'beidou': 'BeiDou',
        'galileo': 'Galileo',
        'glonass': 'GLONASS',
        'gps': 'GPS',
        'cnav': 'Cnav',
        'lnav': 'Lnav',
        'mnav': 'Mnav',
        '1_d': '_1d',
        '2_d': '_2d',
        '3_d': '_3d',
    }

    for key, value in cases.items():
        if key in out:
            out = out.replace(key, value)

    return out.upper() if screaming else out


def snake_to_pascal(snake_string: str) -> str:
    """
    Accepts a string in snake_case and converts it to PascalCase.
    For example:
    'measurement_imu' will return 'MeasurementImu'
    'measurement_TDOA_1Tx_2Rx' will return 'MeasurementTdoa1Tx2Rx'
    'measurement_direction_of_motion_3d' will return
    'MeasurementDirectionOfMotion3D'
    'measurement_direction_2d_to_points' will return
    'MeasurementDirection2DToPoints'
    """

    out = []
    snake_string = snake_string.capitalize()
    raise_next = True
    for char in snake_string:
        if char == '_':
            raise_next = True
        elif raise_next and char.isalpha():
            out += char.upper()
            raise_next = False
        else:
            out += char
    return ''.join(out)


def camel_to_snake(str_name: str, screaming: bool = False) -> str:
    """
    Accepts a string in camelCase and converts it to snake_case.
    For example:
    'measurementImu' will return 'measurement_imu'
    'measurementTdoa1Tx2Rx' will return 'measurement_TDOA_1Tx_2Rx'
    'measurementDirectionOfMotion3D' will return
    'measurement_direction_of_motion_3d'
    'measurementDirection2DToPoints' will return
    'measurement_direction_2d_to_points'
    """

    if str_name:
        return pascal_to_snake(str_name[0].upper() + str_name[1:], screaming)
    else:
        return str_name


def snake_to_camel(snake_string: str) -> str:
    """
    Accepts a string in snake_case and converts it to camelCase.
    For example:
    'measurement_imu' will return 'measurementImu'
    'measurement_TDOA_1Tx_2Rx' will return 'measurementTdoa1Tx2Rx'
    'measurement_direction_of_motion_3d' will return
    'measurementDirectionOfMotion3D'
    'measurement_direction_2d_to_points' will return
    'measurementDirection2DToPoints'
    """

    out = snake_to_pascal(snake_string)

    if out:
        out = out[0].lower() + out[1:]

    return out


def clang_format_file_contents(file_content, output_path):
    CLANG_FORMAT = dedent("""
    {AccessModifierOffset: -4,
    AlignConsecutiveAssignments: true,
    AlignTrailingComments: true,
    AllowShortFunctionsOnASingleLine: All,
    AllowShortIfStatementsOnASingleLine: true,
    BasedOnStyle: Google,
    BinPackArguments: false,
    BinPackParameters: false,
    BreakBeforeBraces: Custom,
    ColumnLimit: 100,
    DerivePointerAlignment: false,
    IncludeBlocks: Preserve,
    IndentCaseLabels: false,
    IndentPPDirectives: AfterHash,
    IndentWidth: 4,
    KeepEmptyLinesAtTheStartOfBlocks: true,
    Language: Cpp,
    MaxEmptyLinesToKeep: 1,
    PointerAlignment: Left,
    SortIncludes: false,
    TabWidth: 4,
    UseTab: ForIndentation}
    """).strip().replace(",\n", ", ")
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(file_content)
    try:
        cmd = ['clang-format', '-i', f'--style={CLANG_FORMAT}', '--files='] + [
            output_path
        ]
        check_call(cmd)

    except Exception as ex:
        print(f"\nCaught the following exception:\n{ex}\n")
        print(f'\tWhen running this command:\n{" ".join(cmd)}')


def format_and_write_dds_file(file_content, out_path):
    formatted_idl_content = []
    brace_level = 0
    for line in file_content.splitlines():
        # Format indentation level for each line
        opening_braces = line.count('{')
        closing_braces = line.count('}')
        if opening_braces > 0:
            brace_level += 1
            indent = INDENT * (brace_level - 1)
        elif closing_braces > 0:
            indent = INDENT * (brace_level - 1)
            brace_level -= 1
        else:
            indent = INDENT * brace_level
        if brace_level < 0:
            raise Exception(f"Unexpected '}}' encountered, {out_path}")
        formatted_line = indent + line.lstrip()

        # No consecutive empty lines
        if len(formatted_idl_content) > 1:
            if formatted_idl_content[-1].lstrip() == "":
                if formatted_line.lstrip() == "":
                    continue

        formatted_idl_content.append(formatted_line)

    if brace_level != 0:
        raise Exception(f"Unexpected '{{' encountered, {out_path}")

    # Write file
    with open(out_path, "a", encoding="utf-8") as f:
        for line in formatted_idl_content:
            f.write(line + "\n")


def format_and_write_xmi_file(file_content, out_path):
    # TODO- actually fill in the body of this formatter here for the XMI
    print("WARNING: No formatter written for XMI yet, please implement me!")
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(file_content)


def format_and_write_py_file(file_content, out_path):
    LINE_LENGTH = 88

    code = file_content
    # Manually remove unused imports here.
    if 'np.' not in code:
        code = code.replace('import numpy as np', '')

    if 'List[' not in code:
        code = code.replace('from typing import List', '')

    if '(Enum)' not in code:
        code = code.replace('from enum import Enum', '')

    formatted_code = code

    try:
        # Format code using Black's API
        import black

        formatted_code = black.format_str(
            src_contents=code,
            mode=black.FileMode(
                target_versions={black.TargetVersion.PY311},
                line_length=LINE_LENGTH,
                magic_trailing_comma=False,
            ),
        )
    except ImportError:
        print("Unable to find formatting dependency 'black', skipping!")
    except Exception as e:
        print("Error while formatting with 'black'.  Skipping formatting")
        print(e)

    try:
        import isort
        from isort.settings import Config

        # Sort imports using isort's API
        formatted_code = isort.code(
            formatted_code,
            config=Config(line_length=LINE_LENGTH, profile="black"),
        )
    except ImportError:
        print("Unable to find formatting dependency 'isort', skipping!")
    except Exception as e:
        print(f"isort formatting failed: {e}")
        # You can decide whether to proceed or fallback
        pass

    # Write the formatted code to the output file
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(formatted_code)


def format_and_write_json_file(file_content, out_path):
    content = file_content
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(content)


def format_json_string(string_to_format: str):
    output = string_to_format.replace("\n", " ")
    output = output.replace("\"", "'")
    output = '\"' + output + '\"'
    output = output.replace(' \"', '\"')
    return output


def create_json_prop(name: str, pairs: dict, indent_level: int = 0) -> str:
    """
    Creates json property structure from nested dictionary structure. A blank
    name field creates empty braces around the contained properties.
    """
    output = []
    content = []
    if name == "":
        output.append(f"{indent_level*JSON_INDENT}{{\n")
    else:
        output.append(f"{indent_level*JSON_INDENT}{name}: {{\n")
    for key, val in pairs.items():
        if type(val) is dict:
            content.append(create_json_prop(key, val, indent_level + 1))
        elif type(val) is list:
            array_content = []
            for item in val:
                array_content.append(
                    create_json_prop("", item, indent_level + 2)
                )
            content.append(
                f"{(indent_level+1)*JSON_INDENT}{key}: [\n"
                + ",\n".join(array_content)
                + f"\n{(indent_level+1)*JSON_INDENT}]"
            )
        else:
            content.append(f"{(indent_level+1)*JSON_INDENT}{key}: {val}")

    output.append(",\n".join(content))
    output.append(f"\n{indent_level*JSON_INDENT}}}")
    return "".join(output)


def _get_line_indent(line):
    indent_len = next(
        (i for i, char in enumerate(line) if not char.isspace()), None
    )
    return ' ' * indent_len if indent_len > 0 else ''


def write_file(file_content, out_path):
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(file_content)


def format_and_write_to_file(file_content, out_path):
    """
    Switch case for which file formatter to use based on file extension
    """
    CLANG_GANG = {'.h', '.c', '.hpp', '.cpp'}

    _, file_extension = splitext(out_path)

    if file_extension in CLANG_GANG:
        clang_format_file_contents(file_content, out_path)
    elif file_extension == '.idl':
        format_and_write_dds_file(file_content, out_path)
    elif file_extension == '.xmi':
        format_and_write_xmi_file(file_content, out_path)
    elif file_extension == '.py':
        format_and_write_py_file(file_content, out_path)
    else:  # other file extensions, like LCM, don't require formatting
        write_file(file_content, out_path)


def format_c_codegen_array(lines):
    """
    Takes an input array presumed to be lines of C code.
    Adds a semicolon at the end of each line, accounting for inline-comments.
    Adds a newline after each item in the array as well
    """
    output = ''
    for line in lines:
        if ' /* ' in line and line.endswith('*/'):
            code_and_comment = line.split(' /* ')
            if len(code_and_comment) == 2:
                code, comment = code_and_comment
            else:
                raise Exception("Unexpected '*/' in code!")
            output += f'{code};  /* {comment.strip()}\n'
        else:
            output += f'{line};\n'
    return output
