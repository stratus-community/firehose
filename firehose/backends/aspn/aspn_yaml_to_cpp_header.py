from os.path import join
from textwrap import dedent
from typing import List, Union

from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    ASPN_PREFIX,
    ASPN_PREFIX_LOWER,
    INDENT,
    MatrixType,
    format_and_write_to_file,
    format_c_codegen_array,
    format_docstring,
    is_length_field,
    name_to_struct,
)

ASPN_DIR = ASPN_PREFIX_LOWER

EXTRA_HEADER_INC = {
    'TypeTimestamp': """
#include <iostream>
    """,
    'TypeSatnavTime': """
#include <iostream>
    """,
}
EXTRA_HEADER_DEF = {
    'TypeTimestamp': """
/**
 * Create a TypeTimestamp object from decimal seconds.
 *
 * @param t The decimal time in seconds since the epoch.
 */
TypeTimestamp to_type_timestamp(double t = 0.);

/**
 * Create a TypeTimestamp object from integer seconds and nanoseconds.
 *
 * @param sec The number of seconds since the epoch, to be combined with \p nsec.
 * @param nsec The number of nanoseconds since the epoch, to be combined with \p sec.
 */
TypeTimestamp to_type_timestamp(int64_t sec, int64_t nsec);

/**
 * @param time An ASPN time
 *
 * @return A double-precision representation of this time in seconds. At realistic epoch times,
 * doubles are considerably less precise than TypeTimestamp's native storage format of an integer
 * number of nanoseconds, so such conversions should be kept to a minimum.
 */
double to_seconds(const TypeTimestamp& time);

/**
 * Add the value of two TypeTimestamp objects together without converting data types.
 *
 * @param t1 First TypeTimestamp object
 * @param t2 Second TypeTimestamp object
 *
 * @return A TypeTimestamp object holding the added time, (t1 + t2).
 */
TypeTimestamp operator+(const TypeTimestamp& t1, const TypeTimestamp& t2);

/**
 * Add the value of a TypeTimestamp object and a double value (in seconds). This operator overload
 * avoids an implicit cast from double to TypeTimestamp, which would yield an invalid result if the
 * double is in seconds, since TypeTimestamp stores time in nanoseconds.
 *
 * @param t1 A TypeTimestamp object
 * @param t2_sec A double value in seconds
 *
 * @return A TypeTimestamp object holding the added time, (t1 + t2_sec).
 */
TypeTimestamp operator+(const TypeTimestamp& t1, double t2_sec);

/**
 * @param t1_sec A double value in seconds
 * @param t2 A TypeTimestamp object
 *
 * @return A TypeTimestamp object holding the added time, (t1_sec + t2).
 */
TypeTimestamp operator+(double t1_sec, const TypeTimestamp& t2);

/**
 * Subtract the value of one Timestamp object from another Timestamp.
 *
 * @param t1 First TypeTimestamp object
 * @param t2 Second TypeTimestamp object
 *
 * @return A TypeTimestamp object holding the subtracted time, (t1 - t2).
 */
TypeTimestamp operator-(const TypeTimestamp& t1, const TypeTimestamp& t2);

/**
 * Subtract the value of a double (in seconds) from a TypeTimestamp object. This operator overload
 * avoids an implicit cast from double to TypeTimestamp, which would yield an invalid result if the
 * double is in seconds, since TypeTimestamp stores time in nanoseconds.
 *
 * @param t1 A TypeTimestamp object
 * @param t2_sec A double value in seconds
 *
 * @return A TypeTimestamp object holding the subtracted time, (t1 - t2_sec).
 */
TypeTimestamp operator-(const TypeTimestamp& t1, double t2_sec);

/**
 * @param t1_sec A double value in seconds
 * @param t2 A TypeTimestamp object
 *
 * @return A TypeTimestamp object holding the subtracted time, (t1_sec - t2).
 */
TypeTimestamp operator-(double t1_sec, const TypeTimestamp& t2);

/**
 * Check whether two TypeTimestamp objects represent the same nanosecond.
 *
 * @param t1 A TypeTimestamp object
 * @param t2 Another TypeTimestamp object
 *
 * @return `true` when both times represent the same nanosecond.
 */
bool operator==(const TypeTimestamp& t1, const TypeTimestamp& t2);

/**
 * Check whether two TypeTimestamp objects represent the same nanosecond.
 *
 * @param t1_sec A double value in seconds
 * @param t2 A TypeTimestamp object
 *
 * @return `true` when both times represent the same nanosecond.
 */
bool operator==(double t1_sec, const TypeTimestamp& t2);

/**
 * Check whether two TypeTimestamp objects represent the same nanosecond.
 *
 * @param t1 A TypeTimestamp object
 * @param t2_sec A double value in seconds
 *
 * @return `true` when both times represent the same nanosecond.
 */
bool operator==(const TypeTimestamp& t1, double t2_sec);

/**
 * Check whether two TypeTimestamp objects represent a different nanosecond.
 *
 * @param t1 A TypeTimestamp object
 * @param t2 Another TypeTimestamp object
 *
 * @return `true` when both times do not represent the same nanosecond.
 */
bool operator!=(const TypeTimestamp& t1, const TypeTimestamp& t2);

/**
 * Check whether two TypeTimestamp objects represent a different nanosecond.
 *
 * @param t1_sec A double value in seconds
 * @param t2 A TypeTimestamp object
 *
 * @return `true` when both times do not represent the same nanosecond.
 */
bool operator!=(double t1_sec, const TypeTimestamp& t2);

/**
 * Check whether two TypeTimestamp objects represent a different nanosecond.
 *
 * @param t1 A TypeTimestamp object
 * @param t2_sec A double value in seconds
 *
 * @return `true` when both times do not represent the same nanosecond.
 */
bool operator!=(const TypeTimestamp& t1, double t2_sec);

/**
 * Check whether time \p t1 occurred before time \p t2.
 *
 * @param t1 A TypeTimestamp object
 * @param t2 Another TypeTimestamp object
 *
 * @return `true` when \p t1 represents an earlier nanosecond than \p t2.
 */
bool operator<(const TypeTimestamp& t1, const TypeTimestamp& t2);

/**
 * @param t1_sec A double value in seconds
 * @param t2 A TypeTimestamp object
 *
 * @return `true` when \p t1_sec represents an earlier nanosecond than \p t2.
 */
bool operator<(double t1_sec, const TypeTimestamp& t2);

/**
 * @param t1 A TypeTimestamp object
 * @param t2_sec A double value in seconds
 *
 * @return `true` when \p t1 represents an earlier nanosecond than \p t2_sec.
 */
bool operator<(const TypeTimestamp& t1, double t2_sec);

/**
 * Check whether time \p t1 occurred after time \p t2.
 *
 * @param t1 A TypeTimestamp object
 * @param t2 Another TypeTimestamp object
 *
 * @return `true` when \p t1 represents a later nanosecond than \p t2.
 */
bool operator>(const TypeTimestamp& t1, const TypeTimestamp& t2);

/**
 * @param t1_sec A double value in seconds
 * @param t2 A TypeTimestamp object
 *
 * @return `true` when \p t1_sec represents a later nanosecond than \p t2.
 */
bool operator>(double t1_sec, const TypeTimestamp& t2);

/**
 * @param t1 A TypeTimestamp object
 * @param t2_sec A double value in seconds
 *
 * @return `true` when \p t1 represents a later nanosecond than \p t2_sec.
 */
bool operator>(const TypeTimestamp& t1, double t2_sec);

/**
 * Check whether time \p t1 is equal to or after \p t2.
 *
 * @param t1 A TypeTimestamp object
 * @param t2 A double value in seconds
 *
 * @return `true` when \p t1 represents a nanosecond later than or equal to \p t2.
 */
bool operator>=(const TypeTimestamp& t1, const TypeTimestamp& t2);

/**
 * @param t1_sec A double value in seconds
 * @param t2 A TypeTimestamp object
 *
 * @return `true` when \p t1_sec represents a nanosecond later than or equal to \p t2.
 */
bool operator>=(double t1_sec, const TypeTimestamp& t2);

/**
 * @param t1 A double value in seconds
 * @param t2_sec A TypeTimestamp object
 *
 * @return `true` when \p t1 represents a nanosecond later than or equal to \p t2_sec.
 */
bool operator>=(const TypeTimestamp& t1, double t2_sec);

/**
 * Check whether time \p t1 is equal to or before \p t2.
 *
 * @param t1 A TypeTimestamp object
 * @param t2 Another TypeTimestamp object
 *
 * @return `true` when \p t1 represents a nanosecond before or equal to \p t2.
 */
bool operator<=(const TypeTimestamp& t1, const TypeTimestamp& t2);

/**
 * @param t1_sec A double value in seconds
 * @param t2 A TypeTimestamp object
 *
 * @return `true` when \p t1_sec represents a nanosecond before or equal to \p t2.
 */
bool operator<=(double t1_sec, const TypeTimestamp& t2);

/**
 * @param t1 A TypeTimestamp object
 * @param t2_sec A double value in seconds
 *
 * @return `true` when \p t1 represents a nanosecond before or equal to \p t2_sec.
 */
bool operator<=(const TypeTimestamp& t1, double t2_sec);

/**
 * Write a human-readable representation of a `TypeTimestamp` to the given output stream.
 * @param output stream to write to.
 * @param time TypeTimestamp object being described.
 *
 * @return The output stream `output` after writing.
 */
std::ostream& operator<<(std::ostream& output, const TypeTimestamp& time);

""",
    'TypeSatnavTime': """
/**
 * Add a double to a TypeSatnavTime.
 * @param t TypeSatnavTime to add to.
 * @param t2_sec Value in seconds to add to \p t.
 * @return The result of the addition.
 */
TypeSatnavTime operator+(const TypeSatnavTime& t, double const t2_sec);

/**
 * Subtract a double from a TypeSatnavTime.
 * @param t TypeSatnavTime to subtract from.
 * @param t2_sec Value in seconds to subtract from \p t.
 * @return The result of the subtraction.
 */
TypeSatnavTime operator-(const TypeSatnavTime& t, double const t2_sec);

/**
 * Difference two TypeSatnavTime objects and return the result as a double.
 *
 * @param t1 TypeSatnavTime to subtract from.
 * @param t2 TypeSatnavTime to subtract from \p t1 .
 * @return The difference between the two times, represented as a double-precision number of seconds
 * @throw std::invalid_argument if the ErrorMode is DIE and t1.get_time_reference() !=
 * t2.get_time_reference()
 */
double operator-(const TypeSatnavTime& t1, const TypeSatnavTime& t2);

/**
 * Check whether two TypeSatnavTime objects represent the same time.
 * @param t1 LHS of the comparison.
 * @param t2 RHS of the comparison.
 * @return The boolean result of t1 == t2. Note, if t1.get_time_reference() !=
 * t2.get_time_reference(), will return false.
 */
bool operator==(const TypeSatnavTime& t1, const TypeSatnavTime& t2);

/**
 * Check whether two TypeSatnavTime objects represent different times.
 * @param t1 LHS of the comparison.
 * @param t2 RHS of the comparison.
 * @return The boolean result of t1 != t2. Note, if t1.get_time_reference() !=
 * t2.get_time_reference(), will return true.
 */
bool operator!=(const TypeSatnavTime& t1, const TypeSatnavTime& t2);

/**
 * Check whether TypeSatnavTime \p t2 ocurred after \p t1.
 * @param t1 LHS of the comparison.
 * @param t2 RHS of the comparison.
 * @return The boolean result of the t1 > t2.
 * @throw std::invalid_argument if the ErrorMode is DIE and t1.get_time_reference() !=
 * t2.get_time_reference()
 */
bool operator>(const TypeSatnavTime& t1, const TypeSatnavTime& t2);

/**
 * Check whether TypeSatnavTime \p t2 ocurred at or after \p t1.
 * Define the >= operator for the TypeSatnavTime class.
 * @param t1 LHS of the comparison.
 * @param t2 RHS of the comparison.
 * @return The boolean result of the t1 >= t2.
 * @throw std::invalid_argument if the ErrorMode is DIE and t1.get_time_reference() !=
 * t2.get_time_reference()
 */
bool operator>=(const TypeSatnavTime& t1, const TypeSatnavTime& t2);

/**
 * Check whether TypeSatnavTime \p t2 ocurred before \p t1.
 * @param t1 LHS of the comparison.
 * @param t2 RHS of the comparison.
 * @return The boolean result of the t1 < t2.
 * @throw std::invalid_argument if the ErrorMode is DIE and t1.get_time_reference() !=
 * t2.get_time_reference()
 */
bool operator<(const TypeSatnavTime& t1, const TypeSatnavTime& t2);

/**
 * Check whether TypeSatnavTime \p t2 ocurred at or before \p t1.
 * @param t1 LHS of the comparison.
 * @param t2 RHS of the comparison.
 * @return The boolean result of the t1 <= t2.
 * @throw std::invalid_argument if the ErrorMode is DIE and t1.get_time_reference() !=
 * t2.get_time_reference()
 */
bool operator<=(const TypeSatnavTime& t1, const TypeSatnavTime& t2);

/**
 * Define the `ostream` operator for the TypeSatnavTime class.
 * @param os The `std::ostream` reference.
 * @param t The TypeSatnavTime object to print.
 * @return The `std::ostream` reference that can print the TypeSatnavTime object.
 */
std::ostream& operator<<(std::ostream& os, const TypeSatnavTime& t);

""",
}


