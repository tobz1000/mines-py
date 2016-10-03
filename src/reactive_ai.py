#!/usr/bin/env python3.4
import random
import math
import itertools
import time
import inspect
import traceback
import enum

from server_json_wrapper import JSONServerWrapper
from internal_server import (
	PythonInternalServer,
	get_surrounding_coords,
	count_empty_cells
)

# TODO: command line arg '-v0/-v1' etc with 'argparse' package
# 0: No output
# 1: See results of repeated games
# 2: See progress of single game (turns only)
# 3: Progress of single game with start/end info
VERBOSITY = 0

class State(enum.Enum):
	MINE = -1
	UNKNOWN = -2
	EMPTY = -3
	TO_CLEAR = -4

def log(verbosity, *args, **kwargs):
	if(VERBOSITY >= verbosity):
		print(*args, **kwargs)

class GameEnd(Exception):
	def __init__(self, game, msg=None):
		end_time = time.time()
		# TODO: this is negative for really short games. Figure that out...
		game.total_time = end_time - game.start_time - game.wait_time

		# Line break
		log(2)

		if msg:
			log(2, msg)

		turns_id = "{:x}".format(abs(game.turns_hash_sum))[:5]

		log(3, "{}".format("Win!!11" if game.server.win else "Lose :((("))
		log(3, "Turns id: {}".format(turns_id))
		log(3, "Time elapsed: {:.5}s (+{:.5}s waiting)".format(
			game.total_time,
			game.wait_time)
		)
		log(3, "="*50)

class ReactiveClient(object):
	# Set True for more advanced logic.
	check_shared = False
	game_grid = None
	known_cells = None
	password = "pass"
	game_over = False
	win = False
	turns_hash_sum = 0
	start_time = None
	wait_time = None

	# Types of cell to track in reverse-lookup dicts
	cell_state_lookups = [ State.TO_CLEAR, State.EMPTY, State.MINE ]

	def __init__(self, server, first_coords=None):
		self.server = server
		self.wait_time = float(0)

		self.game_grid = GameGrid(self)

		# Reverse lookup table for grid
		self.known_cells = { s : [] for s in self.cell_state_lookups }

		log(3, "New game: {} (original {}) dims: {} mines: {}".format(
			self.server.id,
			self.server.reload_id or self.server.id,
			self.server.dims,
			self.server.mines
		))

		try:
			self.play(first_coords)
		except GameEnd as e:
			pass

	def random_coords(self):
		return tuple(
			math.floor(random.random() * dim) for dim in self.server.dims
		)

	def all_coords(self):
		return itertools.product(*(range(c) for c in self.server.dims))

	# Debug information about each cell. Read private vars to avoid triggering
	# any prop-getting behaviour.
	def game_cells_debug(self):
		info = {}

		# Can't use tuple as JSON key; this matches js-style toString for a
		# coords array
		def coords_json_key(coords):
			return ",".join(str(c) for c in coords)

		for coords, cell in self.game_grid.items():
			# Add some private primitives
			cell_info = {
				attr : getattr(cell, attr) for attr in [
					"coords",
					"_state",
					"_unkn_surr_mine_cnt",
					"_unkn_surr_empt_cnt"
				]
			}

			# Represent adjacent cells by their coords
			cell_info["_surr_cells"] = None if cell._surr_cells is None else [
				adj_cell.coords for adj_cell in cell._surr_cells
			]

			cell_info["shared_unkn_surr_cnts"] = {
				coords_json_key(adj_cell.coords) : count
				for adj_cell, count in cell.shared_unkn_surr_cnts.items()
			}

			# Can't use tuple as JSON key; this matches js-style toString for
			# a coords array
			info[coords_json_key(coords)] = cell_info

		return info

	def play(self, first_coords):
		self.start_time = time.time()
		if first_coords == None:
			first_coords = self.random_coords()

		if first_coords == 0:
			first_coords = (0,) * len(self.server.dims)

		log(3, "Clearing... ", end='', flush=True)
		self.game_grid[first_coords].state = State.TO_CLEAR
		while True:
			self.clear_cells()

	def clear_cells(self):
		if not any(self.known_cells[State.TO_CLEAR]):
			guess_cell = self.get_guess_cell()

			if guess_cell is None:
				raise GameEnd(self, "Out of ideas!")

			log(2, "(?)", end='', flush=True)
			guess_cell.state = State.TO_CLEAR

		to_clear, to_flag = (
			tuple(c.coords for c in self.known_cells[state])
			for state in (State.TO_CLEAR, State.MINE)
		)

		log(2, "{}".format(len(to_clear)), end='', flush=True)

		self.turns_hash_sum += hash(to_clear)

		wait_start = time.time()
		new_cells = self.server.clear_cells(
			clear=to_clear,
			flag=to_flag,
			debug={
				"gameInfo" : "game info here",
				"cellInfo" : self.game_cells_debug()
			}
		)
		self.wait_time += time.time() - wait_start

		log(2, "->{} ".format(len(new_cells)), end='', flush=True)

		if self.server.game_over:
			raise GameEnd(self)

		for cell_data in new_cells:
			cell = self.game_grid[tuple(cell_data["coords"])]
			surr_mine_count = cell_data["surrounding"]

			cell.state = {
				'empty':	State.EMPTY,
				'cleared':	State.EMPTY,
				'mine':		State.MINE,
				'unknown':	State.UNKNOWN
			}[cell_data["state"]]

			# This check avoids unnecessary calculations on zero-cells; can
			# speed up some games a lot.
			if surr_mine_count > 0 or not self.server.clears_zeroes:
				cell.unkn_surr_mine_cnt += surr_mine_count
				cell.unkn_surr_empt_cnt -= surr_mine_count

	def get_guess_cell(self):
		pass

