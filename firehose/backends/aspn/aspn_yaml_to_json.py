from glob import glob
from os import makedirs, remove
from os.path import join
from typing import List, Union
import re

from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    JSON_INDENT as INDENT,
    create_json_prop,
    format_and_write_json_file,
    format_json_string,
    snake_to_camel,
)

# This URL is used simply as an identifier - it does not have to be where the file is located
ID_URL = (
    "https://github.com/stratus-community/stratus-aspn-generated/tree/main"
)
SCHEMA_URL = "https://json-schema.org/draft/2020-12/schema"


class Schema:
    metadata: dict | None
    metadata_header: str

    def __init__(self, snake_case_struct_name: str, yaml_data: dict = None):
        self.properties_buf: List[str] = []
        self.required_list: List[str] = []
        self.snake_struct_name = snake_case_struct_name
        self.struct_name = snake_to_camel(snake_case_struct_name)

        if yaml_data:  # TODO yaml.safe_load() gives "no" values as boolean
            exclude = [
                'name',
                'fields',
            ]  # "title" JSON schema annotation used instead of "name"
            self.metadata = {
                k: v for k, v in yaml_data.items() if k not in exclude
            }
            self.metadata_header = "\n" + self._process_metadata()
        else:
            self.metadata_header = ""

        self.template = f'''{{{{
{INDENT}"$comment": "This file is generated via firehose. DO NOT edit by hand. Make any changes required using the firehose repo instead.",
{INDENT}"$schema": "{SCHEMA_URL}",
{INDENT}"$id": "{ID_URL}/{{subdir}}/{self.snake_struct_name}.json",
{INDENT}"title": "{self.struct_name}",{self.metadata_header}
{INDENT}"type": "object",
{INDENT}"properties": {{{{
{{properties}}
{INDENT}}}}},
{{required}}
}}}}
'''

    def _process_metadata(self) -> str:
        output = []
        for k, v in self.metadata.items():
            if type(v) is str:
                outstr = format_json_string(v)
            elif type(v) is bool:
                outstr = "true" if v else "false"
            else:
                outstr = v
            output.append(f'{INDENT}"{snake_to_camel(k)}": {outstr},')
        return "\n".join(output)


