#!/usr/bin/env python3.4
import sys
import os
import importlib
import pip

import deps

venv_path = sys.argv[1]

if sys.prefix != os.path.realpath(venv_path):
	print(
		"Activate the virtual environment first:\n"
		". {}/bin/activate".format(venv_path)
	)
	sys.exit()

def installed(package):
	return bool(importlib.util.find_spec(package))

def install(package):
	pip.main(['install', '-q', package])

print("Checking/installing: {}".format(deps.imports))

for imp in deps.imports:
	if type(imp) is str:
		imp = (imp, None)

	package, source = imp

	if not installed(package):
		action_msg = "installing..."
		install(source or package)
	else:
		action_msg = "found"
	print("{:<30}{}".format(package, action_msg))