class ReactiveClientCheckShared(ReactiveClient):
	check_shared = True

class GameGrid(dict):
	def __init__(self, parent_game):
		self.parent_game = parent_game

	def __getitem__(self, coords):
		if not coords in self:
			self.__setitem__(coords, Cell(coords, self.parent_game))
		return super().__getitem__(coords)

# The number of unknown cells which surround both of two cells. While this is
# accessed from dictionaries on either cell, it is only actually stored on one
# of the two (the other just defers to it).
class SharedUnknownSurrCounts(dict):
	def __init__(self, this_cell):
		self.this_cell = this_cell

	def __setitem__(self, other_cell, val):
		if id(other_cell) > id(self.this_cell):
			other_cell.shared_unkn_surr_cnts[self.this_cell] = val
			return
		super().__setitem__(other_cell, val)
		if (
			self.this_cell.state == State.EMPTY and
			other_cell.state == State.EMPTY
		):
			self.this_cell.check_exclusive_cells_saturated(other_cell)

	def __getitem__(self, other_cell):
		if id(other_cell) > id(self.this_cell):
			return other_cell.shared_unkn_surr_cnts[self.this_cell]
		# Get the value from the other cell if it has it. If not set yet,
		# count how many cells are shared *total* (no UNKNOWN check), since when
		# it's first accessed, all involved cells should be unknown.
		if not other_cell in self:
			# TODO: figure out formula based on coords values instead of
			# compared sets; see if it's quicker.
			val = len(self.this_cell.surr_cells & other_cell.surr_cells)
			self.__setitem__(other_cell, val)
		return super().__getitem__(other_cell)

