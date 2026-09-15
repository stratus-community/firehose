project('aspn-generated',
    ['c', 'cpp'],
    version : '23',
    default_options: ['cpp_std=c++20', 'c_std=c99', 'warning_level=3'])

if (host_machine.system() == 'windows')
    if meson.get_compiler('cpp').get_argument_syntax() == 'msvc'
        add_project_arguments(['/bigobj', '/Zc:preprocessor', '-D_USE_MATH_DEFINES', '-DNOMINMAX'], language : 'cpp')
    endif
endif

if not get_option('aspn-c').disabled()
    subdir('aspn-c')
else
    aspn_c_dep = disabler()
endif

if not get_option('aspn-cpp').disabled()
    subdir('aspn-cpp')
else
    aspn_xtensor_dep = disabler()
    aspn_xtensor_py_dep = disabler()
    aspn_eigen_dep = disabler()
    aspn_stl_dep = disabler()
endif

if not get_option('lcm-generated').disabled()
    subdir('lcm')
else
    aspn_lcm_c_dep = disabler()
    aspn_lcm_cpp_dep = disabler()
endif

if not get_option('dds-generated').disabled()
    subdir('dds')
else
    aspn23_dds_dep = disabler()
endif
