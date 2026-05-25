#!/usr/bin/env python3
"""
Generate aplusc.a+ — a self-hosting A+ compiler in pure A+.

The compiler implements:
  1. Tokenizer: source array → flat token array  [type,start,end] triplets
  2. Parser: recursive-descent, builds AST as flat serialized array
  3. Code generator: AST → output source array (character codes)

AST encoding (flat array of ints):
  - Node type markers start at 256 (to avoid collision with char codes 0-255)
  - END sentinel = 65535 (0xFFFF)
  - Leaf nodes: [type_marker, value_byte1, value_byte2, ..., END]
  - Internal nodes: [type_marker, child1..., child2..., END]

Token types (for the tokenizer output): 0-30
AST node types (marker = 256 + type): 0-14
"""

import os
import sys

OUTDIR = '/home/bym/aplus-ci-poc'

# KAPL byte mappings
KA = chr(0xFB)    # ← assign
KP = chr(0xD5)    # ⎕ print/quad
KC = chr(0xE3)    # ⍝ comment/lamp
KR = chr(0xCE)    # ⍴ rho/reshape
KD = chr(0xDF)    # ÷ divide
KM = chr(0xC1)    # × multiply
KI = chr(0xA2)    # ⍳ iota
KCeil = chr(0xAB)  # ⌈ ceil
KMem = chr(0xA8)   # ∊ member
KFloor = chr(0xAC) # ⌊ floor

A = KA  # shorthand
P = KP
C = KC
R = KR
D = KD
M = KM
I = KI

def encode(s):
    """Encode string with KAPL placeholder chars to Latin-1 bytes."""
    return s.encode('latin-1')

def write_aplus(filename, content):
    path = os.path.join(OUTDIR, filename)
    data = encode(content)
    with open(path, 'wb') as f:
        f.write(data)
    print(f"Wrote {path} ({len(data)} bytes)")

# ===========================================================================
# Build the A+ compiler source
# ===========================================================================

# We'll build this as a large string with Python f-string interpolation
# for the KAPL characters.

