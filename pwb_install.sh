# Functions for working with pywikibot build install test

function pwb_build_install {
    check_var $BUILD_PREFIX
    check_var $SYS_CC
    check_var $SYS_CXX
    check_var $PYTHON_EXE
    cd pywikibot-core
    cat << EOF > setup.cfg
[directories]
# 0verride the default basedir in setupext.py.
# This can be a single directory or a comma-delimited list of directories.
basedirlist = $BUILD_PREFIX, /usr
EOF
    CC=${SYS_CC} CXX=${SYS_CXX} python setup.py bdist_wheel
    require_success "Pywikibot build failed"
    $PYTHON_EXE ../mpl_delocate.py dist/*.whl
    require_success "Wheel delocation failed"
    delocate-addplat --rm-orig -x 10_9 -x 10_10 dist/*.whl
    pip install dist/*.whl
    cd ..
}


function pwb_test {
    check_var $PYTHON_EXE
    check_var $PIP_CMD
    echo "python $PYTHON_EXE"
    echo "pip $PIP_CMD"

    mkdir tmp_for_test
    cd tmp_for_test
    echo "sanity checks"
    $PYTHON_EXE -c "import sys; print('\n'.join(sys.path))"
    $PYTHON_EXE -c "import pywikibot; print(pywikibot.__file__)"

    echo "testing pywikibot using 1 process"
    $PYTHON_EXE -m unittest tests
    require_success "Testing pywikibot returned non-zero status"
    cd ..
}