class Cell(object):
	def __init__(self, coords, parent_game):
		self.coords = coords
		self.parent_game = parent_game

		self._state = State.UNKNOWN
		self._surr_cells = None
		self._unkn_surr_mine_cnt = 0
		self._unkn_surr_empt_cnt = None
		self.shared_unkn_surr_cnts = SharedUnknownSurrCounts(self)

	def __str__(self):
		return (
			"Cell {}: {} surrounding; state={}; unkn_surr_mine_cnt={}; "
			"unkn_surr_empt_cnt={}".format(
				self.coords,
				len(self.surr_cells),
				self.state,
				self.unkn_surr_mine_cnt,
				self.unkn_surr_empt_cnt
			)
		)

	@property
	def state(self):
		return self._state

	@state.setter
	def state(self, val):
		if val == self._state:
			return

		known_cells = self.parent_game.known_cells

		if self._state in known_cells and self in known_cells[self._state]:
			known_cells[self._state].remove(self)

		if val in known_cells:
			known_cells[val].append(self)

		self._state = val

		if val == State.MINE:
			for cell in self.surr_cells:
				cell.unkn_surr_mine_cnt -= 1

		if val == State.EMPTY:
			for cell in self.surr_cells:
				cell.unkn_surr_empt_cnt -= 1
				if self.parent_game.check_shared:
					self.check_exclusive_cells_saturated(cell)

		# Update the number of shared unknowns for each pair of surrounding
		# cells
		if (
			self.parent_game.check_shared and
			(val == State.EMPTY or val == State.MINE)
		):
			for c1, c2 in itertools.combinations(
				(c for c in self.surr_cells if c.state != State.MINE),
				2
			):
				c1.shared_unkn_surr_cnts[c2] -= 1

	@property
	def surr_cells(self):
		if self._surr_cells is None:
			self._surr_cells = frozenset(
				self.parent_game.game_grid[surr_coords]
				for surr_coords in get_surrounding_coords(
					self.coords,
					self.parent_game.server.dims
				)
			)

		return self._surr_cells

	@property
	def unkn_surr_mine_cnt(self):
		return self._unkn_surr_mine_cnt

	@unkn_surr_mine_cnt.setter
	def unkn_surr_mine_cnt(self, val):
		if val == 0 and self.state == State.EMPTY:
			for cell in self.surr_cells:
				if cell.state == State.UNKNOWN:
					cell.state = State.TO_CLEAR
		self._unkn_surr_mine_cnt = val

	@property
	def unkn_surr_empt_cnt(self):
		if self._unkn_surr_empt_cnt is None:
			self._unkn_surr_empt_cnt = len(self.surr_cells)
		return self._unkn_surr_empt_cnt

	@unkn_surr_empt_cnt.setter
	def unkn_surr_empt_cnt(self, val):
		if val == 0:
			for cell in self.surr_cells:
				if cell.state == State.UNKNOWN:
					cell.state = State.MINE
		self._unkn_surr_empt_cnt = val

	# The exclusive surrounding cells of two shared cells can be set if
	# we're sure one's exclusive cells must all be mines, and the other's
	# must all be clear (with the shared cells' states still unknown).
	def check_exclusive_cells_saturated(self, other_cell):
		mutual_count = self.shared_unkn_surr_cnts[other_cell]
		for (cell1, cell2) in (
			(self, other_cell),
			(other_cell, self)
		):
			if (
				cell1.unkn_surr_mine_cnt < mutual_count and
				cell2.unkn_surr_empt_cnt < mutual_count
			):
				new_empties = cell1.surr_cells - cell2.surr_cells
				new_mines = cell2.surr_cells - cell1.surr_cells
				for cell in new_empties:
					if cell.state == State.UNKNOWN:
						cell.state = State.TO_CLEAR
				for cell in new_mines:
					if cell.state == State.UNKNOWN:
						cell.state = State.MINE
				return

def play_game(dims, mines, repeats=1):
	played_games = []

	for i in range(repeats):
		played_games.append(ReactiveClientCheckShared(
			PythonInternalServer(dims, mines)
		))

	won = 0
	empty_cell_count = count_empty_cells(dims, mines)

	totals = {
		"cells_rem": 0,
		"total_time": 0,
		"wait_time": 0
	}

	avgs = {}

	for game in played_games:
		won += 1 if game.server.win else 0
		totals["cells_rem"] += game.server.cells_rem
		totals["total_time"] += game.total_time
		totals["wait_time"] += game.wait_time

	for stat,val in totals.items():
		avgs[stat] = val / repeats

	log(1,
		"Won {}/{} games ({:.5}%)\n"
		"Avg. cells cleared: {:.5}/{} ({:.5}%)\n"
		"Avg. time: {:.5}s (waiting {:.5}s)".format(
			won,
			repeats,
			100 * won / repeats,
			empty_cell_count - avgs["cells_rem"],
			empty_cell_count,
			100 * (empty_cell_count - avgs["cells_rem"]) / empty_cell_count,
			avgs["total_time"],
			avgs["wait_time"]
		)
	)

if __name__ == '__main__':
	play_game((6, 6), 2, 100)
