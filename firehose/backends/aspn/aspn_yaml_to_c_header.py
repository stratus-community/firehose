from os.path import join
from textwrap import dedent
from typing import List, Union
from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    ASPN_NULLABILITY_MACRO_END,
    ASPN_NULLABILITY_MACRO_START,
    ASPN_NULLABLE_MACRO,
    ASPN_PREFIX,
    ASPN_PREFIX_LOWER,
    INDENT,
    format_and_write_to_file,
    format_c_codegen_array,
    format_docstring,
    name_to_struct,
)


class Struct:
    def __init__(self, snake_case_struct_name: str):
        self.constructor_param_buf: List[str] = []
        self.enum_defs_buf: List[str] = []
        self.fn_basename: str = (
            f"{ASPN_PREFIX_LOWER}_{snake_case_struct_name}".lower()
        )
        self.includes: List[str] = []
        self.struct_docstr: str = "<Missing C Docstring>"
        self.struct_fields_buf: List[str] = []
        self.struct_name: str = name_to_struct(snake_case_struct_name)
        self.pointer_fields: List[str] = []
        self.nullability_macro_start: str = ''
        self.nullability_macro_end: str = ''
        self.header_template = dedent(f"""
            /*
             * This code is generated via firehose.
             * DO NOT hand edit code.  Make any changes required using the firehose repo instead
             */

            #pragma once
            #include "common.h"
            {{includes}}
            #ifdef __cplusplus
            extern "C" {{{{
            #endif
            {{nullability_macro_start}}
            {{enum_defs}}

            {{struct_docstr}}
            typedef struct {self.struct_name} {{{{
            {{struct_fields}}
            }}}} {self.struct_name};

            {self.struct_name}* {ASPN_NULLABLE_MACRO} {{fn_basename}}_new({{fn_params}});

            {self.struct_name}* {ASPN_NULLABLE_MACRO} {{fn_basename}}_copy({self.struct_name}*);

            {{free_docstr}}
            void {{fn_basename}}_free(void* pointer);
            void {{fn_basename}}_free_members({self.struct_name}* self);
            {{nullability_macro_end}}
            #ifdef __cplusplus
            }}}}  // extern "C"
            #endif
        """)

        self.free_docstr_no_ptr = dedent(f"""\
            free() all memory held by the given {self.struct_name},
            including the struct itself.
        """)

        self.free_docstr_w_ptrs = dedent(f"""\
            {self.free_docstr_no_ptr}
            Pointer fields ({{pointer_field_str}}) will be freed using
            free() if they are non-NULL. If any of these have been populated
            using non-malloc'd memory, free them manually and set them to
            NULL before calling this function.
        """)


