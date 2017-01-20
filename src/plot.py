#!/usr/bin/env python3
USE_MULTIPROCESS = False

import sys
import functools
import math
# TODO: sometimes errors using multiprocess due to crappy pickling. Disable
# in this case.
if USE_MULTIPROCESS:
	import multiprocess as multiprocessing
else:
	import multiprocessing.dummy as multiprocessing
import statistics
import scipy
import statsmodels.api as sm
import numpy as np
import matplotlib.pyplot as pyplot
import progressbar # github.com/coagulant/progressbar-python3

from guess_ais import *
from server_json_wrapper import JSONServerWrapper

REPEATS_PER_CONFIG = 300
DIMS_LEN = 6
NUM_DIMS = 2
SEEDS_SEED = 7
MINES_MIN = 1
MINES_MAX = (DIMS_LEN ** NUM_DIMS) // 2

# Reduce this when using very slow clients
POOL_MAX_CHUNKSIZE = 10

SERVER = PythonInternalServer

if hasattr(multiprocessing, "cpu_count"):
	no_cores = multiprocessing.cpu_count()
else:
	no_cores = 1

plot_clients = [
	("blue", ReactiveClient),
	("green", ReactiveClientCheckShared),
	#("red", ReactiveClientGuess),
	#("cyan", ReactiveClientGuessAny),
	("orange", ReactiveClientAvgEmptiesBalanced),
	#("purple", ReactiveClientExhaustiveTest),
	#("pink", ReactiveClientExhaustiveSplit),
]

# Chunksize for pools as calculated in multiprocessing module, but with the
# addition of a specified cap. Allows for more frequent progress counter updates
# on large game sets, with no noticeable performance impact (using the default
# of 100)
def get_chunksize(len, cores, max=POOL_MAX_CHUNKSIZE):
	if len == 0:
		return 0

	chunksize, extra = divmod(len, cores * 4)
	if extra:
		chunksize += 1
	return min(max, chunksize)

def play_session(
	client,
	repeats_per_config = REPEATS_PER_CONFIG,
	dim_length_range = (DIMS_LEN, DIMS_LEN + 1), # range() params
	mine_count_range = (MINES_MIN, MINES_MAX + 1),
	cell_mine_ratio_range = None, # Alternative parameter to mine count
	num_dims_range = (NUM_DIMS, NUM_DIMS + 1),
	seeds_seed = SEEDS_SEED
):
	configs = []

	if seeds_seed is not None:
		np.random.seed(seeds_seed)
	seeds = np.random.randint(0, 4294967295, repeats_per_config)

	# Get a list of all game parameters first
	for num_dims in range(*num_dims_range):
		for dim_length in range(*dim_length_range):
			cell_count = dim_length ** num_dims

			if cell_mine_ratio_range is not None:
				# setify to remove dups
				mine_counts = list(set(
					math.floor(cell_count/m)
					for m in range(*cell_mine_ratio_range)
				))
			else:
				mine_counts = list(range(*mine_count_range))

			# Remove invalid values
			mine_counts = [m for m in mine_counts if m < cell_count and m > 0]

			for mine_count in mine_counts:
				for seed in seeds:
					configs.append({
						"client": client,
						"dims": (dim_length,) * num_dims,
						"mines": mine_count,
						"seed" : seed
					})

	pool = multiprocessing.Pool(no_cores)
	results = pool.map_async(
		play_game,
		configs,
		chunksize = get_chunksize(len(configs), no_cores)
	)
	pool.close()

	# Run w/ progress bar, now we know how many games there are
	counter = progressbar.ProgressBar(
		widgets = [
			progressbar.Timer(format="%s"),
			" | ",
			progressbar.SimpleProgress(),
			" | " + client.__name__
		],
		maxval = len(results._value)
	)

	counter_run = counter.start()
	while not results.ready():
		count = len(results._value) - results._value.count(None)
		counter_run.update(count)
		time.sleep(0.5)
	counter_run.finish()

	return results.get()

# Returns a dict of lists of games with identical configs
def group_by_repeats(games):
	games_by_config = {}
	for g in games:
		key = (tuple(g.server.dims), g.server.mines)
		if key not in games_by_config:
			games_by_config[key] = []
		games_by_config[key].append(g)
	return games_by_config.values()

def get_fraction_cleared(game):
	empty_cell_count = (
		functools.reduce(lambda x,y: x*y, game.server.dims) - game.server.mines
	)
	return (empty_cell_count - game.server.cells_rem) / empty_cell_count

if __name__ == "__main__":
	# Game-running function. Must be non-dynamic, top-level to work with the
	# pickle library used by multiprocessing.
	def play_game(config):
		return config["client"](
			SERVER(
				config["dims"],
				config["mines"],
				config["seed"]
			),
			first_coords=0
		)

	# Option to assume games with zero mines would always be won, to save time
	# actually playing them.
	def plot(instances, x_fn, y_fn, label, colour, add_zero_mine=False):
		if len(instances) < 1:
			raise Exception("No game instances to plot")
		instances = sorted(instances, key=x_fn)
		add_zero_mine = add_zero_mine and x_fn(instances[0]) == 1
		pyplot.plot(
			([0] if add_zero_mine else []) + [x_fn(i) for i in instances],
			([100] if add_zero_mine else []) + [y_fn(i) for i in instances],
			c = colour,
			label = label
		)

	(figure, axes) = pyplot.subplots()

	for (colour, client) in plot_clients:
		games = play_session(client)

		# No. mines vs % games won
		plot(
			group_by_repeats(games),
			lambda g: g[0].server.mines,
			lambda g: 100 * statistics.mean(
				[1 if _g.server.win else 0 for _g in g]
			),
			client.__name__,
			colour
		)

	# Set graph output settings and render
	for spine in axes.spines.values():
		spine.set_visible(False)
	# TODO: get pyplot.show() working...
	pyplot.legend()
	pyplot.title("Mines {} grid, {} games per configuration".format(
		"{}".format(DIMS_LEN) + "x{}".format(DIMS_LEN) * (NUM_DIMS - 1),
		REPEATS_PER_CONFIG
	))
	pyplot.xlabel('No. mines')
	pyplot.ylabel('% Won')
	pyplot.savefig('img.png')
