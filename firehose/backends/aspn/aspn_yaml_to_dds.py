from glob import glob
from os import makedirs, remove
from os.path import join
from typing import List, Union
from firehose.backends import Backend

from firehose.backends.aspn.utils import (
    ASPN_PREFIX_LOWER,
    ASPN_PREFIX_UPPER,
    format_and_write_dds_file,
    snake_to_pascal,
)

PLACEHOLDER = f"{ASPN_PREFIX_UPPER}_PLACEHOLDER"


class Struct:
    def __init__(self, pascal_struct_name: str):
        self.constructor_param_buf: List[str] = []
        self.doc_str: str = ""
        self.enums: str = ""
        self.includes: List[str] = []
        self.struct_fields: List[str] = []
        self.struct_name: str = pascal_struct_name
        self.template = f"""
// This code is generated via firehose.
// DO NOT hand edit code.  Make any changes required using the firehose repo instead

#ifndef {f"__{ASPN_PREFIX_LOWER}_DDS_{self.struct_name.strip('_')}__".upper()}
#define {f"__{ASPN_PREFIX_LOWER}_DDS_{self.struct_name.strip('_')}__".upper()}

{{includes}}

module {ASPN_PREFIX_LOWER}_dds {{{{
{{enums}}
@topic
struct {self.struct_name} {{{{
{{struct_fields}}
}}}};
}}}};

#endif
"""
        self.enum_template = f"""
enum {{enum_name}} {{{{
{{enum_fields}}
}}}};
"""


class AspnYamlToDDS(Backend):
    current_struct: Struct = None
    structs: List[Struct] = []
    output_folder = None

    @property
    def struct_name(self):
        return (
            self.current_struct.struct_name
            if self.current_struct is not None
            else None
        )

    def _remove_existing_output_files(self):
        if self.output_folder is not None:
            for file in glob(f"{self.output_folder}/*.idl"):
                remove(file)

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        makedirs(self.output_folder, exist_ok=True)
        self._remove_existing_output_files()

    def begin_struct(self, snake_case_struct_name):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(
            f"{snake_to_pascal(snake_case_struct_name)}"
        )

    def generate(self) -> str:
        self.structs += [self.current_struct]
        # Ensure unique and sorted values
        for struct in self.structs:
            struct_includes = sorted(list(set(struct.includes)))
            file_contents = struct.template.format(
                includes="\n".join(struct_includes),
                enums=struct.enums,
                struct_fields="\n".join(struct.struct_fields),
            )

            output_filename = join(
                self.output_folder, f"{struct.struct_name}.idl"
            )
            format_and_write_dds_file(file_contents, output_filename)

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # # Backend Methods # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def process_func_ptr_field_with_self(
        self, field_name: str, params, return_t, doc_string: str, nullable=None
    ):
        raise NotImplementedError

    def process_data_pointer_field(
        self,
        field_name: str,
        type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable=None,
    ):
        # This check for isupper() is to see if this is a primitive type or an imported one.
        # This is NOT a robust way of doing this I doubt, and needs revisited.
        prefix = ""
        if type_name[0].isupper() and not type_name.startswith(
            self.current_struct.struct_name
        ):
            self.current_struct.includes.append(
                f"#include <{ASPN_PREFIX_LOWER}_dds/{type_name}.idl>"
            )
            prefix = f"{ASPN_PREFIX_LOWER}_dds::"

        optional_str = "@optional " if nullable else ""
        field_str = f"{optional_str}sequence<{prefix}{type_name}> {field_name}"
        try:
            int(data_len)
            field_str = f"{optional_str}{type_name} {field_name}[{data_len}]"
        except ValueError:
            pass
        self.current_struct.struct_fields.append(f"{field_str};")

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: int,
        y: int,
        doc_string: str,
        nullable=None,
    ):
        self.process_data_pointer_field(
            field_name, type_name, "", doc_string, nullable=nullable
        )

    def process_outer_managed_pointer_field(
        self, field_name: str, field_type_name: str, doc_string: str
    ):
        raise NotImplementedError

    def process_outer_managed_pointer_array_field(
        self,
        field_name: str,
        field_type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable=None,
    ):
        raise NotImplementedError

    def process_string_field(
        self, field_name: str, doc_string: str, nullable=None
    ):
        self.process_simple_field(
            field_name, "string", doc_string, nullable=nullable
        )

    def process_string_array_field(
        self, field_name: str, doc_string: str, nullable=None
    ):
        raise NotImplementedError

    def process_simple_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable=None,
    ):
        ftype = field_type_name
        optional_str = "@optional " if nullable else ""

        if field_type_name[0].isupper() and not field_type_name.startswith(
            self.current_struct.struct_name
        ):
            self.current_struct.includes.append(
                f"#include <{ASPN_PREFIX_LOWER}_dds/{field_type_name}.idl>"
            )
            ftype = f"{ASPN_PREFIX_LOWER}_dds::{field_type_name}"

        self.current_struct.struct_fields.append(
            f"{optional_str}{ftype} {field_name};"
        )

    def process_class_docstring(self, doc_string: str, nullable=None):
        self.current_struct.doc_str = doc_string
        pass

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable=None,
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
        self.current_struct.enums += f"enum {field_type_name} {{\n"
        total_enums = len(enum_values)
        for i, enum_val in enumerate(enum_values):
            # This will generally just return enum_val, but occasionally
            # There is an enum key with the value set in it in the YAML.
            enum_prefix = ""
            split_val = enum_val.split("=")
            e_val = split_val[0].strip(' ')
            if len(split_val) > 1:
                e_at_val = split_val[1].strip(' ')
                enum_prefix = f"@value({e_at_val}) "
            self.current_struct.enums += f"{enum_prefix}{e_val}"
            if i < (total_enums - 1):
                self.current_struct.enums += ",\n"
        # eProsima DDS gen doesn't work with an empty enum so needed to put something here
        if total_enums == 0:
            self.current_struct.enums += f"{PLACEHOLDER}"
        self.current_struct.enums += "\n};\n"

        self.current_struct.struct_fields.append(
            f"{field_type_name} {field_name};"
        )