class AspnYamlToCHeader(Backend):
    def __init__(self):
        self.current_struct: Struct = None
        self.structs: List[Struct] = []

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        # Expecting parent AspnCBackend to clear output folder

    def begin_struct(self, snake_case_struct_name):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(snake_case_struct_name)

    def _set_nullability_macro(self):
        self.nullability_macro_start = f"\n{ASPN_NULLABILITY_MACRO_START}\n"
        self.nullability_macro_end = f"\n{ASPN_NULLABILITY_MACRO_END}\n"

    def generate(self) -> str:
        self.structs += [self.current_struct]
        for struct in self.structs:
            free_docstr = struct.free_docstr_no_ptr
            if len(struct.pointer_fields):
                free_docstr = struct.free_docstr_w_ptrs.format(
                    pointer_field_str=', '.join(struct.pointer_fields)
                )

            # TODO- sort the struct params and "new" function params so they match
            # and are in an order that makes sense.

            header_contents = struct.header_template.format(
                enum_defs='\n'.join(struct.enum_defs_buf),
                struct_docstr=format_docstring(
                    struct.struct_docstr, indent=INDENT
                ),
                struct_fields=format_c_codegen_array(struct.struct_fields_buf),
                free_docstr=format_docstring(free_docstr),
                includes='\n'.join(struct.includes),
                fn_basename=struct.fn_basename,
                fn_params=', '.join(struct.constructor_param_buf),
                nullability_macro_start=struct.nullability_macro_start,
                nullability_macro_end=struct.nullability_macro_end,
            )

            basename = struct.struct_name.replace(f"{ASPN_PREFIX}", "")
            h_output_filename = join(self.output_folder, f"{basename}.h")
            format_and_write_to_file(header_contents, h_output_filename)

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
        f_name = field_name
        f_type = type_name
        if isinstance(data_len, int):
            f_name += f"[{data_len}]"
        elif isinstance(data_len, str):
            self.current_struct.pointer_fields.append(field_name)
            if nullable:
                f_type = f"{type_name}* {ASPN_NULLABLE_MACRO}"
                self._set_nullability_macro()
            else:
                f_type = f"{type_name}*"

        docstr = doc_string
        if nullable:
            if isinstance(data_len, str):
                docstr += (
                    '\nNULL indicates this optional field is not provided.'
                )
            else:
                docstr += (
                    '\nAn array of NaNs indicates this optional field is '
                    'not provided.'
                )

        docstr = format_docstring(docstr, indent=INDENT)
        field_str = f"{f_type} {f_name}"

        if type_name.startswith(ASPN_PREFIX):
            ftype = type_name[len(ASPN_PREFIX) :].strip("*")
            self.current_struct.includes.append(f'#include "{ftype}.h"')
        self.current_struct.constructor_param_buf.append(field_str)

        self.current_struct.struct_fields_buf.append(
            f"{docstr}\n{INDENT}{field_str}"
        )

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: int,
        y: int,
        doc_string: str,
        nullable: bool = False,
    ):
        try:
            x = int(x)
        except ValueError:
            pass
        try:
            y = int(y)
        except ValueError:
            pass

        is_pointer = isinstance(x, str) and isinstance(y, str)
        if nullable:
            if is_pointer:
                doc_string += (
                    '\nNULL indicates this optional field is not provided.'
                )
            else:
                doc_string += (
                    '\nA matrix of NaNs indicates this optional field is '
                    'not provided.'
                )
        docstr = format_docstring(doc_string, indent=INDENT)

        field_str = f"{type_name} {field_name}[{x}][{y}]"
        if is_pointer:
            if nullable:
                self._set_nullability_macro()
                field_str = f"{type_name}* {ASPN_NULLABLE_MACRO} {field_name}"
            else:
                field_str = f"{type_name}* {field_name}"
        elif not (isinstance(x, int) and isinstance(y, int)):
            print(
                "Current implementation only supports homogeneous matrix size types."
            )
            print(
                "X and Y must BOTH be ints or BOTH be strings representing pointers)"
            )
            raise NotImplementedError

        self.current_struct.constructor_param_buf.append(field_str)
        self.current_struct.struct_fields_buf.append(
            f"{docstr}\n{INDENT}{field_str}"
        )

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
            field_name, "char*", doc_string, nullable=nullable
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
        docstr = doc_string
        if nullable:
            docstr += '\nNaN indicates this optional field is not provided.'

        docstr = format_docstring(docstr, indent=INDENT)
        field_str = f"{field_type_name} {field_name}"

        if field_type_name.startswith(f"{ASPN_PREFIX}Type"):
            # If one of the fields of the current struct is another ASPN
            # struct, be sure to include its header file.
            ftype = field_type_name[len(ASPN_PREFIX) :].strip("*")
            self.current_struct.includes.append(f'#include "{ftype}.h"')

            self.current_struct.constructor_param_buf.append(
                f'{field_type_name}* {field_name}'
            )
        else:
            self.current_struct.constructor_param_buf.append(field_str)

        self.current_struct.struct_fields_buf.append(
            f"{docstr}\n{INDENT}{field_str}"
        )

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        self.current_struct.struct_docstr = doc_string
        pass

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
        nullable: bool = False,
    ):
        enum_def_str = (
            f"{format_docstring(doc_string)}\nenum {field_type_name} {{\n"
        )
        enum_field_strings = []
        for i, enum_value in enumerate(enum_values):
            val_docstr = format_docstring(
                enum_values_doc_strs[i], indent=INDENT
            )
            enum_field_strings.append(f'{val_docstr}\n{INDENT}{enum_value}')
        enum_def_str += ',\n'.join(enum_field_strings)
        enum_def_str += '\n};'

        self.current_struct.enum_defs_buf.append(enum_def_str)

        param_str = f"enum {field_type_name} {field_name}"

        docstr = format_docstring(doc_string, indent=INDENT)
        self.current_struct.constructor_param_buf.append(param_str)
        self.current_struct.struct_fields_buf.append(
            f"{docstr}\n{INDENT}{param_str}"
        )