class Struct:
    def __init__(
        self,
        snake_case_struct_name: str,
        matrix_type_lower: str,
        matrix_includes: str,
    ):
        self.constructor_param_buf: List[str] = []
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
        self.virtual = ''
        class_name = self.struct_name.removeprefix(ASPN_PREFIX)
        inheritance = ''
        inheritance_overrides = ''
        if not class_name.startswith('Type'):
            inheritance = ': public TypeHeader'
            inheritance_overrides = f'''
                {ASPN_PREFIX}MessageType get_message_type() const override;
                void set_message_type({ASPN_PREFIX}MessageType) override;

                uint32_t get_vendor_id() const override;
                void set_vendor_id(uint32_t) override;

                uint64_t get_device_id() const override;
                void set_device_id(uint64_t) override;

                uint32_t get_context_id() const override;
                void set_context_id(uint32_t) override;

                uint16_t get_sequence_id() const override;
                void set_sequence_id(uint16_t) override;
            '''
        elif class_name == 'TypeHeader':
            self.virtual = 'virtual '

        destructor = f'~{class_name}(); '
        if class_name == 'TypeHeader':
            destructor = 'virtual ~TypeHeader();'

        self.header_template = dedent(f"""
            // This code is generated via firehose.
            // DO NOT hand edit code. Make any changes required using the firehose repo instead.

            #pragma once

            // ASPN-C class to wrap.
            #include <{ASPN_DIR}/{class_name}.h>

            // {matrix_type_lower}
            {matrix_includes}

            // ASPN-C++ includes
            {{includes}}

            // System includes
            #include <vector>
            {{extra_includes}}

            namespace {ASPN_DIR}_{matrix_type_lower} {{{{
            {{struct_docstr}}class {class_name} {inheritance} {{{{
            public:
            /**
            *  The C struct must have been created using the corresponding {ASPN_DIR}_*_new() function in
            *  ASPN-C. When this class' destructor is called, the memory will be cleaned up using the
            *  corresponding {ASPN_DIR}_*_free() function in ASPN-C.
            */
            {class_name}({self.struct_name}* c_struct, bool take_ownership = true);

            {class_name}({{ctor_params}});

            {destructor}

            {class_name}(const {class_name}& other);
            {class_name}& operator=(const {class_name}& rhs);

            {class_name}({class_name}&& other);
            {class_name}& operator=({class_name}&& rhs);

            {inheritance_overrides}

            /**
            * Returns the underlying C struct while retaining ownership of the pointer.  The pointer
            * is valid so long as this object has not gone out of scope.
            */
            {self.struct_name}* get_aspn_c() const;

            /**
             * Frees the underlying C struct and replaces it with \p replacement_struct.
             * Set \p take_ownership to false if this object should not free \p replacement_struct when it
             * is destroyed.
             */
            void reset_aspn_c({self.struct_name}* replacement_struct, bool take_ownership = true);

            {{struct_fields}}

            private:
            {self.struct_name}* c_struct;
            bool take_ownership = true;
            void nullptr_check() const;
            }}}};

            {{extra_declarations}}
            }}}}
        """)


