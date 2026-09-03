from glob import glob
from os import makedirs, remove
from os.path import join
from shutil import rmtree
from typing import List, Union
import re

import numpy as np

from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    ASPN_PREFIX_LOWER,
    INDENT,
    char_limit_docstr,
    format_and_write_py_file,
    format_docstring,
    is_length_field,
    pascal_to_snake,
    snake_to_pascal,
)

ASPN_MODULE = ASPN_PREFIX_LOWER


class Struct:
    def __init__(self, pascal_struct_name: str):
        self.enum_classes_buf: List[str] = []
        self.aspn_imports: List[str] = []
        self.class_docstring: str = "<Missing class docstring!>"
        self.attr_docstr_buf: List[str] = []
        self.class_fields_buf: List[str] = []
        self.struct_name: str = pascal_struct_name
        self.pointer_fields: List[str] = []

        inherit = ""
        if not pascal_struct_name.startswith("Type"):
            self.aspn_imports.append("from .aspn_base import AspnBase")
            inherit = "(AspnBase)"

        self.template = f'''
"""
This code is generated via firehose.
DO NOT hand edit code.  Make any changes required using the firehose repo instead.
"""

from enum import Enum
from dataclasses import dataclass
from typing import List
from typing import Optional
from numpy.typing import NDArray
import numpy as np

{{aspn_imports}}

{{enum_classes}}

@dataclass
class {self.struct_name}{inherit}:
{INDENT}"""
{INDENT}{{class_docstr}}

{INDENT}### Attributes
{{attr_docstr}}
{INDENT}"""

{{class_fields}}
'''


