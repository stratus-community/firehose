from os import makedirs, remove, path
from os.path import join
from textwrap import dedent
from typing import List, Union

from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    ASPN_PREFIX_LOWER,
    INDENT,
    format_and_write_to_file,
    is_length_field,
    pascal_to_snake,
    snake_to_pascal,
)

ASPN_MODULE = ASPN_PREFIX_LOWER


class Struct:
    def __init__(self, pascal_struct_name: str, to_lcm: bool = True):
        self.struct_name = pascal_struct_name
        # this field allows us to define whether we are going to or from lcm.
        # defaults to true
        self.to_lcm = to_lcm
        self.assignments: list[str] = []
        self.imports_aspn = []
        self.to_lcm_template = dedent(f"""
            def {pascal_to_snake(pascal_struct_name)}_to_lcm(old: {pascal_struct_name}) -> Lcm{pascal_struct_name}:
            {INDENT}msg = Lcm{pascal_struct_name}()
            {{assigns}}

            {INDENT}return msg
            """)
        self.from_lcm_template = dedent(f"""
            def lcm_to_{pascal_to_snake(pascal_struct_name)}(old: Lcm{pascal_struct_name}) -> {pascal_struct_name}:
            {INDENT}return {pascal_struct_name}({{fields}})
            """)


PRIMITIVES = ["float", "int", "bool", "str"]