class AspnYamlToCppHeader(Backend):
    matrix_type: MatrixType = MatrixType.NONE
    current_struct: Struct = None
    structs: List[Struct] = []

    def __init__(self):
        self.current_struct: Struct = None
        self.structs: List[Struct] = []
        self.namespace = self.matrix_type.name.lower()
        self.directory = self.matrix_type.name.lower()

    def matrix_includes(self) -> str:
        pass

    def vector(self, type: str, size: Union[str, int]) -> str:
        pass

    def matrix(self, type: str, x: Union[str, int], y: Union[str, int]) -> str:
        pass

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        # Expecting parent AspnCppBackend to clear output folder

    def begin_struct(self, snake_case_struct_name):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(
            snake_case_struct_name, self.namespace, self.matrix_includes()
        )

    def generate(self) -> str:
        self.structs += [self.current_struct]

        # TODO- sort the struct params and "new" function params so they match and are in
        # an order that makes sense.
        for struct in self.structs:
            class_name = struct.struct_name.removeprefix(ASPN_PREFIX)
            header_contents = struct.header_template.format(
                struct_docstr=format_docstring(
                    struct.struct_docstr, indent=INDENT
                ),
                struct_fields=format_c_codegen_array(struct.struct_fields_buf),
                ctor_params=','.join(struct.constructor_param_buf),
                includes='\n'.join(struct.includes),
                fn_basename=struct.fn_basename,
                fn_params=', '.join(struct.constructor_param_buf),
                nullability_macro_start=struct.nullability_macro_start,
                nullability_macro_end=struct.nullability_macro_end,
                extra_includes=EXTRA_HEADER_INC.get(class_name, ''),
                extra_declarations=EXTRA_HEADER_DEF.get(class_name, ''),
            )

            basename = struct.struct_name.replace(f"{ASPN_PREFIX}", "")
            h_output_filename = join(self.output_folder, f"{basename}.hpp")
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
        f_type = (
            f'std::vector<{type_name[len(ASPN_PREFIX) :].strip("*")}>'
            if type_name.startswith(ASPN_PREFIX)
            else self.vector(type_name, data_len)
        )

        docstr = doc_string
        if nullable:
            docstr += (
                '\nAn array of NaNs indicates this optional field is '
                'not provided.'
            )

        docstr = format_docstring(docstr, indent=INDENT)
        field_str = f"{f_type} {f_name}"

        if type_name.startswith(ASPN_PREFIX):
            ftype = type_name[len(ASPN_PREFIX) :].strip("*")
            self.current_struct.includes.append(f'#include "{ftype}.hpp"')
        self.current_struct.constructor_param_buf.append(field_str)

        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}{f_type} get_{f_name}() const"
        )
        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}void set_{f_name}({f_type})"
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
        if nullable:
            doc_string += (
                '\nA matrix of NaNs indicates this optional field is '
                'not provided.'
            )
        docstr = format_docstring(doc_string, indent=INDENT)

        try:
            x = int(x)
        except ValueError:
            pass
        try:
            y = int(y)
        except ValueError:
            pass

        field_str = f"{self.matrix(type_name, x, y)} {field_name}"

        self.current_struct.constructor_param_buf.append(field_str)
        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}{self.matrix(type_name, x, y)} get_{field_name}() const"
        )
        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}void set_{field_name}({self.matrix(type_name, x, y)})"
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
        self.current_struct.includes.append('#include <string>')
        self.current_struct.constructor_param_buf.append(
            f"const std::string& {field_name}"
        )

        docstr = format_docstring(doc_string, indent=INDENT)

        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}std::string {self.current_struct.virtual} get_{field_name}() const"
        )
        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}void {self.current_struct.virtual} set_{field_name}(const std::string&)"
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

        if is_length_field(field_name):
            # Generate getters for length fields, but skip using them in constructors and don't
            # generate setters.
            self.current_struct.struct_fields_buf.append(
                f"{docstr}{INDENT}{field_type_name} {self.current_struct.virtual} get_{field_name}() const"
            )
            return

        field_str = f"{field_type_name} {field_name}"

        if field_type_name.startswith(f"{ASPN_PREFIX}Type"):
            # If one of the fields of the current struct is another ASPN
            # struct, be sure to include its header file.
            field_type_name = field_type_name[len(ASPN_PREFIX) :].strip("*")
            field_str = f"{field_type_name} {field_name}"
            self.current_struct.includes.append(
                f'#include "{field_type_name}.hpp"'
            )

            # If the constructor parameter is an ASPN value type, instead of
            # passing the type directly we want to simplify things for ASPN-C
            # users by having them pass in the parameters used to initialize
            # those types.  The parameter name is updated accordingly.

            # For example, most measurements have an AspnTypeHeader and
            # an AspnTypeTimestamp.  Instead of having to construct those
            # first and then pass them to the measurement constructor, the
            # measurement constructor can be called and the same fields that
            # would have been used to construct AspnTypeHeader and
            # AspnTypeTimestamp will be passed to the measurement
            # constructor instead.

            # But I can't do this without more information... How do I know
            # what the fields of the type are?
            self.current_struct.constructor_param_buf.append(field_str)
        else:
            self.current_struct.constructor_param_buf.append(field_str)

        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}{field_type_name} {self.current_struct.virtual} get_{field_name}() const"
        )
        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}void {self.current_struct.virtual} set_{field_name}({field_type_name})"
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
        docstr = format_docstring(doc_string, indent=INDENT)
        field_str = f"{field_type_name} {field_name}"
        self.current_struct.constructor_param_buf.append(field_str)

        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}{field_type_name} {self.current_struct.virtual} get_{field_name}() const"
        )
        self.current_struct.struct_fields_buf.append(
            f"{docstr}{INDENT}void {self.current_struct.virtual} set_{field_name}({field_type_name})"
        )