class AspnYamlToJson(Backend):
    current_struct: Schema | None = None
    structs: List[Schema] = []
    output_folder = None

    def _remove_existing_output_files(self):
        if self.output_folder is not None:
            for file in glob(f"{self.output_folder}/*.json"):
                remove(file)

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = join(output_root_folder, 'schemas')
        makedirs(self.output_folder, exist_ok=True)
        self._remove_existing_output_files

    def _get_relative_path(self) -> str:
        split = re.split(
            r'(?=aspn-json)', self.output_folder, maxsplit=1
        )  # path must include aspn-json
        return split[1]

    def _create_nullable_type(self, type: str, nullable: bool) -> str:
        """
        Takes a JSON formatted type and returns it, creating an array if nullable
        """
        if nullable:
            output = f"[{type}, {format_json_string('null')}]"
        else:
            output = type
        return output

    def begin_struct(
        self, snake_case_struct_name: str, yaml_data: dict = None
    ):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Schema(snake_case_struct_name, yaml_data)

    def generate(self):
        print(self.output_folder)
        self.structs += [self.current_struct]

        for struct in self.structs:
            file_contents = struct.template.format(
                properties=",\n".join(struct.properties_buf),
                subdir=self._get_relative_path(),
                required=f"{INDENT}{format_json_string('required')}: [ {', '.join(struct.required_list)} ]",
            )

            filename = struct.snake_struct_name
            output_filename = join(self.output_folder, f"{filename}.json")
            format_and_write_json_file(file_contents, output_filename)

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
        dp_name = format_json_string(snake_to_camel(field_name))
        dp_docstr = format_json_string(
            f"{field_name}: " + doc_string
        )  # TODO add more formatting for multiline docstrings
        dp_props = dict()
        dp_props[format_json_string("description")] = dp_docstr
        dp_props[format_json_string("type")] = self._create_nullable_type(
            format_json_string("array"), nullable
        )

        is_static_dimension = type(data_len) is int
        if is_static_dimension:
            dp_props[format_json_string("minItems")] = data_len
            dp_props[format_json_string("maxItems")] = data_len

        dp_items = dict()

        if type_name.startswith("type"):
            dp_items[format_json_string("$ref")] = format_json_string(
                f"{type_name}.json"
            )
        else:
            dp_items[format_json_string("type")] = format_json_string(
                type_name
            )

        dp_props[format_json_string("items")] = dp_items

        self.current_struct.properties_buf.append(
            create_json_prop(dp_name, dp_props, indent_level=2)
        )
        self.current_struct.required_list.append(dp_name)

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: Union[str, int],
        y: Union[str, int],
        doc_string: str,
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return

        matrix_name = format_json_string(snake_to_camel(field_name))
        matrix_docstr = format_json_string(f"{field_name}: " + doc_string)
        matrix_props = dict()
        matrix_props[format_json_string("description")] = matrix_docstr
        matrix_props[format_json_string("type")] = self._create_nullable_type(
            format_json_string("array"), nullable
        )

        matrix_items_l2 = dict()
        matrix_items_l1 = dict()
        is_static_dimension = (
            type(x) is int and type(y) is int
        )  # TODO support single static dimension?

        # Level 2
        matrix_items_l2[format_json_string("type")] = format_json_string(
            type_name
        )

        # Level 1
        matrix_items_l1[format_json_string("type")] = format_json_string(
            "array"
        )
        matrix_items_l1[format_json_string("items")] = matrix_items_l2
        if is_static_dimension:
            matrix_items_l1[format_json_string("minItems")] = y
            matrix_items_l1[format_json_string("maxItems")] = y

        # Outer
        matrix_props[format_json_string("items")] = matrix_items_l1
        if is_static_dimension:
            matrix_props[format_json_string("minItems")] = x
            matrix_props[format_json_string("maxItems")] = x

        self.current_struct.properties_buf.append(
            create_json_prop(matrix_name, matrix_props, indent_level=2)
        )
        self.current_struct.required_list.append(matrix_name)

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
        self.process_simple_field(field_name, "string", doc_string, nullable)

    def process_string_array_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        raise NotImplementedError

    def process_simple_field(  # TODO put size limits on values
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return
        simple_docstr = format_json_string(f"{field_name}: " + doc_string)
        simple_name = format_json_string(snake_to_camel(field_name))
        simple_props = dict()
        simple_props[format_json_string("description")] = simple_docstr
        if field_type_name.startswith(
            "type"
        ):  # NOTE this does not proecss nullable
            simple_props[format_json_string("$ref")] = format_json_string(
                f"{field_type_name}.json"
            )
        else:
            simple_props[format_json_string("type")] = (
                self._create_nullable_type(
                    format_json_string(field_type_name), nullable
                )
            )

        self.current_struct.properties_buf.append(
            create_json_prop(simple_name, simple_props, indent_level=2)
        )
        self.current_struct.required_list.append(simple_name)

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        pass  # processed manually with metadata

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
        enum_docstr = format_json_string(f"{field_name} (enum): " + doc_string)
        enum_field_name = format_json_string(field_type_name)
        enum_props = dict()
        enum_props[format_json_string("description")] = enum_docstr
        enum_props[format_json_string("type")] = format_json_string("integer")

        enum_dicts = []
        for i, enum_key in enumerate(enum_values):
            enum_dict = dict()
            enum_val = i
            enum_name = enum_key
            enum_split = enum_key.split("=")
            enum_val_docstr = enum_values_doc_strs[i]
            if len(enum_split) == 2:
                enum_name = enum_split[0].strip()
                enum_val = int(enum_split[1].strip())
            enum_dict[format_json_string("const")] = enum_val
            enum_dict[format_json_string("description")] = format_json_string(
                f"{enum_name}: {enum_val_docstr}"
            )
            enum_dicts.append(enum_dict)

        enum_props[format_json_string("oneOf")] = enum_dicts

        self.current_struct.properties_buf.append(
            create_json_prop(enum_field_name, enum_props, indent_level=2)
        )
        self.current_struct.required_list.append(enum_field_name)
