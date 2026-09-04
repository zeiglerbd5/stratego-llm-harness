# Rulebook

## Sec.1 Objective

Capture the enemy Flag, or leave the enemy with no legal Move. Your own rank
identities are hidden from your opponent until revealed in Combat.

## Sec.2 Board

The board is 10x10. Columns are lettered `a`-`j` left to right; rows are
numbered `1`-`10` bottom to top. A square is a column letter followed by a row
number, for example `d7`.

Eight squares are lakes: `c5 c6 d5 d6 g5 g6 h5 h6`. No piece may enter or pass
through a lake.

RED deploys in rows 1-4. BLUE deploys in rows 7-10.

## Sec.3 Movement

One piece moves per turn. All movement is orthogonal - forward, backward, left,
or right. Diagonal movement does not exist in Stratego.

- **Flag** and **Bomb** can never move.
- **Scout** moves any number of empty squares in one straight line, and may end
  that move by attacking an adjacent enemy. It may not jump over any piece.
- **Every other piece** moves exactly one square.

A piece may not move onto a square held by one of your own pieces. Moving onto a
square held by an enemy piece is an attack and starts Combat.

## Sec.4 Combat

When you attack, both pieces reveal their rank. Ranks from highest to lowest:

`Marshal(10) General(9) Colonel(8) Major(7) Captain(6) Lieutenant(5)
Sergeant(4) Miner(3) Scout(2) Spy(1)`

- The lower rank is removed. The winner occupies the square.
- Equal ranks: both pieces are removed.
- **Bomb**: any attacker is removed, *except* a **Miner**, which removes the Bomb.
- **Spy**: if the Spy *attacks* the Marshal, the Marshal is removed. If the
  Marshal attacks the Spy, the Spy is removed. The Spy loses to everything else.
- **Flag**: attacking the Flag captures it and wins the game immediately.

Both pieces stay revealed to both players for the rest of the game.

## Sec.5 Repetition

You may not move a piece back and forth between the same two squares a third
time, and you may not keep a piece confined to three or fewer squares across a
run of its own moves. Shuffling one piece instead of playing is rejected as
illegal.

## Sec.6 Ending the game

The game ends when a Flag is captured, or when the side to move has no legal
Move (that side loses).

If the move cap is reached first, the game is **adjudicated on material**: the
side holding more surviving material wins. A capped game is only a draw if
material is within 2 points. Material values:

`Marshal 10, General 9, Colonel 8, Major 7, Captain 6, Spy 6, Lieutenant 5,
Miner 5, Sergeant 4, Bomb 4, Scout 3, Flag 0`
