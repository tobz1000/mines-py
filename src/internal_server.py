#!/usr/bin/env python3.4
import numpy
import functools
import itertools

# Grid values
# Use value of 1 directly for counting surrounding mines; ~20% game speedup
# compared to checking val==MINE for each cell
MINE = 1
CLEAR = 0

def get_surrounding_coords(coords, dims):
	ret = []

	for offset in itertools.product(*([-1, 0, 1],) * len(coords)):
		# Don't include self
		if all(c == 0 for c in offset):
			continue

		surr_coords = tuple(sum(c) for c in zip(offset, coords))

		# Check all coords are positive
		if any(c < 0 for c in surr_coords):
			continue

		# Check all coords are within grid size
		if any(c >= d for c, d in zip(surr_coords, dims)):
			continue

		ret.append(surr_coords)

	return ret

def count_empty_cells(dims, mines):
	return functools.reduce(lambda x,y: x*y, dims) - mines

class PythonInternalServer(object):
	id = "unknown_seed"
	reload_id = None

	# Whether the game server can be relied upon to auto-clear zero-cells.
	clears_zeroes = False

	dims = None
	mines = None
	seed = None

	cells_rem = None
	game_over = False
	win = False

	game_grid = None

	# Specify "grid" (n-dimensional list of 1s and 0s) to override other options
	# and use a pre-determined game instead of random.
	def __init__(self, dims=None, mines=None, seed=None, grid=None):
		if grid:
			buffer = numpy.array(grid)
			if buffer.dtype != int:
				raise Exception(
					"Supplied buffer is invalid: {}".format(buffer)
				)
			self.game_grid = numpy.ndarray(buffer.shape, buffer=buffer)
			self.dims = self.game_grid.shape
			self.mines = numpy.count_nonzero(self.game_grid)
		else:
			self.game_grid = self.random_grid(dims, mines, seed)
			self.dims = dims
			self.mines = mines
			self.seed = seed

		self.cells_rem = count_empty_cells(self.dims, self.mines)
		self.id = (self.dims, self.mines, self.seed)


	def random_grid(self, dims, mines, seed):
		grid = numpy.ndarray(dims, dtype=int)
		grid.fill(CLEAR)
		grid.ravel()[:mines].fill(MINE)
		if seed is not None:
			numpy.random.seed(self.seed)
		numpy.random.shuffle(grid.ravel())
		return grid

	def turn(self, clear=[], flag=[], debug=None, client=None):
		cleared_cells = []
		for coords in clear:
			if self.game_grid[coords] == MINE:
				self.game_over = True
				return []
			else:
				cleared_cells.append({
					"coords" : coords,
					"surrounding" : sum([
						self.game_grid[surr_coords]
						for surr_coords in get_surrounding_coords(
							coords,
							self.dims
						)
					]),
					"state" : "cleared"
				})

		# Result already returned if game is lost
		self.cells_rem -= len(clear)
		if self.cells_rem == 0:
			self.win = True
			self.game_over = True

		return cleared_cells
