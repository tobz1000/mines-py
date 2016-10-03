#!/usr/bin/env python3.4
"""Start a number of client-server pairs to play the specified games."""
#TODO: take CLI-style arguments too

import sys
import json

from guess_ais import *

def run_game_config(
	dims,
	mines,
	repeats=1,
	client=ReactiveClient,
	server=PythonInternalServer
):
	for _ in range(repeats):
		client(server(dims, mines))

def str_to_class(obj):
	"""Get class types from strings for the client/server parameters"""
	for param in "client", "server":
		if(param in obj and type(obj[param]) is str):
			obj[param] = globals()[obj[param]]
	return obj

if __name__ == '__main__':
	try:
		args = json.loads(sys.argv[1], object_hook=str_to_class)
	except:
		print("Must provide parameters as a JSON string.")
		raise
	for cfg in args:
		# Convert JSON strings to class types
		run_game_config(**cfg)