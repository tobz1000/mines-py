#!/bin/bash

SETUP_DIR=$(pwd)/$(dirname $0)

pyvenv-3.5 $VENV_DIR
. $VENV_DIR/bin/activate
$SETUP_DIR/venv_install.py $VENV_DIR
