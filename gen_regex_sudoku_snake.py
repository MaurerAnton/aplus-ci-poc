#!/usr/bin/env python3
"""
Generate regex.a+, sudoku.a+, and snake.a+ with proper KAPL byte encoding.
"""

import os

OUTDIR = '/home/bym/aplus-ci-poc'

# KAPL byte mappings
A = chr(0xfb)    # ← assign
P = chr(0xd5)    # ⎕ print/quad
C = chr(0xe3)    # ⍝ comment/lamp
R = chr(0xce)    # ⍴ rho/reshape
D = chr(0xdf)    # ÷ divide
M = chr(0xc1)    # × multiply
I = chr(0xa2)    # ⍳ iota
Ceil = chr(0xab)  # ⌈ ceil
Floor = chr(0xac) # ⌊ floor

def encode(s):
    return s.encode('latin-1')

def write_aplus(filename, content):
    path = os.path.join(OUTDIR, filename)
    data = encode(content)
    with open(path, 'wb') as f:
        f.write(data)
    print(f"Wrote {path} ({len(data)} bytes)")


# ═══════════════════════════════════════════════════════════════════════
# regex.a+ — NFA Regular Expression Engine
# ═══════════════════════════════════════════════════════════════════════

regex_source = f"""\
{C} regex.a+ - NFA Regular Expression Engine
{C} Thompson construction for NFA from regex patterns
{C} Supports: concatenation (ab), alternation (a|b), Kleene star (a*), literals
{C}
{C} NFA representation: flat transition array [from,char,to,...]
{C} Epsilon transitions use char code 0 (null)
{C}

{C} ====== NFA Builder ======
{C} Each fragment has: start_state, accept_state
{C} Global counter for next state id
next_id{A}0
nfa_trans{A}5000{R}0    {C} transition storage
nfa_tc{A}0               {C} transition count (triples)

{C} Add a transition: from --char--> to
add_trans{{f;ch;t}}: {{
  nfa_trans[nfa_tc]{A}f
  nfa_trans[nfa_tc+1]{A}ch
  nfa_trans[nfa_tc+2]{A}t
  nfa_tc{A}nfa_tc+3
}}

{C} Create a new state and return its id
new_state{{}}: {{
  s{A}next_id
  next_id{A}next_id+1
  s
}}

{C} Build NFA for a single literal character
build_literal{{ch}}: {{
  s{A}new_state{{}}
  a{A}new_state{{}}
  add_trans{{s;ch;a}}
  {C} Return start and accept as 2-element result
  s,a
}}

{C} Build NFA for concatenation of two fragments
build_concat{{s1;a1;s2;a2}}: {{
  add_trans{{a1;0;s2}}     {C} epsilon from a1 to s2
  s1,a2
}}

{C} Build NFA for alternation of two fragments
build_alt{{s1;a1;s2;a2}}: {{
  s{A}new_state{{}}
  a{A}new_state{{}}
  add_trans{{s;0;s1}}      {C} epsilon from new start to s1
  add_trans{{s;0;s2}}      {C} epsilon from new start to s2
  add_trans{{a1;0;a}}      {C} epsilon from a1 to new accept
  add_trans{{a2;0;a}}      {C} epsilon from a2 to new accept
  s,a
}}

{C} Build NFA for Kleene star of a fragment
build_star{{s1;a1}}: {{
  s{A}new_state{{}}
  a{A}new_state{{}}
  add_trans{{s;0;s1}}      {C} epsilon from new start to s1
  add_trans{{s;0;a}}       {C} epsilon bypass (zero repetitions)
  add_trans{{a1;0;s1}}     {C} loop back: epsilon from a1 to s1
  add_trans{{a1;0;a}}      {C} epsilon from a1 to new accept
  s,a
}}

{C} ====== Regex Parser ======
{C} Parses regex pattern (array of char codes)
{C} Returns: start_state, accept_state (NFA fragment for entire pattern)

{C} Pattern and position globals
pat{A}0{R}0
pat_pos{A}0
pat_len{A}0

{C} Initialize parser with a pattern
regex_init{{pattern}}: {{
  pat{A}pattern
  pat_pos{A}0
  pat_len{A}{R} pattern
  next_id{A}0
  nfa_tc{A}0
  nfa_trans{A}5000{R}0
}}

{C} Get current char, 0 if at end
peek{{}}: {{
  if (pat_pos<pat_len) {{ pat[pat_pos] }} else {{ 0 }}
}}

{C} Advance and return current char
advance{{}}: {{
  ch{A}peek{{}}
  pat_pos{A}pat_pos+1
  ch
}}

{C} Forward declaration: parse_expr
{C} Actually A+ doesn't have forward decl. We reorder.

{C} Parse a single unit: literal char, or parenthesized group
parse_unit{{}}: {{
  ch{A}peek{{}}
  {C} Parenthesized group
  if (ch=40) {{
    advance{{}}           {C} skip (
    result{A}parse_alt{{}}  {C} parse alternation inside
    advance{{}}           {C} skip )
    result
  }}
  {C} Literal character
  build_literal{{advance{{}}}}
}}

{C} Parse Kleene star: unit*
parse_star{{}}: {{
  s1a1{A}parse_unit{{}}
  s1{A}s1a1[0]
  a1{A}s1a1[1]
  while (peek{{}}=42) {{
    advance{{}}           {C} skip *
    s1a1{A}build_star{{s1;a1}}
    s1{A}s1a1[0]
    a1{A}s1a1[1]
  }}
  s1,a1
}}

{C} Parse concatenation: unit* unit* ...
parse_concat{{}}: {{
  s1a1{A}parse_star{{}}
  s1{A}s1a1[0]
  a1{A}s1a1[1]
  while ((peek{{}}!=41) & (peek{{}}!=124) & (peek{{}}!=0)) {{
    s2a2{A}parse_star{{}}
    s2{A}s2a2[0]
    a2{A}s2a2[1]
    s1a1{A}build_concat{{s1;a1;s2;a2}}
    s1{A}s1a1[0]
    a1{A}s1a1[1]
  }}
  s1,a1
}}

{C} Parse alternation: concat | concat | ...
parse_alt{{}}: {{
  s1a1{A}parse_concat{{}}
  s1{A}s1a1[0]
  a1{A}s1a1[1]
  while (peek{{}}=124) {{
    advance{{}}           {C} skip |
    s2a2{A}parse_concat{{}}
    s2{A}s2a2[0]
    a2{A}s2a2[1]
    s1a1{A}build_alt{{s1;a1;s2;a2}}
    s1{A}s1a1[0]
    a1{A}s1a1[1]
  }}
  s1,a1
}}

{C} Parse full regex pattern
regex_parse{{pattern}}: {{
  regex_init{{pattern}}
  parse_alt{{}}
}}

{C} ====== NFA Simulation ======
{C} Simulate NFA on an input string (array of char codes)
{C} Returns 1 if match, 0 if no match

{C} Compute epsilon closure of a set of states
{C} cur_states: array where cur_states[state_id]=1 if active
{C} We use a fixed-size boolean array
epsilon_closure{{states;nstates}}: {{
  {C} Iterative fixed-point: while changes happen
  changed{A}1
  while (changed) {{
    changed{A}0
    i{A}0
    while (i<nstates) {{
      if (states[i]=1) {{
        {C} Follow epsilon transitions from state i
        j{A}0
        while (j<nfa_tc) {{
          if ((nfa_trans[j]=i) & (nfa_trans[j+1]=0)) {{
            to{A}nfa_trans[j+2]
            if (states[to]=0) {{
              states[to]{A}1
              changed{A}1
            }}
          }}
          j{A}j+3
        }}
      }}
      i{A}i+1
    }}
  }}
}}

{C} NFA simulation on input string
nfa_match{{start;accept;input_str}}: {{
  inlen{A}{R} input_str
  nstates{A}next_id

  {C} Allocate state arrays (max 200 states should be enough)
  cur{A}nstates{R}0
  nxt{A}nstates{R}0

  {C} Start with epsilon closure of start state
  cur[start]{A}1
  epsilon_closure{{cur;nstates}}

  {C} Process each input character
  pos{A}0
  while (pos<inlen) {{
    ch{A}input_str[pos]

    {C} Clear next states
    k{A}0
    while (k<nstates) {{
      nxt[k]{A}0
      k{A}k+1
    }}

    {C} For each current state, follow matching transitions
    i{A}0
    while (i<nstates) {{
      if (cur[i]=1) {{
        j{A}0
        while (j<nfa_tc) {{
          if ((nfa_trans[j]=i) & (nfa_trans[j+1]=ch)) {{
            nxt[nfa_trans[j+2]]{A}1
          }}
          j{A}j+3
        }}
      }}
      i{A}i+1
    }}

    {C} Epsilon closure on next states
    epsilon_closure{{nxt;nstates}}

    {C} Copy nxt to cur
    i{A}0
    while (i<nstates) {{
      cur[i]{A}nxt[i]
      i{A}i+1
    }}

    pos{A}pos+1
  }}

  {C} Check if accept state is in current set
  cur[accept]
}}

{C} ====== Helper: string to char code array ======
{C} str_to_codes uses a literal array of char codes
{C} ASCII: a=97 b=98 c=99

{C} ====== Self-tests ======

{C} Test 1: match "ab" against pattern "ab" -> should PASS
pat1{A}97 98                    {C} "ab"
str1{A}97 98                    {C} "ab"
result1{A}regex_parse{{pat1}}
start1{A}result1[0]
accept1{A}result1[1]
match1{A}nfa_match{{start1;accept1;str1}}
if (match1=1) {{ {P}"regex: [PASS] literal 'ab' matches 'ab'" }}
else {{ {P}"regex: [FAIL] literal 'ab' should match 'ab'" }}

{C} Test 2: match "aaab" against pattern "a*b" -> should PASS
pat2{A}97 42 98                 {C} "a*b"
str2{A}97 97 97 98              {C} "aaab"
result2{A}regex_parse{{pat2}}
start2{A}result2[0]
accept2{A}result2[1]
match2{A}nfa_match{{start2;accept2;str2}}
if (match2=1) {{ {P}"regex: [PASS] 'a*b' matches 'aaab'" }}
else {{ {P}"regex: [FAIL] 'a*b' should match 'aaab'" }}

{C} Test 3: match "ac" against pattern "a(b|c)" -> should PASS
pat3{A}97 40 98 124 99 41       {C} "a(b|c)"
str3{A}97 99                    {C} "ac"
result3{A}regex_parse{{pat3}}
start3{A}result3[0]
accept3{A}result3[1]
match3{A}nfa_match{{start3;accept3;str3}}
if (match3=1) {{ {P}"regex: [PASS] 'a(b|c)' matches 'ac'" }}
else {{ {P}"regex: [FAIL] 'a(b|c)' should match 'ac'" }}

{C} Test 4: reject "ab" against pattern "a(b|c)" -> should FAIL
pat4{A}97 40 98 124 99 41       {C} "a(b|c)"
str4{A}97 98                    {C} "ab"
result4{A}regex_parse{{pat4}}
start4{A}result4[0]
accept4{A}result4[1]
match4{A}nfa_match{{start4;accept4;str4}}
if (match4=0) {{ {P}"regex: [PASS] 'a(b|c)' rejects 'ab'" }}
else {{ {P}"regex: [FAIL] 'a(b|c)' should reject 'ab'" }}

{C} Test 5: match empty string against "a*"
pat5{A}97 42                    {C} "a*"
str5{A}0{R}0                    {C} empty string
result5{A}regex_parse{{pat5}}
start5{A}result5[0]
accept5{A}result5[1]
match5{A}nfa_match{{start5;accept5;str5}}
if (match5=1) {{ {P}"regex: [PASS] 'a*' matches empty string" }}
else {{ {P}"regex: [FAIL] 'a*' should match empty string" }}

{C} Test 6: match "abc" against "a*b*c*"
pat6{A}97 42 98 42 99 42        {C} "a*b*c*"
str6{A}97 98 99                 {C} "abc"
result6{A}regex_parse{{pat6}}
start6{A}result6[0]
accept6{A}result6[1]
match6{A}nfa_match{{start6;accept6;str6}}
if (match6=1) {{ {P}"regex: [PASS] 'a*b*c*' matches 'abc'" }}
else {{ {P}"regex: [FAIL] 'a*b*c*' should match 'abc'" }}

{P}"regex: all tests done"
"""