class AspnYamlToPython(Backend):
    current_struct: Struct | None = None
    structs: List[Struct] = []

    def _remove_existing_output_files(self):
        rmtree(self.output_folder, ignore_errors=True)

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = join(output_root_folder, 'src', ASPN_PREFIX_LOWER)
        self._remove_existing_output_files()
        makedirs(self.output_folder, exist_ok=True)

    def begin_struct(self, struct_name: str):
        self.struct_name = struct_name
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(f"{snake_to_pascal(struct_name)}")

    def _add_attribute_docstring(
        self, field_name, typehint, docstring, limit=100, nullable=False
    ):
        if self.current_struct is None:
            return
        type = typehint if not nullable else f"Optional[{typehint}]"
        lines = [f"\n{INDENT}{field_name} - {type}:"]
        current_line = f"{INDENT}"
        words = docstring.split()

        char_limit = limit - (len(INDENT) * 3)
        for word in words:
            if len(current_line) + len(word) <= char_limit:
                current_line += word + " "
            else:
                lines.append(f"{INDENT * 3}{current_line.strip()}")
                current_line = word + " "

        if current_line:
            lines.append(f"{INDENT * 3}{current_line.strip()}")

        self.current_struct.attr_docstr_buf.append("\n".join(lines))

    def _generate_aspn_base_class(self):
        print("Generating aspn_base.py")
        template = '''
"""
This code is generated via firehose.
DO NOT hand edit code.  Make any changes required using the firehose repo instead.
"""

from typing import Protocol

class AspnBase(Protocol):
    pass
'''
        format_and_write_py_file(
            template, join(self.output_folder, "aspn_base.py")
        )

    def generate(self):
        if self.current_struct is not None:
            self.structs += [self.current_struct]

        output_init_filename = join(self.output_folder, "__init__.py")

        def format_struct_exports(struct: Struct):
            """
            returns either an empty string or a comma followed by the extra
            enum exports for a struct.
            """
            enum_names = []
            for enum in struct.enum_classes_buf:
                searched = re.search(r"class (.*)\(Enum\):", enum)
                if searched is None:
                    continue

                name = searched.group(1)
                enum_names.append(name)
            # if there are no extra imports...
            if len(enum_names) == 0:
                return ""
            joined_enum_names = ''
            for name in enum_names:
                joined_enum_names += f', {name} as {name}'
            return joined_enum_names

        init_exports = '# Follow Python export conventions:\n'
        init_exports += '# https://typing.readthedocs.io/en/latest/spec/distributing.html#import-conventions\n'
        init_exports += 'from .aspn_base import AspnBase as AspnBase\n'
        init_exports += "\n".join(
            [
                f"from .{pascal_to_snake(it.struct_name)} import {it.struct_name} as {it.struct_name}{format_struct_exports(it)}"
                for it in self.structs
            ]
        )
        format_and_write_py_file(init_exports, output_init_filename)

        for struct in self.structs:
            file_contents = struct.template.format(
                enum_classes="\n".join(struct.enum_classes_buf),
                class_docstr=struct.class_docstring,
                attr_docstr="\n".join(struct.attr_docstr_buf),
                class_fields="\n".join((struct.class_fields_buf)),
                aspn_imports="\n".join(struct.aspn_imports),
            )

            filename = pascal_to_snake(struct.struct_name)
            output_filename = join(self.output_folder, f"{filename}.py")
            output_init_filename = join(self.output_folder, "__init__.py")
            format_and_write_py_file(file_contents, output_filename)

        self._generate_aspn_base_class()

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # Backend Methods # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def process_func_ptr_field_with_self(
        self,
        field_name: str,
        params,
        return_t,
        doc_string: str,
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_data_pointer_field(
        self,
        field_name: str,
        type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return

        typehint = f"List[{type_name}]"
        if isinstance(data_len, int) or type_name in ["float", "int"]:
            typehint = f"NDArray[np.{np.dtype(type_name).type.__name__}]"
        if nullable:
            typehint = f"Optional[{typehint}]"
        field_str = f"{field_name}: {typehint}"

        if type_name.startswith("Type"):
            filepath = pascal_to_snake(type_name)
            self.current_struct.aspn_imports.append(
                f"from .{filepath} import {type_name}"
            )

        self._add_attribute_docstring(
            field_name, typehint, doc_string, nullable=nullable
        )
        self.current_struct.class_fields_buf.append(f"{INDENT}{field_str}")

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: int | str,
        y: int | str,
        doc_string: str,
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return
        typehint = f"NDArray[np.{np.dtype(type_name).type.__name__}]"
        if nullable:
            typehint = f"Optional[{typehint}]"
        field_str = f"{field_name}: {typehint}"

        self._add_attribute_docstring(
            field_name, typehint, doc_string, nullable=nullable
        )
        self.current_struct.class_fields_buf.append(f"{INDENT}{field_str}")

    def process_outer_managed_pointer_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_outer_managed_pointer_array_field(
        self,
        field_name: str,
        field_type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_string_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        self.process_simple_field(
            field_name, "str", doc_string, nullable=nullable
        )

    def process_string_array_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        raise NotImplementedError

    def process_simple_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return
        if is_length_field(field_name):
            return
        typehint = field_type_name
        if nullable:
            typehint = f"Optional[{typehint}]"
        field_str = f"{field_name}: {typehint}"

        if field_type_name.startswith("Type"):
            ftype = field_type_name[:]
            filepath = pascal_to_snake(ftype)
            self.current_struct.aspn_imports.append(
                f"from .{filepath} import {field_type_name}"
            )

        self._add_attribute_docstring(
            field_name, typehint, doc_string, nullable=nullable
        )
        self.current_struct.class_fields_buf.append(f"{INDENT}{field_str}")

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        if self.current_struct is None:
            return
        self.current_struct.class_docstring = char_limit_docstr(
            doc_string, indent=INDENT, prefix=""
        )

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_enum(
        self,
        field_name: str,
        field_type_name: str,
        enum_values: List[str],
        doc_string: str,
        enum_values_doc_strs: List[str],
    ):
        if self.current_struct is None:
            return
        enum_docstr = format_docstring(
            doc_string, indent=INDENT, style='"""', char_limit=100
        )

        self.current_struct.enum_classes_buf.append(
            f"class {field_type_name}(Enum):"
        )
        self.current_struct.enum_classes_buf.append(f"{INDENT}{enum_docstr}")

        for i, enum_key in enumerate(enum_values):
            enum_val = i
            enum_name = enum_key
            enum_split = enum_key.split("=")
            if len(enum_split) == 2:
                enum_name = enum_split[0].strip()
                enum_val = int(enum_split[1].strip())
            ev_docstr = format_docstring(
                enum_values_doc_strs[i],
                indent=INDENT,
                style='"""',
                char_limit=100,
            )

            self.current_struct.enum_classes_buf.append(
                f"{ev_docstr}{INDENT}{enum_name} = {enum_val}"
            )

        self._add_attribute_docstring(field_name, field_type_name, doc_string)
        self.current_struct.class_fields_buf.append(
            f"{INDENT}{field_name}: {field_type_name}"
        )