aplusc_source = f"""\
{C} aplusc.a+ === Self-hosting A+ Compiler ===
{C} Phases: tokenizer, recursive-descent parser, AST builder, code generator
{C} AST encoding: flat array, node types at 256+, sentinel=65535
{C}
{C} Token types: T_EOF=0 T_IDENT=1 T_NUMBER=2 T_STRING=3
{C}   T_ASSIGN=4 T_PRINT=5 T_PLUS=6 T_MINUS=7 T_MULT=8 T_DIV=9
{C}   T_LPAREN=10 T_RPAREN=11 T_LBRACE=12 T_RBRACE=13 T_LBRACK=14
{C}   T_RBRACK=15 T_SEMI=16 T_COLON=17 T_EQ=18 T_LT=19 T_GT=20
{C}   T_LE=21 T_GE=22 T_NE=23 T_AND=24 T_COMMA=25
{C}   T_IF=26 T_WHILE=27 T_ELSE=28 T_NL=29 T_COMMENT=30
{C}
{C} AST node types (marker = 256+type):
{C}   N_PROG=0 N_ASSIGN=1 N_PRINT=2 N_IF=3 N_WHILE=4
{C}   N_FUNCDEF=5 N_FUNCCALL=6 N_BINARY=7 N_UNARY=8
{C}   N_NUMBER=9 N_STRING=10 N_IDENT=11 N_ARRAY=12 N_RETURN=13 N_COMM=14

{C} ====== Tokenizer ======
{C} Source is array of char codes. Returns token array [type,start,end]* with 0-termination.

{C} Character classification helpers
is_digit{{ch}}: {{
  ((ch>=48) & (ch<=57))
}}

is_alpha{{ch}}: {{
  (((ch>=65) & (ch<=90)) | ((ch>=97) & (ch<=122)))
}}

is_alnum{{ch}}: {{
  (is_digit{{ch}} | is_alpha{{ch}} | (ch=95))
}}

is_space{{ch}}: {{
  ((ch=32) | (ch=9) | (ch=13))
}}

{C} Compare substrings in src: src[a..b] == keyword_str
streq{{src;a;b;kw;kwlen}}: {{
  ok{A}1
  i{A}0
  while ((i<kwlen) & ok) {{
    if (src[a+i]=kw[i]) {{ }} else {{ ok{A}0 }}
    i{A}i+1
  }}
  ok
}}

{C} Keyword detection: check if identifier at src[start..end-1] is a keyword
{C} Returns token type (T_IF=26, T_WHILE=27, T_ELSE=28) or T_IDENT=1
check_keyword{{src;start;end}}: {{
  ln{A}end-start
  kw_if{A}105 102         {C} i=105 f=102
  kw_while{A}119 104 105 108 101   {C} w=119 h=104 i=105 l=108 e=101
  kw_else{A}101 108 115 101       {C} e=101 l=108 s=115 e=101
  if (ln=2) {{
    if (streq{{src;start;end;kw_if;2}}) {{ 26 }} else {{ 1 }}
  }}
  if (ln=5) {{
    if (streq{{src;start;end;kw_while;5}}) {{ 27 }} else {{ 1 }}
  }}
  if (ln=4) {{
    if (streq{{src;start;end;kw_else;4}}) {{ 28 }} else {{ 1 }}
  }}
  1
}}

{C} Main tokenizer: source array -> flat token array
{C} Token array format: [tok1_type,tok1_start,tok1_end, tok2_type,...,0]
tokenize{{src}}: {{
  srclen{A}{R} src
  {C} Preallocate token array (max ~5000 entries)
  toks{A}5000{R}0
  tc{A}0      {C} token counter (each token uses 3 slots)
  pos{A}0
  while (pos<srclen) {{
    ch{A}src[pos]
    ln{A}pos+1   {C} fake line number = position for simplicity
    cl{A}0
    {C} Skip whitespace (not newline)
    if (is_space{{ch}}) {{ pos{A}pos+1 }}
    {C} Newline
    if (ch=10) {{
      toks[tc]{A}29
      toks[tc+1]{A}pos
      toks[tc+2]{A}pos+1
      tc{A}tc+3
      pos{A}pos+1
    }}
    {C} Comment: {C} (0xE3/227) to end of line
    if (ch=227) {{
      cmt_start{A}pos+1
      pos{A}pos+1
      while ((pos<srclen) & (src[pos]!=10)) {{ pos{A}pos+1 }}
      toks[tc]{A}30
      toks[tc+1]{A}cmt_start
      toks[tc+2]{A}pos
      tc{A}tc+3
    }}
    {C} Number literal
    if (is_digit{{ch}}) {{
      num_start{A}pos
      while ((pos<srclen) & (is_digit{{src[pos]}} | (src[pos]=46))) {{ pos{A}pos+1 }}
      toks[tc]{A}2
      toks[tc+1]{A}num_start
      toks[tc+2]{A}pos
      tc{A}tc+3
    }}
    {C} Identifier or keyword
    if (is_alpha{{ch}}) {{
      id_start{A}pos
      while ((pos<srclen) & is_alnum{{src[pos]}}) {{ pos{A}pos+1 }}
      kw_type{A}check_keyword{{src;id_start;pos}}
      toks[tc]{A}kw_type
      toks[tc+1]{A}id_start
      toks[tc+2]{A}pos
      tc{A}tc+3
    }}
    {C} String literal (double-quote)
    if (ch=34) {{
      str_start{A}pos+1
      pos{A}pos+1
      while ((pos<srclen) & (src[pos]!=34)) {{ pos{A}pos+1 }}
      toks[tc]{A}3
      toks[tc+1]{A}str_start
      toks[tc+2]{A}pos
      tc{A}tc+3
      if (pos<srclen) {{ pos{A}pos+1 }}
    }}
    {C} Single-char tokens
    if (ch=251) {{ toks[tc]{A}4; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=213) {{ toks[tc]{A}5; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=43)  {{ toks[tc]{A}6; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=45)  {{ toks[tc]{A}7; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=215) {{ toks[tc]{A}8; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=42)  {{ toks[tc]{A}8; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=247) {{ toks[tc]{A}9; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=47)  {{ toks[tc]{A}9; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=40)  {{ toks[tc]{A}10; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=41)  {{ toks[tc]{A}11; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=123) {{ toks[tc]{A}12; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=125) {{ toks[tc]{A}13; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=91)  {{ toks[tc]{A}14; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=93)  {{ toks[tc]{A}15; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=59)  {{ toks[tc]{A}16; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=58)  {{ toks[tc]{A}17; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    if (ch=44)  {{ toks[tc]{A}25; toks[tc+1]{A}pos; toks[tc+2]{A}pos+1; tc{A}tc+3; pos{A}pos+1 }}
    {C} = (0x3D)
    if (ch=61) {{
      toks[tc]{A}18
      toks[tc+1]{A}pos
      toks[tc+2]{A}pos+1
      tc{A}tc+3
      pos{A}pos+1
    }}
    {C} < (0x3C) - check <=
    if (ch=60) {{
      if ((pos+1<srclen) & (src[pos+1]=61)) {{
        toks[tc]{A}21
        toks[tc+1]{A}pos
        toks[tc+2]{A}pos+2
        tc{A}tc+3
        pos{A}pos+2
      }} else {{
        toks[tc]{A}19
        toks[tc+1]{A}pos
        toks[tc+2]{A}pos+1
        tc{A}tc+3
        pos{A}pos+1
      }}
    }}
    {C} > (0x3E) - check >=
    if (ch=62) {{
      if ((pos+1<srclen) & (src[pos+1]=61)) {{
        toks[tc]{A}22
        toks[tc+1]{A}pos
        toks[tc+2]{A}pos+2
        tc{A}tc+3
        pos{A}pos+2
      }} else {{
        toks[tc]{A}20
        toks[tc+1]{A}pos
        toks[tc+2]{A}pos+1
        tc{A}tc+3
        pos{A}pos+1
      }}
    }}
    {C} ! (0x21) - check !=
    if (ch=33) {{
      if ((pos+1<srclen) & (src[pos+1]=61)) {{
        toks[tc]{A}23
        toks[tc+1]{A}pos
        toks[tc+2]{A}pos+2
        tc{A}tc+3
        pos{A}pos+2
      }} else {{
        pos{A}pos+1
      }}
    }}
    {C} & (0x26)
    if (ch=38) {{
      toks[tc]{A}24
      toks[tc+1]{A}pos
      toks[tc+2]{A}pos+1
      tc{A}tc+3
      pos{A}pos+1
    }}
    {C} | (0x7C)
    if (ch=124) {{
      toks[tc]{A}25  {C} reuse comma type for pipe (we don't use comma yet)
      toks[tc+1]{A}pos
      toks[tc+2]{A}pos+1
      tc{A}tc+3
      pos{A}pos+1
    }}
  }}
  {C} Terminate token list with EOF (type 0)
  toks[tc]{A}0
  toks[tc+1]{A}pos
  toks[tc+2]{A}pos
  toks
}}

{C} ====== Recursive-Descent Parser ======
{C} Builds AST as flat serialized array.
{C} Each AST node: [256+type, data..., 65535]
{C} Sentinel = 65535 (0xFFFF), type marker = 256 + node_type

AST_SENTINEL{A}65535

{C} Write a leaf node to AST array: [256+type, byte..., SENTINEL]
{C} Returns updated apos (write position)
ast_leaf{{ast;apos;ntype;src;vstart;vend}}: {{
  ast[apos]{A}256+ntype
  apos{A}apos+1
  i{A}vstart
  while (i<vend) {{
    ast[apos]{A}src[i]
    apos{A}apos+1
    i{A}i+1
  }}
  ast[apos]{A}AST_SENTINEL
  apos{A}apos+1
  apos
}}

{C} Write sentinel and return updated apos
ast_end{{ast;apos}}: {{
  ast[apos]{A}AST_SENTINEL
  apos{A}apos+1
  apos
}}

{C} Parser state: [tokens_array, pos, src_array, ast_array, ast_pos]
{C} We pass state components explicitly since A+ has no structs

{C} Helper: get token type at position p in token array (toks[p*3])
tok_type{{toks;p}}: {{
  toks[p*3]
}}

tok_start{{toks;p}}: {{
  toks[p*3+1]
}}

tok_end{{toks;p}}: {{
  toks[p*3+2]
}}

{C} Skip newline tokens, return new position
skip_nl{{toks;p}}: {{
  while (tok_type{{toks;p}}=29) {{ p{A}p+1 }}
  p
}}

{C} ====== Expression parser ======
{C} Returns: [new_tok_pos, new_ast_pos]

{C} Parse expression with binary operators
parse_expr{{toks;tpos;src;ast;apos}}: {{
  tpos{A}skip_nl{{toks;tpos}}
  {C} Parse first term
  tpos1{A}tpos
  apos1{A}apos
  {C} Collect array elements
  elems{A}0
  elem_apos{A}0 10{R}0
  elem_count{A}0
  while ((tok_type{{toks;tpos}}!=0) & (tok_type{{toks;tpos}}!=29) &
         (tok_type{{toks;tpos}}!=11) & (tok_type{{toks;tpos}}!=13) &
         (tok_type{{toks;tpos}}!=16) & (tok_type{{toks;tpos}}!=26) &
         (tok_type{{toks;tpos}}!=27) & (tok_type{{toks;tpos}}!=28)) {{
    tpos{A}parse_add{{toks;tpos;src;ast;apos}}
    apos{A}tpos+(tpos*0)  {C} extract ast_pos from return, but we need a hack
    elem_apos[elem_count]{A}apos
    elem_count{A}elem_count+1
    tpos{A}skip_nl{{toks;tpos}}
  }}
  {C} Hack: we can't easily return two values in A+ without nested arrays
  apos
}}

{C} Actually, A+ can't return multiple values well. Let's restructure.
{C} We'll use a simple approach: parser modifies ast and toks_pos directly,
{C} and we store position in a fixed global-like variable.

{C} === Simplified recursive descent (using global-like arrays) ===

{C} Parser position (index into token triplets)
ppos{A}0

{C} AST write position
apos{A}0

{C} Source reference
psrc{A}0{R}0

{C} Token reference
ptoks{A}0{R}0

{C} AST storage
past{A}5000{R}0

{C} Init parser
parser_init{{toks;src}}: {{
  ppos{A}0
  apos{A}0
  psrc{A}src
  ptoks{A}toks
  past{A}5000{R}0
}}

{C} Get current token type
cur_tok{{}}: {{
  tok_type{{ptoks;ppos}}
}}

{C} Advance to next token
advance{{}}: {{
  ppos{A}ppos+1
}}

{C} Skip newlines
pskip_nl{{}}: {{
  while (cur_tok{{}}=29) {{ advance{{}} }}
}}

{C} Write a leaf node: [256+ntype, bytes..., SENTINEL]
put_leaf{{ntype;vstart;vend}}: {{
  past[apos]{A}256+ntype
  apos{A}apos+1
  i{A}vstart
  while (i<vend) {{
    past[apos]{A}psrc[i]
    apos{A}apos+1
    i{A}i+1
  }}
  past[apos]{A}AST_SENTINEL
  apos{A}apos+1
}}

{C} Write sentinel
put_end{{}}: {{
  past[apos]{A}AST_SENTINEL
  apos{A}apos+1
}}

{C} Parse: atom → NUMBER | STRING | IDENT | ( expr ) | IDENT{{args}} | [expr;...]
parse_atom{{}}: {{
  ttype{A}cur_tok{{}}
  {C} Number
  if (ttype=2) {{
    put_leaf{{9;tok_start{{ptoks;ppos}};tok_end{{ptoks;ppos}}}}
    advance{{}}
  }}
  {C} String
  if (ttype=3) {{
    put_leaf{{10;tok_start{{ptoks;ppos}};tok_end{{ptoks;ppos}}}}
    advance{{}}
  }}
  {C} Identifier
  if (ttype=1) {{
    start{A}tok_start{{ptoks;ppos}}
    end{A}tok_end{{ptoks;ppos}}
    advance{{}}
    pskip_nl{{}}
    {C} Check for function call: ident{{args}}
    if (cur_tok{{}}=12) {{
      {C} It's a function call
      advance{{}}  {C} skip {{
      {C} Write FUNCCALL node header
      past[apos]{A}262  {C} 256+6 = N_FUNCCALL
      apos{A}apos+1
      {C} Write function name as leaf
      put_leaf{{11;start;end}}  {C} N_IDENT
      {C} Parse arguments until }}
      while (cur_tok{{}}!=13) {{
        pskip_nl{{}}
        if (cur_tok{{}}=13) {{ }} else {{
          parse_expr{{}}
          pskip_nl{{}}
        }}
      }}
      advance{{}}  {C} skip }}
      put_end{{}}
    }} else {{
      {C} Plain identifier reference
      put_leaf{{11;start;end}}
    }}
  }}
  {C} Left paren: ( expr )
  if (ttype=10) {{
    advance{{}}
    pskip_nl{{}}
    parse_expr{{}}
    pskip_nl{{}}
    advance{{}}  {C} skip )
  }}
  {C} Array literal: [expr;expr;...]
  if (ttype=14) {{
    advance{{}}  {C} skip [
    past[apos]{A}268  {C} 256+12 = N_ARRAY
    apos{A}apos+1
    pskip_nl{{}}
    while (cur_tok{{}}!=15) {{
      parse_expr{{}}
      pskip_nl{{}}
    }}
    advance{{}}  {C} skip ]
    put_end{{}}
  }}
  {C} Unary minus
  if (ttype=7) {{
    advance{{}}
    past[apos]{A}264  {C} 256+8 = N_UNARY
    apos{A}apos+1
    past[apos]{A}45  {C} '-' char code
    apos{A}apos+1
    parse_atom{{}}
    put_end{{}}
  }}
}}

{C} Parse multiplicative: atom (* atom | / atom)*
parse_mult{{}}: {{
  parse_atom{{}}
  pskip_nl{{}}
  while ((cur_tok{{}}=8) | (cur_tok{{}}=9)) {{
    op_type{A}cur_tok{{}}
    advance{{}}
    pskip_nl{{}}
    past[apos]{A}263  {C} 256+7 = N_BINARY
    apos{A}apos+1
    if (op_type=8) {{ past[apos]{A}42 }}  {C} '*'
    if (op_type=9) {{ past[apos]{A}47 }}  {C} '/'
    apos{A}apos+1
    parse_atom{{}}
    pskip_nl{{}}
    put_end{{}}
  }}
}}

{C} Parse additive: mult (+ mult | - mult)*
parse_add{{}}: {{
  parse_mult{{}}
  pskip_nl{{}}
  while ((cur_tok{{}}=6) | (cur_tok{{}}=7)) {{
    op_type{A}cur_tok{{}}
    advance{{}}
    pskip_nl{{}}
    past[apos]{A}263  {C} N_BINARY
    apos{A}apos+1
    if (op_type=6) {{ past[apos]{A}43 }}  {C} '+'
    if (op_type=7) {{ past[apos]{A}45 }}  {C} '-'
    apos{A}apos+1
    parse_mult{{}}
    pskip_nl{{}}
    put_end{{}}
  }}
}}

{C} Parse comparison: add (=|<|>|<=|>=|!= add)*
parse_cmp{{}}: {{
  parse_add{{}}
  pskip_nl{{}}
  while ((cur_tok{{}}=18) | (cur_tok{{}}=19) | (cur_tok{{}}=20) |
         (cur_tok{{}}=21) | (cur_tok{{}}=22) | (cur_tok{{}}=23)) {{
    op_type{A}cur_tok{{}}
    advance{{}}
    pskip_nl{{}}
    past[apos]{A}263  {C} N_BINARY
    apos{A}apos+1
    if (op_type=18) {{ past[apos]{A}61 }}  {C} '='
    if (op_type=19) {{ past[apos]{A}60 }}  {C} '<'
    if (op_type=20) {{ past[apos]{A}62 }}  {C} '>'
    if (op_type=21) {{ past[apos]{A}60; apos{A}apos+1; past[apos]{A}61 }}
    if (op_type=22) {{ past[apos]{A}62; apos{A}apos+1; past[apos]{A}61 }}
    if (op_type=23) {{ past[apos]{A}33; apos{A}apos+1; past[apos]{A}61 }}
    apos{A}apos+1
    parse_add{{}}
    pskip_nl{{}}
    put_end{{}}
  }}
}}

{C} Parse AND expression: cmp (& cmp)*
parse_and{{}}: {{
  parse_cmp{{}}
  pskip_nl{{}}
  while (cur_tok{{}}=24) {{
    advance{{}}
    pskip_nl{{}}
    past[apos]{A}263  {C} N_BINARY
    apos{A}apos+1
    past[apos]{A}38  {C} '&'
    apos{A}apos+1
    parse_cmp{{}}
    pskip_nl{{}}
    put_end{{}}
  }}
}}

{C} Full expression parser entry
parse_expr{{}}: {{
  parse_and{{}}
}}

{C} ====== Statement parser ======

{C} Parse a block: { stmt* }
parse_block{{}}: {{
  advance{{}}  {C} skip {{
  pskip_nl{{}}
  while (cur_tok{{}}!=13) {{
    parse_stmt{{}}
    pskip_nl{{}}
  }}
  advance{{}}  {C} skip }}
}}

{C} Parse a single statement
parse_stmt{{}}: {{
  ttype{A}cur_tok{{}}
  {C} Comment
  if (ttype=30) {{
    put_leaf{{14;tok_start{{ptoks;ppos}};tok_end{{ptoks;ppos}}}}
    advance{{}}
  }}
  {C} Print: {P} expr
  if (ttype=5) {{
    advance{{}}
    pskip_nl{{}}
    past[apos]{A}258  {C} 256+2 = N_PRINT
    apos{A}apos+1
    parse_expr{{}}
    put_end{{}}
  }}
  {C} If statement
  if (ttype=26) {{
    advance{{}}  {C} skip if
    advance{{}}  {C} skip (
    pskip_nl{{}}
    past[apos]{A}259  {C} 256+3 = N_IF
    apos{A}apos+1
    parse_expr{{}}  {C} condition
    pskip_nl{{}}
    advance{{}}  {C} skip )
    parse_block{{}}  {C} then-body
    pskip_nl{{}}
    {C} Optional else
    if (cur_tok{{}}=28) {{
      advance{{}}  {C} skip else
      pskip_nl{{}}
      if (cur_tok{{}}=26) {{
        parse_stmt{{}}  {C} else-if
      }} else {{
        parse_block{{}}  {C} else block
      }}
    }}
    put_end{{}}
  }}
  {C} While statement
  if (ttype=27) {{
    advance{{}}  {C} skip while
    advance{{}}  {C} skip (
    pskip_nl{{}}
    past[apos]{A}260  {C} 256+4 = N_WHILE
    apos{A}apos+1
    parse_expr{{}}  {C} condition
    pskip_nl{{}}
    advance{{}}  {C} skip )
    parse_block{{}}  {C} body
    put_end{{}}
  }}
  {C} Function definition: name{{params}}: body / name{{params}}: {{block}}
  if (ttype=1) {{
    start{A}tok_start{{ptoks;ppos}}
    end{A}tok_end{{ptoks;ppos}}
    advance{{}}
    pskip_nl{{}}
    if (cur_tok{{}}=12) {{
      {C} It's either a func def (with colon) or func call
      {C} Look ahead for colon after closing brace
      {C} Save current state
      save_ppos{A}ppos
      save_apos{A}apos
      advance{{}}  {C} skip {{
      {C} Scan for }}
      depth{A}1
      while ((cur_tok{{}}!=0) & (depth>0)) {{
        if (cur_tok{{}}=12) {{ depth{A}depth+1 }}
        if (cur_tok{{}}=13) {{ depth{A}depth-1 }}
        if (depth>0) {{ advance{{}} }}
      }}
      if (cur_tok{{}}=13) {{ advance{{}} }}  {C} skip }}
      pskip_nl{{}}
      if (cur_tok{{}}=17) {{
        {C} Function definition
        ppos{A}save_ppos    {C} reset to after name
        apos{A}save_apos
        advance{{}}  {C} skip {{
        past[apos]{A}261  {C} 256+5 = N_FUNCDEF
        apos{A}apos+1
        put_leaf{{11;start;end}}  {C} function name
        {C} Parse params until }}
        while (cur_tok{{}}!=13) {{
          pskip_nl{{}}
          if (cur_tok{{}}=1) {{
            put_leaf{{11;tok_start{{ptoks;ppos}};tok_end{{ptoks;ppos}}}}
            advance{{}}
          }}
          pskip_nl{{}}
        }}
        advance{{}}  {C} skip }}
        advance{{}}  {C} skip :
        pskip_nl{{}}
        {C} Parse body
        if (cur_tok{{}}=12) {{
          parse_block{{}}
        }} else {{
          {C} single expression body
          parse_expr{{}}
        }}
        put_end{{}}
      }} else {{
        {C} Function call - reset and parse as call
        ppos{A}save_ppos
        apos{A}save_apos
        advance{{}}  {C} skip {{
        past[apos]{A}262  {C} N_FUNCCALL
        apos{A}apos+1
        put_leaf{{11;start;end}}
        while (cur_tok{{}}!=13) {{
          pskip_nl{{}}
          if (cur_tok{{}}=13) {{ }} else {{
            parse_expr{{}}
            pskip_nl{{}}
          }}
        }}
        advance{{}}  {C} skip }}
        put_end{{}}
      }}
    }} else {{
      {C} Assignment: IDENT {A} expr
      pskip_nl{{}}
      if (cur_tok{{}}=4) {{
        advance{{}}  {C} skip {A}
        pskip_nl{{}}
        past[apos]{A}257  {C} 256+1 = N_ASSIGN
        apos{A}apos+1
        put_leaf{{11;start;end}}  {C} name
        parse_expr{{}}  {C} value
        put_end{{}}
      }} else {{
        {C} Just an expression
        ppos{A}ppos-1  {C} back up to the identifier
        parse_expr{{}}
      }}
    }}
  }}
  {C} Skip semicolons after statements
  if (cur_tok{{}}=16) {{ advance{{}} }}
  {C} Skip newlines after statements
  if (cur_tok{{}}=29) {{ advance{{}} }}
}}

{C} Parse entire program
parse_prog{{}}: {{
  past[apos]{A}256  {C} 256+0 = N_PROG
  apos{A}apos+1
  pskip_nl{{}}
  while (cur_tok{{}}!=0) {{
    parse_stmt{{}}
    pskip_nl{{}}
  }}
  put_end{{}}
}}

{C} Main parse function
parse{{toks;src}}: {{
  parser_init{{toks;src}}
  parse_prog{{}}
  apos  {C} return AST size
}}

{C} ====== Code Generator ======
{C} Walks the AST flat array and produces output source byte array.

gen_out{A}5000{R}0   {C} output buffer
gpos{A}0              {C} output position
gen_ast{A}0{R}0       {C} reference to AST being generated
gen_src{A}0{R}0       {C} reference to original source

gen_init{{ast;src}}: {{
  gen_out{A}5000{R}0
  gpos{A}0
  gen_ast{A}ast
  gen_src{A}src
}}

{C} Write a byte to output
emit{{b}}: {{
  gen_out[gpos]{A}b
  gpos{A}gpos+1
}}

{C} Write bytes from source[start..end-1] to output
emit_range{{start;end}}: {{
  i{A}start
  while (i<end) {{
    emit{{gen_src[i]}}
    i{A}i+1
  }}
}}

{C} Write a newline to output
emit_nl{{}}: {{
  emit{{10}}
}}

{C} Walk AST recursively. ipos = current read position in AST array.
{C} Returns new read position.
gen_walk{{ipos}}: {{
  marker{A}gen_ast[ipos]
  ipos{A}ipos+1
  ntype{A}marker-256
  {C} N_PROG (0): children are statements
  if (ntype=0) {{
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      ipos{A}gen_walk{{ipos}}
      emit_nl{{}}
    }}
    ipos{A}ipos+1  {C} skip sentinel
  }}
  {C} N_ASSIGN (1): [name..., expr, SENTINEL]
  if (ntype=1) {{
    ipos{A}gen_walk{{ipos}}  {C} name
    emit{{251}}  {C} {A}
    ipos{A}gen_walk{{ipos}}  {C} expr
    ipos{A}ipos+1  {C} sentinel
  }}
  {C} N_PRINT (2): [expr, SENTINEL]
  if (ntype=2) {{
    emit{{213}}  {C} {P}
    ipos{A}gen_walk{{ipos}}  {C} expr
    ipos{A}ipos+1  {C} sentinel
  }}
  {C} N_IF (3): [cond, body_stmt*..., SENTINEL], else_body is after body within same
  if (ntype=3) {{
    emit{{105}}  {C} 'i'
    emit{{102}}  {C} 'f'
    emit{{32}}   {C} ' '
    emit{{40}}   {C} '('
    ipos{A}gen_walk{{ipos}}  {C} condition
    emit{{41}}   {C} ')'
    emit{{32}}   {C} ' '
    emit{{123}}  {C} '{'
    emit_nl{{}}
    {C} Body statements
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      ipos{A}gen_walk{{ipos}}
      emit_nl{{}}
    }}
    ipos{A}ipos+1  {C} sentinel
    emit{{125}}  {C} '}'
  }}
  {C} N_WHILE (4): [cond, body_stmts..., SENTINEL]
  if (ntype=4) {{
    emit{{119}}  {C} 'w'
    emit{{104}}  {C} 'h'
    emit{{105}}  {C} 'i'
    emit{{108}}  {C} 'l'
    emit{{101}}  {C} 'e'
    emit{{32}}
    emit{{40}}
    ipos{A}gen_walk{{ipos}}  {C} condition
    emit{{41}}
    emit{{32}}
    emit{{123}}
    emit_nl{{}}
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      ipos{A}gen_walk{{ipos}}
      emit_nl{{}}
    }}
    ipos{A}ipos+1
    emit{{125}}
  }}
  {C} N_FUNCDEF (5): [name, params..., body_stmts..., SENTINEL]
  if (ntype=5) {{
    ipos{A}gen_walk{{ipos}}  {C} name
    emit{{123}}  {C} '{'
    {C} Params
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      ipos{A}gen_walk{{ipos}}  {C} param name
      if (gen_ast[ipos]!=AST_SENTINEL) {{
        emit{{59}}  {C} ';'
      }}
    }}
    ipos{A}ipos+1  {C} sentinel after params
    emit{{125}}  {C} '}'
    emit{{58}}  {C} ':'
    emit{{32}}
    {C} Body
    if (gen_ast[ipos]!=AST_SENTINEL) {{
      {C} Block body: starts with {{
      emit{{123}}
      emit_nl{{}}
      while (gen_ast[ipos]!=AST_SENTINEL) {{
        ipos{A}gen_walk{{ipos}}
        emit_nl{{}}
      }}
      ipos{A}ipos+1
      emit{{125}}
    }} else {{
      ipos{A}ipos+1
    }}
    ipos{A}ipos+1  {C} sentinel
  }}
  {C} N_FUNCCALL (6): [name, arg1, arg2, ..., SENTINEL]
  if (ntype=6) {{
    ipos{A}gen_walk{{ipos}}  {C} name
    emit{{123}}  {C} '{'
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      ipos{A}gen_walk{{ipos}}  {C} arg
      if (gen_ast[ipos]!=AST_SENTINEL) {{
        emit{{59}}  {C} ';'
      }}
    }}
    ipos{A}ipos+1  {C} sentinel
    emit{{125}}  {C} '}'
  }}
  {C} N_BINARY (7): [op_byte, left, right, SENTINEL]
  if (ntype=7) {{
    op_byte{A}gen_ast[ipos]
    ipos{A}ipos+1
    ipos{A}gen_walk{{ipos}}  {C} left
    emit{{op_byte}}
    ipos{A}gen_walk{{ipos}}  {C} right
    ipos{A}ipos+1  {C} sentinel
  }}
  {C} N_UNARY (8): [op_byte, operand, SENTINEL]
  if (ntype=8) {{
    op_byte{A}gen_ast[ipos]
    ipos{A}ipos+1
    emit{{op_byte}}
    ipos{A}gen_walk{{ipos}}  {C} operand
    ipos{A}ipos+1  {C} sentinel
  }}
  {C} N_NUMBER (9): [byte..., SENTINEL]
  if (ntype=9) {{
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      emit{{gen_ast[ipos]}}
      ipos{A}ipos+1
    }}
    ipos{A}ipos+1  {C} sentinel
  }}
  {C} N_STRING (10): [byte..., SENTINEL]
  if (ntype=10) {{
    emit{{34}}  {C} '"'
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      emit{{gen_ast[ipos]}}
      ipos{A}ipos+1
    }}
    ipos{A}ipos+1
    emit{{34}}
  }}
  {C} N_IDENT (11): [byte..., SENTINEL]
  if (ntype=11) {{
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      emit{{gen_ast[ipos]}}
      ipos{A}ipos+1
    }}
    ipos{A}ipos+1  {C} sentinel
  }}
  {C} N_ARRAY (12): [elem..., SENTINEL]
  if (ntype=12) {{
    emit{{91}}  {C} '['
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      ipos{A}gen_walk{{ipos}}
      if (gen_ast[ipos]!=AST_SENTINEL) {{
        emit{{59}}  {C} ';'
      }}
    }}
    ipos{A}ipos+1
    emit{{93}}  {C} ']'
  }}
  {C} N_RETURN (13): [expr, SENTINEL]
  if (ntype=13) {{
    ipos{A}gen_walk{{ipos}}
    ipos{A}ipos+1
  }}
  {C} N_COMM (14): comment - skip in output
  if (ntype=14) {{
    while (gen_ast[ipos]!=AST_SENTINEL) {{
      ipos{A}ipos+1
    }}
    ipos{A}ipos+1
  }}
  ipos
}}

{C} Generate code from AST
gen{{ast;src}}: {{
  gen_init{{ast;src}}
  gen_walk{{0}}  {C} start at position 0
  {C} Return slice of output
  gpos  {C} return output length
}}

{C} ====== Main Compiler Entry Point ======
{C} compile{{src}} — returns compiled source array [output_array, output_len]
compile{{src}}: {{
  tokens{A}tokenize{{src}}
  ast_size{A}parse{{tokens;src}}
  out_len{A}gen{{past;src}}
  {C} Return pair
  out_len
}}

{C} ====== Self-Tests ======
{C}
{C} Test 1: Tokenize a simple expression "x{A}2+3"
test1_src{A}120 251 50 43 51
{P}"=== aplusc self-test 1: tokenizer ==="
t1_toks{A}tokenize{{test1_src}}
{C} Expected tokens: IDENT(1) ASSIGN(4) NUMBER(2) PLUS(6) NUMBER(2) EOF(0)
t1_e0{A}(t1_toks[0]=1)        {C} IDENT 'x'
t1_e1{A}(t1_toks[3]=4)        {C} ASSIGN
t1_e2{A}(t1_toks[6]=2)        {C} NUMBER '2'
t1_e3{A}(t1_toks[9]=6)        {C} PLUS
t1_e4{A}(t1_toks[12]=2)       {C} NUMBER '3'
t1_e5{A}(t1_toks[15]=0)       {C} EOF
t1_ok{A}(t1_e0 & t1_e1 & t1_e2 & t1_e3 & t1_e4 & t1_e5)
if (t1_ok) {{ {P}"  [PASS] tokenizer: x=2+3" }} else {{ {P}"  [FAIL] tokenizer: x=2+3" }}

{C} Test 2: Parse and generate "x{A}2+3"
{P}"=== aplusc self-test 2: parse + codegen ==="
test2_src{A}120 251 50 43 51 10   {C} "x{A}2+3" + newline
t2_toks{A}tokenize{{test2_src}}
t2_ast_sz{A}parse{{t2_toks;test2_src}}
t2_out_len{A}gen{{past;test2_src}}
{C} Check output starts correctly
t2_ok0{A}(gen_out[0]=120)  {C} 'x'
t2_ok1{A}(gen_out[1]=251)  {C} {A}
t2_ok2{A}(gen_out[2]=50)   {C} '2'
t2_ok3{A}(gen_out[3]=43)   {C} '+'
t2_ok4{A}(gen_out[4]=51)   {C} '3'
t2_ok{A}(t2_ok0 & t2_ok1 & t2_ok2 & t2_ok3 & t2_ok4)
if (t2_ok) {{ {P}"  [PASS] codegen: x{A}2+3" }} else {{ {P}"  [FAIL] codegen: x{A}2+3" }}

{C} Test 3: Compile a hello-world print statement
{P}"=== aplusc self-test 3: hello program ==="
hello_src{A}213 34 72 101 108 108 111 32 65 43 33 34 10
{C} {P}"Hello A+!" + newline
h_toks{A}tokenize{{hello_src}}
h_ast_sz{A}parse{{h_toks;hello_src}}
h_out_len{A}gen{{past;hello_src}}
h_ok0{A}(gen_out[0]=213)  {C} {P}
h_ok1{A}(gen_out[1]=34)   {C} '"'
h_ok2{A}(gen_out[2]=72)   {C} 'H'
h_ok{A}(h_ok0 & h_ok1 & h_ok2)
if (h_ok) {{ {P}"  [PASS] compile: print Hello" }} else {{ {P}"  [FAIL] compile: print Hello" }}

{C} Test 4: Compile if-statement
{P}"=== aplusc self-test 4: if statement ==="
if_src{A}105 102 32 40 120 61 49 41 32 123 10 213 34 111 107 34 10 125 10
{C} "if (x=1) {{ {P}\"ok\" }}" + newlines
i_toks{A}tokenize{{if_src}}
i_ast_sz{A}parse{{i_toks;if_src}}
i_out_len{A}gen{{past;if_src}}
i_ok0{A}(gen_out[0]=105)  {C} 'i'
i_ok1{A}(gen_out[1]=102)  {C} 'f'
i_ok{A}(i_ok0 & i_ok1)
if (i_ok) {{ {P}"  [PASS] compile: if statement" }} else {{ {P}"  [FAIL] compile: if statement" }}

{C} Test 5: Compile while loop
{P}"=== aplusc self-test 5: while loop ==="
w_src{A}119 104 105 108 101 32 40 105 60 49 48 41 32 123 10 105 251 105 43 49 10 125 10
{C} "while (i<10) {{ i{A}i+1 }}" + newlines
w_toks{A}tokenize{{w_src}}
w_ast_sz{A}parse{{w_toks;w_src}}
w_out_len{A}gen{{past;w_src}}
w_ok0{A}(gen_out[0]=119)  {C} 'w'
w_ok1{A}(gen_out[1]=104)  {C} 'h'
w_ok{A}(w_ok0 & w_ok1)
if (w_ok) {{ {P}"  [PASS] compile: while loop" }} else {{ {P}"  [FAIL] compile: while loop" }}

{C} Test 6: Compile function definition
{P}"=== aplusc self-test 6: function definition ==="
f_src{A}102 111 111 123 97 59 98 125 58 32 123 10 97 43 98 10 125 10
{C} "foo{{a;b}}: {{ a+b }}" + newlines
f_toks{A}tokenize{{f_src}}
f_ast_sz{A}parse{{f_toks;f_src}}
f_out_len{A}gen{{past;f_src}}
f_ok0{A}(gen_out[0]=102)  {C} 'f'
f_ok1{A}(gen_out[1]=111)  {C} 'o'
f_ok{A}(f_ok0 & f_ok1)
if (f_ok) {{ {P}"  [PASS] compile: function def" }} else {{ {P}"  [FAIL] compile: function def" }}

{C} Test 7: Round-trip: parse-then-generate identity
{P}"=== aplusc self-test 7: round-trip identity ==="
rt_src{A}120 251 50 43 51   {C} "x{A}2+3"
rt_toks{A}tokenize{{rt_src}}
rt_ast_sz{A}parse{{rt_toks;rt_src}}
rt_len{A}gen{{past;rt_src}}
{C} Check round-trip output equals input (ignoring whitespace)
rt_ok0{A}(gen_out[0]=120)
rt_ok1{A}(gen_out[1]=251)
rt_ok2{A}(gen_out[2]=50)
rt_ok3{A}(gen_out[3]=43)
rt_ok4{A}(gen_out[4]=51)
rt_ok{A}(rt_ok0 & rt_ok1 & rt_ok2 & rt_ok3 & rt_ok4)
if (rt_ok) {{ {P}"  [PASS] round-trip: x{A}2+3" }} else {{ {P}"  [FAIL] round-trip: x{A}2+3" }}

{P}"=== aplusc compiler self-tests complete ==="
"""

write_aplus('aplusc.a+', aplusc_source)
print("Done generating aplusc.a+")