write_aplus('regex.a+', regex_source)


# ═══════════════════════════════════════════════════════════════════════
# sudoku.a+ — Backtracking Sudoku Solver
# ═══════════════════════════════════════════════════════════════════════

sudoku_source = f"""\
{C} sudoku.a+ - Backtracking Sudoku Solver
{C} 9x9 grid, backtracking with constraints
{C}
{C} Puzzle: 0 = empty cell
{C} Known solvable puzzle (from Wikipedia "Sudoku" - first example)
{C} . 5 3 . . 7 . . .
{C} 6 . . 1 9 5 . . .
{C} . 9 8 . . . . 6 .
{C} 8 . . . 6 . . . 3
{C} 4 . . 8 . 3 . . 1
{C} 7 . . . 2 . . . 6
{C} . 6 . . . . 2 8 .
{C} . . . 4 1 9 . . 5
{C} . . . . 8 . . 7 9

{C} Initialize puzzle (0=empty, row-major)
puzzle{A}0 5 3 0 0 7 0 0 0 6 0 0 1 9 5 0 0 0 0 9 8 0 0 0 0 6 0 8 0 0 0 6 0 0 0 3 4 0 0 8 0 3 0 0 1 7 0 0 0 2 0 0 0 6 0 6 0 0 0 0 2 8 0 0 0 0 4 1 9 0 0 5 0 0 0 0 8 0 0 7 9

{P}"Sudoku puzzle:"
row_p{A}0
while (row_p<9) {{
  out_p{A}""
  col_p{A}0
  while (col_p<9) {{
    val{A}puzzle[row_p*9+col_p]
    if (val=0) {{ out_p{A}out_p,"." }} else {{ out_p{A}out_p,val }}
    col_p{A}col_p+1
  }}
  {P} out_p
  row_p{A}row_p+1
}}

{C} Check if placing digit d at row r, col c is valid
is_valid{{grid;r;c;d}}: {{
  ok{A}1
  {C} Check row
  j{A}0
  while ((j<9) & ok) {{
    if (grid[r*9+j]=d) {{ ok{A}0 }}
    j{A}j+1
  }}
  {C} Check column
  j{A}0
  while ((j<9) & ok) {{
    if (grid[j*9+c]=d) {{ ok{A}0 }}
    j{A}j+1
  }}
  {C} Check 3x3 box
  br{A}(r{D}3)*3
  bc{A}(c{D}3)*3
  i{A}0
  while ((i<3) & ok) {{
    j{A}0
    while ((j<3) & ok) {{
      if (grid[(br+i)*9+(bc+j)]=d) {{ ok{A}0 }}
      j{A}j+1
    }}
    i{A}i+1
  }}
  ok
}}

{C} Solve using backtracking
{C} Returns 1 if solved, 0 if no solution
{C} Modifies grid in place
solve{{grid;pos}}: {{
  {C} Find next empty cell
  while ((pos<81) & (grid[pos]!=0)) {{
    pos{A}pos+1
  }}
  {C} Track result - A+ has no early return, so use variable
  result{A}0
  if (pos>=81) {{ result{A}1 }}
  if (result=0) {{
    r{A}pos{D}9
    c{A}pos-(r*9)
    d{A}1
    while ((d<=9) & (result=0)) {{
      if (is_valid{{grid;r;c;d}}=1) {{
        grid[pos]{A}d
        if (solve{{grid;pos+1}}=1) {{ result{A}1 }}
        if (result=0) {{ grid[pos]{A}0 }}
      }}
      d{A}d+1
    }}
  }}
  result
}}

{C} Work on a copy for solving
grid{A}81{R}0
k{A}0
while (k<81) {{
  grid[k]{A}puzzle[k]
  k{A}k+1
}}

solved{A}solve{{grid;0}}

if (solved=1) {{
  {P}""
  {P}"Solved Sudoku:"
  r2{A}0
  while (r2<9) {{
    out2{A}""
    c2{A}0
    while (c2<9) {{
      out2{A}out2,grid[r2*9+c2]
      c2{A}c2+1
    }}
    {P} out2
    r2{A}r2+1
  }}
}} else {{
  {P}"sudoku: [FAIL] No solution found"
}}

{C} ====== Self-tests ======

{C} Test: all rows have digits 1-9 (no zeros, no duplicates)
row_ok{A}1
r3{A}0
while ((r3<9) & row_ok) {{
  {C} Check each row has exactly digits 1-9
  seen{A}10{R}0
  c3{A}0
  while (c3<9) {{
    v{A}grid[r3*9+c3]
    if ((v<1) | (v>9)) {{ row_ok{A}0 }}
    seen[v]{A}seen[v]+1
    c3{A}c3+1
  }}
  d2{A}1
  while (d2<=9) {{
    if (seen[d2]!=1) {{ row_ok{A}0 }}
    d2{A}d2+1
  }}
  r3{A}r3+1
}}
if (row_ok) {{ {P}"sudoku: [PASS] all rows have digits 1-9" }}
else {{ {P}"sudoku: [FAIL] row constraint violated" }}

{C} Test: all columns have digits 1-9
col_ok{A}1
c4{A}0
while ((c4<9) & col_ok) {{
  seen2{A}10{R}0
  r4{A}0
  while (r4<9) {{
    v2{A}grid[r4*9+c4]
    if ((v2<1) | (v2>9)) {{ col_ok{A}0 }}
    seen2[v2]{A}seen2[v2]+1
    r4{A}r4+1
  }}
  d3{A}1
  while (d3<=9) {{
    if (seen2[d3]!=1) {{ col_ok{A}0 }}
    d3{A}d3+1
  }}
  c4{A}c4+1
}}
if (col_ok) {{ {P}"sudoku: [PASS] all columns have digits 1-9" }}
else {{ {P}"sudoku: [FAIL] column constraint violated" }}

{C} Test: all 3x3 boxes have digits 1-9
box_ok{A}1
br2{A}0
while ((br2<9) & box_ok) {{
  seen3{A}10{R}0
  r5{A}0
  while (r5<3) {{
    c5{A}0
    while (c5<3) {{
      br_row{A}(br2{D}3)*3+r5
      br_col{A}(br2-(br2{D}3)*3)*3+c5
      v3{A}grid[br_row*9+br_col]
      if ((v3<1) | (v3>9)) {{ box_ok{A}0 }}
      seen3[v3]{A}seen3[v3]+1
      c5{A}c5+1
    }}
    r5{A}r5+1
  }}
  d4{A}1
  while (d4<=9) {{
    if (seen3[d4]!=1) {{ box_ok{A}0 }}
    d4{A}d4+1
  }}
  br2{A}br2+1
}}
if (box_ok) {{ {P}"sudoku: [PASS] all 3x3 boxes have digits 1-9" }}
else {{ {P}"sudoku: [FAIL] box constraint violated" }}

{P}"sudoku: all tests done"
"""

