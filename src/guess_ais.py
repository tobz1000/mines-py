#!/usr/bin/env python3
import itertools
import functools

from reactive_ai import *

# Just finds first cleared cell with surrounding unknown empties.
class ReactiveClientGuess(ReactiveClient):
	# TODO: Refactor to use the function in ReactiveClientExhaustiveTest, and
	# see if speed is noticeably affected. If not, just replace all the
	# get_adjacent_unknown_cells functions with that one.
	def get_adjacent_unknown_cells(self):
		# TODO: Sometimes returns None; figure out the situation that causes
		# this and see what might be the next best thing to do (just pick random
		# unknown?)
		for surr_empt_cell in self.known_cells[State.EMPTY]:
			if surr_empt_cell.unkn_surr_empt_cnt <= 0:
				continue

			for unk_cell in surr_empt_cell.surr_cells:
				if unk_cell.state == State.UNKNOWN:
					yield (unk_cell, surr_empt_cell)

	def get_guess_cell(self):
		for (unk_cell, surr_empt_cell) in self.get_adjacent_unknown_cells():
			return unk_cell

# For all unknowns next to an empty, choose the one next to fewest empties
class ReactiveClientCountEmpties(ReactiveClientGuess):
	def get_guess_cell(self):
		adjacent_unknowns = set(
			s[0] for s in self.get_adjacent_unknown_cells()
		)

		if len(adjacent_unknowns) == 0:
			return None
		else:
			return min(
				adjacent_unknowns,
				key=lambda c: c.unkn_surr_empt_cnt + c.unkn_surr_mine_cnt
			)

# Just pick something.
class ReactiveClientGuessAny(ReactiveClient):
	def get_guess_cell(self):
		while True:
			cell = self.game_grid[self.random_coords()]
			if cell.state == State.UNKNOWN:
				return cell

# For all unknowns next to an empty, sum the unknown surrounding empty count vs
# the total unknown surrounding count for each cleared empty cell. Choose the
# unknown with the highest ratio; hopefully it's the most likely to be empty.
class ReactiveClientAvgEmpties(ReactiveClientGuess):
	def get_guess_cell(self):
		return self.get_best_scoring_unknown(
			self.get_adjacent_unknown_cells,
			self.empty_ratio
		)

	def get_best_scoring_unknown(self, get_fn, score_fn):
		scores = {}

		for (cell, surr_empties) in get_fn():
			scores[cell] = score_fn(cell, surr_empties)

		if len(scores) == 0:
			return None

		return max(scores.items(), key=lambda c: c[1])[0]

	def get_adjacent_unknown_cells(self):
		unk_cells = {}
		for surr_empt_cell in self.known_cells[State.EMPTY]:
			for unk_cell in (
				c for c in surr_empt_cell.surr_cells if c.state == State.UNKNOWN
			):
				if unk_cell not in unk_cells:
					unk_cells[unk_cell] = []
				unk_cells[unk_cell].append(surr_empt_cell)
		return unk_cells.items()

	def empty_ratio(self, cell, surr_empties):
		empty_count = 0
		mine_count = 0
		for surr in surr_empties:
			empty_count += surr.unkn_surr_empt_cnt
			mine_count += surr.unkn_surr_mine_cnt
		return empty_count / ((empty_count + mine_count) or 1)

class ReactiveClientAvgEmptiesAll(ReactiveClientAvgEmpties):
	landlocked_cell_score = lambda self: 2

	def get_guess_cell(self):
		return self.get_best_scoring_unknown(
			self.get_all_unknown_cells,
			self.empty_ratio_all
		)

	def empty_ratio_all(self, cell, surr_empties):
		surr_empties = list(surr_empties)

		if len(surr_empties) == 0:
			return self.landlocked_cell_score()

		return self.empty_ratio(cell, surr_empties)

	def get_all_unknown_cells(self):
		for coords in self.all_coords():
			cell = self.game_grid[coords]
			if cell.state != State.UNKNOWN:
				continue

			yield (cell, (c for c in cell.surr_cells if c.state == State.EMPTY))

class ReactiveClientAvgEmptiesBalanced(ReactiveClientAvgEmptiesAll):
	def landlocked_cell_score(self):
		return (self.server.cells_rem / self.server.mines) / 10

# TODO: Test every possible mine position; gather statisitcs to find most likely
# candidate. Obviously slow.
class ReactiveClientExhaustiveTest(ReactiveClientAvgEmpties):
	# TODO: add to the cell_state_lookups list in the superclass, instead of
	# replacing it.
	cell_state_lookups = [ State.TO_CLEAR, State.EMPTY, State.MINE ]
	split_edge_cells = False

	def get_adjacent_unknown_cells(self):
		# TODO: Sometimes returns None; figure out the situation that causes
		# this and see what might be the next best thing to do (just pick random
		# unknown?)
		for surr_empt_cell in self.known_cells[State.EMPTY]:
			if surr_empt_cell.unkn_surr_empt_cnt <= 0:
				continue

			for unk_cell in surr_empt_cell.surr_cells:
				if unk_cell.state == State.UNKNOWN:
					yield unk_cell

	def get_guess_cell(self):
		# For each cleared mine, check that this configuration gives it the
		# correct number of new surrounding mines.
		def test_valid(edge_mines):
			for empty_cell in self.known_cells[State.EMPTY]:
				unkn_mine_count = empty_cell.unkn_surr_mine_cnt

				if unkn_mine_count == 0:
					continue

				if unkn_mine_count - len(
					edge_mines & frozenset(empty_cell.surr_cells)
				) != 0:
					return False
			return True

		# Combine sets into disjoint groups. Destructive to supplied 'sets'..
		def combine_overlaps(sets):
			for ((ai, a), (bi, b)) in itertools.combinations(
				enumerate(sets),
				2
			):
				if not a or not b:
					continue

				if not a.isdisjoint(b):
					a |= b
					sets[bi] = None

			return [s for s in sets if s]

		mines_left = self.server.mines - len(self.known_cells[State.MINE])
		edge_cells = frozenset(self.get_adjacent_unknown_cells())
		edge_mine_tally = { c : 0 for c in edge_cells }

		if self.split_edge_cells:
			# Divide edge_cells into groups based on contact with one another.
			edge_cell_sets = combine_overlaps(
				[(set(c.surr_cells) | {c}) & edge_cells for c in edge_cells]
			)
		else:
			edge_cell_sets = [ edge_cells ]

		# For each possible number of mines on the edge, see which combinations
		# are possible, and tally the placement count in each edge cell.
		# TODO: Break up edge mines further to reduce no. of combinations (using
		# edge_cell_sets above)
		# TODO: weight this based on nCr(inner cells, inner mines) for each
		# num_edge_mines value.
		for cell_set in edge_cell_sets:
			for num_edge_mines in range(1, min(len(cell_set), mines_left) + 1):
				for mine_combo in (frozenset(m) for m in itertools.combinations(
					cell_set,
					num_edge_mines
				)):
					if test_valid(mine_combo):
						for cell in mine_combo:
							edge_mine_tally[cell] += 1

		if len(edge_mine_tally) == 0:
			return None

		ret = min(edge_mine_tally.items(), key=lambda c: c[1])[0]
		return ret

class ReactiveClientExhaustiveSplit(ReactiveClientExhaustiveTest):
	split_edge_cells = True