class AspnYamlToXtensorHeader(AspnYamlToCppHeader):
    def __init__(self):
        self.matrix_type = MatrixType.XTENSOR
        super().__init__()

    def matrix_includes(self) -> str:
        return '''#include <xtensor/containers/xtensor.hpp>
                  #include <xtensor/containers/xadapt.hpp>'''

    def vector(self, type: str, size: Union[str, int]) -> str:
        if isinstance(size, int):
            return f'xt::xtensor_fixed<{type}, xt::xshape<{size}>>'
        else:
            return f'xt::xtensor<{type}, 1>'

    def matrix(self, type: str, x: Union[str, int], y: Union[str, int]) -> str:
        if isinstance(x, int) and isinstance(y, int):
            return f'xt::xtensor_fixed<{type}, xt::xshape<{x}, {y}>>'
        else:
            return f'xt::xtensor<{type}, 2>'


class AspnYamlToXtensorPyHeader(AspnYamlToCppHeader):
    def __init__(self):
        self.matrix_type = MatrixType.XTENSOR
        super().__init__()
        self.directory = 'xtensor_py'

    def matrix_includes(self) -> str:
        return '''#include <xtensor-python/pytensor.hpp>
                  #include <xtensor/containers/xadapt.hpp>'''

    def vector(self, type: str, _: Union[str, int]) -> str:
        return f'xt::pytensor<{type}, 1>'

    def matrix(
        self, type: str, _: Union[str, int], __: Union[str, int]
    ) -> str:
        return f'xt::pytensor<{type}, 2>'


class AspnYamlToEigenHeader(AspnYamlToCppHeader):
    def __init__(self):
        self.matrix_type = MatrixType.EIGEN
        super().__init__()

    def matrix_includes(self) -> str:
        return '#include <Eigen/Dense>'

    def vector(self, type: str, _: Union[str, int]) -> str:
        return f'Eigen::Matrix<{type}, Eigen::Dynamic, 1>'

    def matrix(
        self, type: str, _: Union[str, int], __: Union[str, int]
    ) -> str:
        return f'Eigen::Matrix<{type}, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>'


class AspnYamlToStlHeader(AspnYamlToCppHeader):
    def __init__(self):
        self.matrix_type = MatrixType.STL
        super().__init__()

    def matrix_includes(self) -> str:
        return '#include <vector>'

    def vector(self, type: str, _: Union[str, int]) -> str:
        return f'std::vector<{type}>'

    def matrix(
        self, type: str, _: Union[str, int], __: Union[str, int]
    ) -> str:
        return f'std::vector<{type}>'