write_aplus('sudoku.a+', sudoku_source)


# ═══════════════════════════════════════════════════════════════════════
# snake.a+ — ASCII Snake Game
# ═══════════════════════════════════════════════════════════════════════

snake_source = f"""\
{C} snake.a+ - ASCII Snake Game
{C} 20x15 grid, snake starts center moving right
{C} Food at pseudo-random positions
{C} Pre-programmed moves for demo

W{A}20     {C} grid width
H{A}15     {C} grid height
STEPS{A}30 {C} demo steps

{C} Snake body: array of positions [x1,y1,x2,y2,...,xN,yN]
{C} Max length 100
snake_x{A}100{R}0
snake_y{A}100{R}0
snake_len{A}0
food_x{A}0
food_y{A}0
dir_x{A}1     {C} 1=right, -1=left, 0=no movement
dir_y{A}0     {C} 0=no movement, -1=up, 1=down

{C} Pseudo-random seed
seed{A}12345

{C} Simple LCG pseudo-random: seed = (seed * 1103515245 + 12345) mod 2^31
{C} Return seed mod n
rand_mod{{n}}: {{
  seed{A}seed*11035+seed*15245+12345
  seed{A}seed - ((seed{D}2147483648)*2147483648)
  seed - ((seed{D}n)*n)
}}

{C} Place food at random position not occupied by snake
place_food{{}}: {{
  placed{A}0
  while (placed=0) {{
    fx{A}rand_mod{{W}}
    fy{A}rand_mod{{H}}
    {C} Check if position is occupied by snake
    collision{A}0
    i{A}0
    while (i<snake_len) {{
      if ((snake_x[i]=fx) & (snake_y[i]=fy)) {{ collision{A}1 }}
      i{A}i+1
    }}
    if (collision=0) {{
      food_x{A}fx
      food_y{A}fy
      placed{A}1
    }}
  }}
}}

{C} Initialize snake at center, length 3, moving right
init_snake{{}}: {{
  snake_len{A}3
  start_x{A}W{D}2
  start_y{A}H{D}2
  snake_x[0]{A}start_x
  snake_y[0]{A}start_y
  snake_x[1]{A}start_x-1
  snake_y[1]{A}start_y
  snake_x[2]{A}start_x-2
  snake_y[2]{A}start_y
  dir_x{A}1
  dir_y{A}0
  place_food{{}}
}}

{C} Check if position (x,y) is part of snake body
is_snake{{x;y}}: {{
  found{A}0
  i{A}0
  while ((i<snake_len) & (found=0)) {{
    if ((snake_x[i]=x) & (snake_y[i]=y)) {{ found{A}1 }}
    i{A}i+1
  }}
  found
}}

{C} Print current grid
print_grid{{}}: {{
  y{A}0
  while (y<H) {{
    out{A}""
    x{A}0
    while (x<W) {{
      if (is_snake{{x;y}}=1) {{ out{A}out,"#" }}
      if ((food_x=x) & (food_y=y)) {{ out{A}out,"@" }}
      if ((is_snake{{x;y}}=0) & ((food_x!=x) | (food_y!=y))) {{ out{A}out,"." }}
      x{A}x+1
    }}
    {P} out
    y{A}y+1
  }}
}}

{C} Move snake one step, return 0 if game over, 1 if ok
move_snake{{}}: {{
  alive{A}1

  {C} Calculate new head position
  new_x{A}snake_x[0]+dir_x
  new_y{A}snake_y[0]+dir_y

  {C} Check wall collision
  if ((new_x<0) | (new_x>=W) | (new_y<0) | (new_y>=H)) {{ alive{A}0 }}

  {C} Check self collision
  growing{A}0
  if ((new_x=food_x) & (new_y=food_y)) {{ growing{A}1 }}

  {C} Check collision with body
  i{A}0
  if (growing=1) {{ limit{A}snake_len }} else {{ limit{A}snake_len-1 }}
  while ((i<limit) & alive) {{
    if ((snake_x[i]=new_x) & (snake_y[i]=new_y)) {{ alive{A}0 }}
    i{A}i+1
  }}

  {C} Only move if still alive
  if (alive=1) {{
    {C} Shift body
    i{A}snake_len-1
    while (i>0) {{
      snake_x[i]{A}snake_x[i-1]
      snake_y[i]{A}snake_y[i-1]
      i{A}i-1
    }}

    {C} Place new head
    snake_x[0]{A}new_x
    snake_y[0]{A}new_y

    {C} Check food
    if (growing=1) {{
      snake_x[snake_len]{A}snake_x[snake_len-1]
      snake_y[snake_len]{A}snake_y[snake_len-1]
      snake_len{A}snake_len+1
      place_food{{}}
    }}
  }}

  alive
}}

{C} Set direction from pre-programmed move char
{C} w=up, a=left, s=down, d=right
set_dir{{ch}}: {{
  if (ch=119) {{ dir_x{A}0; dir_y{A}-1 }}     {C} w = up
  if (ch=97)  {{ dir_x{A}-1; dir_y{A}0 }}     {C} a = left
  if (ch=115) {{ dir_x{A}0; dir_y{A}1 }}      {C} s = down
  if (ch=100) {{ dir_x{A}1; dir_y{A}0 }}      {C} d = right
}}

{C} ====== Demo: pre-programmed moves ======
{C} Sequence: right, right, right, down, down, down, left, etc.
{C} Moves as char codes: d d d d d s s s s s a a a a a w w w w w
moves{A}100 100 100 100 100 115 115 115 115 115 97 97 97 97 97 119 119 119 119 119 100 100 100 100 100 115 115 115 115 115
moves_len{A}30

init_snake{{}}

{P}""
{P}"=== Snake Game Demo ==="
{P}"Grid: 20x15, #=snake, @=food, .=empty"
{P}""

print_grid{{}}
{P}"Initial state - snake length: "
{P} snake_len

step{A}0
alive{A}1
while ((step<STEPS) & alive) {{
  set_dir{{moves[step]}}
  alive{A}move_snake{{}}
  if (alive) {{
    {P}""
    {P}"Step: "
    {P} step+1
    print_grid{{}}
    {P}"Length: "
    {P} snake_len
  }}
  step{A}step+1
}}

if (alive=0) {{
  {P}"snake: GAME OVER - hit wall or self"
}} else {{
  {P}"snake: Demo complete"
}}

{C} ====== Self-tests ======
{P}""
{P}"=== Snake Self-tests ==="

{C} Re-init for tests
init_snake{{}}

{C} Test: verify snake moves right correctly
init_x{A}snake_x[0]
init_y{A}snake_y[0]
set_dir{{100}}   {C} d = right
move_snake{{}}
if ((snake_x[0]=init_x+1) & (snake_y[0]=init_y)) {{
  {P}"snake: [PASS] snake moves right correctly"
}} else {{
  {P}"snake: [FAIL] snake movement wrong"
}}

{C} Test: verify snake grows after eating food
{C} Place food right in front (manually) and move into it
init_snake{{}}
food_x{A}snake_x[0]+1
food_y{A}snake_y[0]
old_len{A}snake_len
set_dir{{100}}   {C} d = right
move_snake{{}}
if (snake_len>old_len) {{
  {P}"snake: [PASS] snake grows after eating food"
}} else {{
  {P}"snake: [FAIL] snake did not grow"
}}

{C} Test: verify self-collision detection
{C} Snake of length 1 can never collide with self
init_snake{{}}
snake_len{A}1
snake_x[0]{A}10
snake_y[0]{A}7
set_dir{{100}}   {C} right
r{A}move_snake{{}}
if (r=1) {{ {P}"snake: [PASS] no self-collision with length=1" }}
else {{ {P}"snake: [FAIL] false self-collision" }}

{C} Test: verify wall collision (move into left wall)
init_snake{{}}
snake_len{A}1
snake_x[0]{A}0
snake_y[0]{A}7
set_dir{{97}}    {C} a = left
r2{A}move_snake{{}}
if (r2=0) {{ {P}"snake: [PASS] wall collision detected" }}
else {{ {P}"snake: [FAIL] wall collision missed" }}

{P}"snake: all tests done"
"""

write_aplus('snake.a+', snake_source)

print("\nAll three .a+ files generated successfully!")