class AspnYamlToLCMTranslations(Backend):
    current_struct: Struct | None = None
    structs: List[Struct] = []
    output_folder = None

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        makedirs(self.output_folder, exist_ok=True)
        if self.output_folder is not None:
            filename = f'{self.output_folder}/lcm_translations.py'
            if path.exists(filename):
                remove(filename)

    def begin_struct(self, struct_name, to_lcm: bool = False):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(f"{snake_to_pascal(struct_name)}", to_lcm)

    def generate(self):
        if self.output_folder is None:
            return
        if self.current_struct is not None:
            self.structs += [self.current_struct]

        imports_aspn = []
        imports_lcm = []
        functions = []
        exports = []
        alias_aspn = []
        alias_lcm = []
        to_lcm_map = []
        from_lcm_map = []
        decode_lcm_map = []
        for s in self.structs:
            # Function assignments to LCM
            if s.to_lcm:
                assignments = [f"{INDENT}msg.{a}" for a in s.assignments]
                functions.append(
                    s.to_lcm_template.format(assigns="\n".join(assignments))
                )
                continue

            # Function assignments from LCM
            assignments = [f"{INDENT}{INDENT}{a}" for a in s.assignments]
            functions.append(
                s.from_lcm_template.format(fields=", ".join(assignments))
            )

            # Imports/exports/etc. only need to happen once, so skip them for
            # the "to LCM" structs (see above)
            snake_name = pascal_to_snake(s.struct_name)
            imports_aspn.append(
                f"from {ASPN_PREFIX_LOWER}.{snake_name} import {s.struct_name}"
            )
            imports_aspn.extend(s.imports_aspn)
            imports_lcm.append(
                f"from {ASPN_PREFIX_LOWER}_lcm.{snake_name} import {snake_name} as Lcm{s.struct_name}"
            )
            exports.append(f"lcm_to_{snake_name} as lcm_to_{snake_name}")
            exports.append(f"{snake_name}_to_lcm as {snake_name}_to_lcm")

            # For Measurement/Metadata objects, we also want to generate some
            # utility definitions
            if s.struct_name.startswith("Type"):
                continue
            alias_aspn.append(f"{INDENT}{s.struct_name},")
            alias_lcm.append(f"{INDENT}Lcm{s.struct_name},")
            to_lcm_map.append(f"{INDENT}{s.struct_name}: {snake_name}_to_lcm,")
            from_lcm_map.append(
                f"{INDENT}Lcm{s.struct_name}: lcm_to_{snake_name},"
            )
            decode_lcm_map.append(
                f"{INDENT}Lcm{s.struct_name}._get_packed_fingerprint(): "
                f"Lcm{s.struct_name}.decode,"
            )

        imports = "\n".join(imports_aspn + imports_lcm)
        functions = "\n".join(functions)
        exports = "\n".join(exports)
        alias_aspn = "\n".join(alias_aspn)
        alias_lcm = "\n".join(alias_lcm)
        to_lcm_map = "\n".join(to_lcm_map)
        from_lcm_map = "\n".join(from_lcm_map)
        decode_lcm_map = "\n".join(decode_lcm_map)

        format_and_write_to_file(
            dedent("""\
                from typing import TypeAlias, Union, Callable
                import numpy as np
                import math

                {imports}

                {functions}

                AspnMsg: TypeAlias = Union[
                {alias_aspn}
                ]

                LcmMsg: TypeAlias = Union[
                {alias_lcm}
                ]

                to_lcm_map: dict[type[AspnMsg], Callable] = {{
                {to_lcm_map}
                }}

                from_lcm_map: dict[type[LcmMsg], Callable] = {{
                {from_lcm_map}
                }}

                decode_lcm_map: dict[bytes, Callable] = {{
                {decode_lcm_map}
                }}\
                """).format(
                imports=imports,
                alias_aspn=alias_aspn,
                alias_lcm=alias_lcm,
                functions=functions,
                to_lcm_map=to_lcm_map,
                from_lcm_map=from_lcm_map,
                decode_lcm_map=decode_lcm_map,
            ),
            join(self.output_folder, "lcm_translations.py"),
        )

        format_and_write_to_file(
            dedent("""\
                # Follow Python export conventions:
                # https://typing.readthedocs.io/en/latest/spec/distributing.html#import-conventions
                from .lcm_translations import (
                    AspnMsg as AspnMsg,
                    LcmMsg as LcmMsg,
                    to_lcm_map as to_lcm_map,
                    from_lcm_map as from_lcm_map,
                    decode_lcm_map as decode_lcm_map,
                    {exports}
                )\
                """).format(exports=exports),
            join(self.output_folder, "__init__.py"),
        )

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # Backend Methods # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def process_func_ptr_field_with_self(
        self, field_name: str, params, return_t, doc_string: str, nullable=None
    ):
        raise NotImplementedError

    def _process_array(
        self,
        field_name: str,
        type_name: str,
        nullable: bool | None,
        dim1_len: int | str,
        dim2_len: int | str | None = None,
    ):
        """Process 1d or 2d array field."""
        if self.current_struct is None:
            return

        # In lcm, add length fields missing from aspn-py if not already set
        if (
            self.current_struct.to_lcm
            and isinstance(dim1_len, str)
            and not any(
                assign.startswith(dim1_len)
                for assign in self.current_struct.assignments
            )
        ):
            qualifier = ""
            if nullable:
                qualifier = f" if old.{field_name} is not None else 0"
            self.current_struct.assignments.append(
                f"{dim1_len} = len(old.{field_name})" + qualifier
            )

        if self.current_struct.to_lcm:
            qualifier = ""
            if nullable:
                data_len = (
                    str(dim1_len)
                    if isinstance(dim1_len, int)
                    else f"msg.{dim1_len}"
                )
                nans = f"[math.nan] * {data_len}"
                if dim2_len:
                    nans = f"[{nans}] * {data_len}"
                qualifier = f" if old.{field_name} is not None else {nans}"
            if isinstance(dim1_len, int) or type_name in PRIMITIVES:
                self.current_struct.assignments.append(
                    f"{field_name} = old.{field_name}.tolist()" + qualifier
                )
            else:
                self.current_struct.assignments.append(
                    f"{field_name} = [{pascal_to_snake(type_name)}_to_lcm(x) "
                    f"for x in old.{field_name}]" + qualifier
                )
        else:
            if isinstance(dim1_len, int) or type_name in PRIMITIVES:
                qualifier = ""
                if nullable:
                    qualifier += (
                        f"if not np.isnan(old.{field_name}).any() else None"
                    )
                self.current_struct.assignments.append(
                    f"{field_name} = np.array(old.{field_name})" + qualifier
                )
            else:
                self.current_struct.assignments.append(
                    f"{field_name} = [lcm_to_{pascal_to_snake(type_name)}(x) "
                    f"for x in old.{field_name}]"
                )

    def process_data_pointer_field(
        self,
        field_name: str,
        type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable=None,
    ):
        self._process_array(field_name, type_name, nullable, data_len)

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: int | str,
        y: int | str,
        doc_string: str,
        nullable=None,
    ):
        if x != y:
            raise NotImplementedError

        self._process_array(field_name, type_name, nullable, x, y)

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
        nullable=None,
    ):
        raise NotImplementedError

    def process_string_field(
        self, field_name: str, doc_string: str, nullable=None
    ):
        self.process_simple_field(
            field_name, "str", doc_string, nullable=nullable
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
        if self.current_struct is None:
            return
        if is_length_field(field_name):
            return

        if self.current_struct.to_lcm:
            qualifier = ""
            if field_type_name in PRIMITIVES:
                if nullable:
                    # LCM cannot handle None fields, so these must be
                    # default-initalized
                    qualifier = (
                        f" if old.{field_name} is not None else "
                        f"{field_type_name}()"
                    )
                self.current_struct.assignments.append(
                    f"{field_name} = old.{field_name}" + qualifier
                )
            else:
                if nullable:
                    qualifier = (
                        f" if old.{field_name} is not None else "
                        f"Lcm{field_type_name}()"
                    )
                self.current_struct.assignments.append(
                    f"{field_name} = {pascal_to_snake(field_type_name)}"
                    f"_to_lcm(old.{field_name})" + qualifier
                )
        else:
            if field_type_name in PRIMITIVES:
                self.current_struct.assignments.append(
                    f"{field_name} = old.{field_name}"
                )
            else:
                self.current_struct.assignments.append(
                    f"{field_name} = lcm_to_"
                    f"{pascal_to_snake(field_type_name)}(old.{field_name})"
                )

    def process_class_docstring(self, doc_string: str, nullable=None):
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
        if self.current_struct is None:
            return

        if self.current_struct.to_lcm:
            self.current_struct.assignments.append(
                f"{field_name} = old.{field_name}.value"
            )
        else:
            struct_name = pascal_to_snake(self.current_struct.struct_name)
            field_type_name = f"{self.current_struct.struct_name}{snake_to_pascal(field_type_name)}"
            import_string = f"from {ASPN_PREFIX_LOWER}.{struct_name} import {field_type_name}"
            if import_string not in self.current_struct.imports_aspn:
                self.current_struct.imports_aspn.append(import_string)
            self.current_struct.assignments.append(
                f"{field_name} = {field_type_name}(old.{field_name})"
            )
