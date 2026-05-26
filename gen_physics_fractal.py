#!/usr/bin/env python3
"""Generate physics.a+ and fractal.a+ with proper KAPL byte encoding."""

# KAPL byte mappings
ASSIGN  = 0xfb   # ←
PRINT   = 0xd5   # ⎕
COMMENT = 0xe3   # λ
RHO     = 0xce   # ⍴
DIVIDE  = 0xdf   # ÷
MULTIPLY= 0xc1   # ×
IOTA    = 0xa2   # ⍳
CEIL    = 0xab   # ⌈
FLOOR   = 0xac   # ⌊

def encode(text):
    """Convert KAPL source with escape sequences to bytes."""
    result = bytearray()
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\':
            if i + 1 < len(text):
                next_c = text[i+1]
                if next_c == 'a':
                    result.append(ASSIGN)
                    i += 2
                    continue
                elif next_c == 'p':
                    result.append(PRINT)
                    i += 2
                    continue
                elif next_c == 'c':
                    result.append(COMMENT)
                    i += 2
                    continue
                elif next_c == 'r':
                    result.append(RHO)
                    i += 2
                    continue
                elif next_c == 'd':
                    result.append(DIVIDE)
                    i += 2
                    continue
                elif next_c == 'm':
                    result.append(MULTIPLY)
                    i += 2
                    continue
                elif next_c == 'i':
                    result.append(IOTA)
                    i += 2
                    continue
                elif next_c == 'u':
                    result.append(CEIL)
                    i += 2
                    continue
                elif next_c == 'f':
                    result.append(FLOOR)
                    i += 2
                    continue
                elif next_c == 'n':
                    result.append(ord('\n'))
                    i += 2
                    continue
                elif next_c == 't':
                    result.append(ord('\t'))
                    i += 2
                    continue
                elif next_c == '\\':
                    result.append(ord('\\'))
                    i += 2
                    continue
                else:
                    result.append(ord(c))
                    i += 1
            else:
                result.append(ord(c))
                i += 1
        else:
            result.append(ord(c))
            i += 1
    return bytes(result)


def p(text):
    """Print statement."""
    return '\\p' + text

def c(text):
    """Comment."""
    return '\\c' + text

def a():
    """Assign."""
    return '\\a'

def r():
    """Rho (shape)."""
    return '\\r'

def d():
    """Divide."""
    return '\\d'

def m():
    """Multiply."""
    return '\\m'

# ============================================================
# PHYSICS.A+
# ============================================================

PHYSICS = (
    c('physics.a+ - 2D Physics Engine with gravity, collisions, Verlet integration\n\n')
    + c('Particle format: [x, y, vx, vy, mass, radius] stored in flat array\n')
    + c('PART[i*6+0]=x, PART[i*6+1]=y, PART[i*6+2]=vx, PART[i*6+3]=vy, PART[i*6+4]=mass, PART[i*6+5]=radius\n\n')

    + c('--- Constants ---\n\n')
    + 'GRAV' + a() + '0.4\n'
    + 'DT' + a() + '1\n'
    + 'NP' + a() + '5\n'
    + 'W' + a() + '50\n'
    + 'H' + a() + '30\n'
    + 'RESTITUTION' + a() + '0.75\n'
    + 'STEPS' + a() + '50\n\n'

    + c('--- Helper: distance between two particles ---\n\n')
    + 'dist{i;j}:\n'
    + '{\n'
    + '  dx' + a() + 'PART[i*6+0] - PART[j*6+0]\n'
    + '  dy' + a() + 'PART[i*6+1] - PART[j*6+1]\n'
    + '  sqrt{dx*dx + dy*dy}\n'
    + '}\n\n'

    + c('--- Newton method square root ---\n\n')
    + 'sqrt{x}:\n'
    + '{\n'
    + '  g' + a() + 'x' + d() + '2\n'
    + '  k' + a() + '0\n'
    + '  while (k<8) {\n'
    + '    g' + a() + '(g + x' + d() + 'g)' + d() + '2\n'
    + '    k' + a() + 'k+1\n'
    + '  }\n'
    + '  g\n'
    + '}\n\n'

    + c('--- Initialize 5 particles ---\n\n')
    + 'PART' + a() + '6*NP ' + r() + ' 0\n'
    + c('Particle 0: top-left, moving right\n')
    + 'PART[0]' + a() + '8\n'
    + 'PART[1]' + a() + '5\n'
    + 'PART[2]' + a() + '2.5\n'
    + 'PART[3]' + a() + '1\n'
    + 'PART[4]' + a() + '1.5\n'
    + 'PART[5]' + a() + '1.5\n'
    + c('Particle 1: top-right, moving left\n')
    + 'PART[6]' + a() + '35\n'
    + 'PART[7]' + a() + '7\n'
    + 'PART[8]' + a() + '-2\n'
    + 'PART[9]' + a() + '0.5\n'
    + 'PART[10]' + a() + '2\n'
    + 'PART[11]' + a() + '1.3\n'
    + c('Particle 2: middle, moving down\n')
    + 'PART[12]' + a() + '22\n'
    + 'PART[13]' + a() + '12\n'
    + 'PART[14]' + a() + '0.8\n'
    + 'PART[15]' + a() + '3\n'
    + 'PART[16]' + a() + '1.2\n'
    + 'PART[17]' + a() + '1\n'
    + c('Particle 3: left side\n')
    + 'PART[18]' + a() + '12\n'
    + 'PART[19]' + a() + '18\n'
    + 'PART[20]' + a() + '1.5\n'
    + 'PART[21]' + a() + '-1.5\n'
    + 'PART[22]' + a() + '1\n'
    + 'PART[23]' + a() + '0.9\n'
    + c('Particle 4: right side, heavy\n')
    + 'PART[24]' + a() + '40\n'
    + 'PART[25]' + a() + '20\n'
    + 'PART[26]' + a() + '-1\n'
    + 'PART[27]' + a() + '-2\n'
    + 'PART[28]' + a() + '3\n'
    + 'PART[29]' + a() + '1.8\n\n'

    + c('--- Collision response between particle i and j ---\n\n')
    + 'collide{i;j}:\n'
    + '{\n'
    + '  dx' + a() + 'PART[j*6+0] - PART[i*6+0]\n'
    + '  dy' + a() + 'PART[j*6+1] - PART[i*6+1]\n'
    + '  dd' + a() + 'dx*dx + dy*dy\n'
    + '  mind' + a() + 'PART[i*6+5] + PART[j*6+5]\n'
    + '  if (dd < mind*mind) {\n'
    + '    d' + a() + 'sqrt{dd}\n'
    + '    if (d < 0.001) {\n'
    + '      d' + a() + '0.001\n'
    + '    }\n'
    + '    nx' + a() + 'dx' + d() + 'd\n'
    + '    ny' + a() + 'dy' + d() + 'd\n'
    + '    dvx' + a() + 'PART[i*6+2] - PART[j*6+2]\n'
    + '    dvy' + a() + 'PART[i*6+3] - PART[j*6+3]\n'
    + '    dvn' + a() + 'dvx*nx + dvy*ny\n'
    + '    if (dvn > 0) {\n'
    + '      mi' + a() + 'PART[i*6+4]\n'
    + '      mj' + a() + 'PART[j*6+4]\n'
    + '      jj' + a() + '(1+RESTITUTION)*dvn' + d() + '(mi+mj)\n'
    + '      PART[i*6+2]' + a() + 'PART[i*6+2] - jj*mj*nx\n'
    + '      PART[i*6+3]' + a() + 'PART[i*6+3] - jj*mj*ny\n'
    + '      PART[j*6+2]' + a() + 'PART[j*6+2] + jj*mi*nx\n'
    + '      PART[j*6+3]' + a() + 'PART[j*6+3] + jj*mi*ny\n'
    + '      overlap' + a() + 'mind - d\n'
    + '      if (overlap > 0) {\n'
    + '        total' + a() + 'mi + mj\n'
    + '        PART[i*6+0]' + a() + 'PART[i*6+0] - nx*overlap*mj' + d() + 'total\n'
    + '        PART[i*6+1]' + a() + 'PART[i*6+1] - ny*overlap*mj' + d() + 'total\n'
    + '        PART[j*6+0]' + a() + 'PART[j*6+0] + nx*overlap*mi' + d() + 'total\n'
    + '        PART[j*6+1]' + a() + 'PART[j*6+1] + ny*overlap*mi' + d() + 'total\n'
    + '      }\n'
    + '    }\n'
    + '  }\n'
    + '}\n\n'

    + c('--- Wall bounce with bounding box ---\n\n')
    + 'wall_bounce{i}:\n'
    + '{\n'
    + '  rad' + a() + 'PART[i*6+5]\n'
    + '  if (PART[i*6+0] - rad < 0) {\n'
    + '    PART[i*6+0]' + a() + 'rad\n'
    + '    PART[i*6+2]' + a() + '-RESTITUTION*PART[i*6+2]\n'
    + '  }\n'
    + '  if (PART[i*6+0] + rad > W) {\n'
    + '    PART[i*6+0]' + a() + 'W - rad\n'
    + '    PART[i*6+2]' + a() + '-RESTITUTION*PART[i*6+2]\n'
    + '  }\n'
    + '  if (PART[i*6+1] - rad < 0) {\n'
    + '    PART[i*6+1]' + a() + 'rad\n'
    + '    PART[i*6+3]' + a() + '-RESTITUTION*PART[i*6+3]\n'
    + '  }\n'
    + '  if (PART[i*6+1] + rad > H) {\n'
    + '    PART[i*6+1]' + a() + 'H - rad\n'
    + '    PART[i*6+3]' + a() + '-RESTITUTION*PART[i*6+3]\n'
    + '  }\n'
    + '}\n\n'

    + c('--- Apply gravity to a particle ---\n\n')
    + 'apply_gravity{i}:\n'
    + '{\n'
    + '  PART[i*6+3]' + a() + 'PART[i*6+3] + GRAV\n'
    + '}\n\n'

    + c('--- Step function: one physics step ---\n\n')
    + 'step{}:\n'
    + '{\n'
    + '  ' + c('Apply gravity to all particles\n')
    + '  i' + a() + '0\n'
    + '  while (i<NP) {\n'
    + '    apply_gravity{i}\n'
    + '    i' + a() + 'i+1\n'
    + '  }\n'
    + '  ' + c('Update positions\n')
    + '  i' + a() + '0\n'
    + '  while (i<NP) {\n'
    + '    PART[i*6+0]' + a() + 'PART[i*6+0] + PART[i*6+2]*DT\n'
    + '    PART[i*6+1]' + a() + 'PART[i*6+1] + PART[i*6+3]*DT\n'
    + '    i' + a() + 'i+1\n'
    + '  }\n'
    + '  ' + c('Wall collisions\n')
    + '  i' + a() + '0\n'
    + '  while (i<NP) {\n'
    + '    wall_bounce{i}\n'
    + '    i' + a() + 'i+1\n'
    + '  }\n'
    + '  ' + c('Particle-particle collisions\n')
    + '  i' + a() + '0\n'
    + '  while (i<NP) {\n'
    + '    j' + a() + 'i+1\n'
    + '    while (j<NP) {\n'
    + '      collide{i;j}\n'
    + '      j' + a() + 'j+1\n'
    + '    }\n'
    + '    i' + a() + 'i+1\n'
    + '  }\n'
    + '}\n\n'

    + c('--- Compute total energy (kinetic + potential) ---\n\n')
    + 'energy{}:\n'
    + '{\n'
    + '  e' + a() + '0\n'
    + '  i' + a() + '0\n'
    + '  while (i<NP) {\n'
    + '    v2' + a() + 'PART[i*6+2]*PART[i*6+2] + PART[i*6+3]*PART[i*6+3]\n'
    + '    e' + a() + 'e + 0.5*PART[i*6+4]*v2\n'
    + '    e' + a() + 'e + PART[i*6+4]*GRAV*(H - PART[i*6+1])\n'
    + '    i' + a() + 'i+1\n'
    + '  }\n'
    + '  e\n'
    + '}\n\n'

    + c('--- Run simulation ---\n\n')
    + p('"Physics Simulation: 5 particles, 50 steps\\n"') + '\n'
    + p('"Initial state:\\n"') + '\n'
    + 'i' + a() + '0\n'
    + 'while (i<NP) {\n'
    + '  ' + p('PART[i*6+0]') + '\n'
    + '  ' + p('" "') + '\n'
    + '  ' + p('PART[i*6+1]') + '\n'
    + '  ' + p('" | v="') + '\n'
    + '  ' + p('PART[i*6+2]') + '\n'
    + '  ' + p('" "') + '\n'
    + '  ' + p('PART[i*6+3]') + '\n'
    + '  ' + p('"\\n"') + '\n'
    + '  i' + a() + 'i+1\n'
    + '}\n\n'
    + 'e0' + a() + 'energy{}\n'
    + p('"Initial energy: "') + '\n'
    + p('e0') + '\n'
    + p('"\\n"') + '\n\n'
    + 's' + a() + '0\n'
    + 'while (s<STEPS) {\n'
    + '  step{}\n'
    + '  s' + a() + 's+1\n'
    + '}\n\n'
    + p('"After "') + '\n'
    + p('STEPS') + '\n'
    + p('" steps:\\n"') + '\n'
    + 'i' + a() + '0\n'
    + 'while (i<NP) {\n'
    + '  ' + p('PART[i*6+0]') + '\n'
    + '  ' + p('" "') + '\n'
    + '  ' + p('PART[i*6+1]') + '\n'
    + '  ' + p('" | v="') + '\n'
    + '  ' + p('PART[i*6+2]') + '\n'
    + '  ' + p('" "') + '\n'
    + '  ' + p('PART[i*6+3]') + '\n'
    + '  ' + p('"\\n"') + '\n'
    + '  i' + a() + 'i+1\n'
    + '}\n\n'
    + 'e1' + a() + 'energy{}\n'
    + p('"Final energy: "') + '\n'
    + p('e1') + '\n'
    + p('"\\n"') + '\n\n'

    + c('--- Self-tests ---\n\n')
    + p('"--- Self Tests ---\\n"') + '\n\n'

    + c('Test 1: all particles within bounds\n')
    + 'in_bounds' + a() + '1\n'
    + 'i' + a() + '0\n'
    + 'while (i<NP) {\n'
    + '  rad' + a() + 'PART[i*6+5]\n'
    + '  if (PART[i*6+0]-rad < 0) { in_bounds' + a() + '0 }\n'
    + '  if (PART[i*6+0]+rad > W) { in_bounds' + a() + '0 }\n'
    + '  if (PART[i*6+1]-rad < 0) { in_bounds' + a() + '0 }\n'
    + '  if (PART[i*6+1]+rad > H) { in_bounds' + a() + '0 }\n'
    + '  i' + a() + 'i+1\n'
    + '}\n'
    + 'if (in_bounds=1) {\n'
    + '  ' + p('"physics: [PASS] All particles in bounds\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"physics: [FAIL] Particles out of bounds\\n"') + '\n'
    + '}\n\n'

    + c('Test 2: no particle overlap\n')
    + 'no_overlap' + a() + '1\n'
    + 'i' + a() + '0\n'
    + 'while (i<NP) {\n'
    + '  j' + a() + 'i+1\n'
    + '  while (j<NP) {\n'
    + '    dd' + a() + 'dist{i;j}\n'
    + '    mind' + a() + 'PART[i*6+5] + PART[j*6+5]\n'
    + '    if (dd < mind - 0.01) { no_overlap' + a() + '0 }\n'
    + '    j' + a() + 'j+1\n'
    + '  }\n'
    + '  i' + a() + 'i+1\n'
    + '}\n'
    + 'if (no_overlap=1) {\n'
    + '  ' + p('"physics: [PASS] No overlapping particles\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"physics: [FAIL] Particles overlap\\n"') + '\n'
    + '}\n\n'

    + c('Test 3: energy is reasonable\n')
    + 'if ((e1 > 0)&(e1 < e0*3)) {\n'
    + '  ' + p('"physics: [PASS] Energy reasonable\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"physics: [FAIL] Energy unreasonable\\n"') + '\n'
    + '}\n\n'

    + c('Test 4: particles actually moved\n')
    + 'any_moved' + a() + '0\n'
    + 'i' + a() + '0\n'
    + 'while (i<NP) {\n'
    + '  if ((PART[i*6+2] ~= 0)|(PART[i*6+3] ~= 0)) { any_moved' + a() + '1 }\n'
    + '  i' + a() + 'i+1\n'
    + '}\n'
    + 'if (any_moved=1) {\n'
    + '  ' + p('"physics: [PASS] Particles have velocity\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"physics: [FAIL] No particle movement\\n"') + '\n'
    + '}\n\n'

    + p('"physics: all tests done\\n"') + '\n'
)


# ============================================================
# FRACTAL.A+
# ============================================================

FRACTAL = (
    c('fractal.a+ - L-system fractals: Plant, Koch Snowflake, Sierpinski Triangle\n\n')
    + c('Turtle graphics: convert L-system string to coordinates\n')
    + c('Symbols: F=forward, +=turn left, -=turn right, [=push, ]=pop\n')
    + c('X,G=no-op (used in axiom/expansion only)\n\n')

    + c('--- L-system expansion: iterate production rules N times ---\n')
    + c('axiom = starting string (char codes)\n')
    + c('rules = flat array: [num_rules, char1, len1, rep1_0, rep1_1, ..., char2, len2, ...]\n')
    + c('N = number of iterations\n\n')

    + 'lsystem{axiom;rules;N}:\n'
    + '{\n'
    + '  cur' + a() + 'axiom\n'
    + '  nr' + a() + ' rules[0]\n'
    + '  iter' + a() + '0\n'
    + '  while (iter<N) {\n'
    + '    nxt' + a() + '0' + r() + '0\n'
    + '    nc' + a() + '0\n'
    + '    ri' + a() + '0\n'
    + '    cur_len' + a() + r() + ' cur\n'
    + '    while (ri<cur_len) {\n'
    + '      ch' + a() + 'cur[ri]\n'
    + '      matched' + a() + '0\n'
    + '      rp' + a() + '1\n'
    + '      while (rp<nr) {\n'
    + '        rch' + a() + 'rules[rp]\n'
    + '        if (ch=rch) {\n'
    + '          rplen' + a() + 'rules[rp+1]\n'
    + '          rp2' + a() + 'rp+2\n'
    + '          k' + a() + '0\n'
    + '          while (k<rplen) {\n'
    + '            nxt[nc]' + a() + 'rules[rp2+k]\n'
    + '            nc' + a() + 'nc+1\n'
    + '            k' + a() + 'k+1\n'
    + '          }\n'
    + '          matched' + a() + '1\n'
    + '          rp' + a() + 'nr\n'
    + '        } else {\n'
    + '          rp' + a() + 'rp + 2 + rules[rp+1]\n'
    + '        }\n'
    + '      }\n'
    + '      if (matched=0) {\n'
    + '        nxt[nc]' + a() + 'ch\n'
    + '        nc' + a() + 'nc+1\n'
    + '      }\n'
    + '      ri' + a() + 'ri+1\n'
    + '    }\n'
    + '    cur' + a() + 'nc ' + r() + ' nxt\n'
    + '    iter' + a() + 'iter+1\n'
    + '  }\n'
    + '  cur\n'
    + '}\n\n'

    + c('--- Turtle graphics: convert L-system string to SVG path ---\n')
    + c('turn angle in degrees\n')
    + c('Returns: array of [x,y] coordinates with count at index 0\n\n')

    + 'turtle{cmd;angle;step}:\n'
    + '{\n'
    + '  n' + a() + r() + ' cmd\n'
    + '  max_pts' + a() + 'n*4\n'
    + '  pts' + a() + 'max_pts*2 ' + r() + ' 0\n'
    + '  np' + a() + '0\n'
    + '  x' + a() + '0\n'
    + '  y' + a() + '0\n'
    + '  ang' + a() + '0\n'
    + '  pts[0]' + a() + 'x\n'
    + '  pts[1]' + a() + 'y\n'
    + '  np' + a() + '1\n'
    + '  stack' + a() + '0' + r() + '0\n'
    + '  ss' + a() + '0\n'
    + '  rad' + a() + 'angle*3.14159' + d() + '180\n'
    + '  i' + a() + '0\n'
    + '  while (i<n) {\n'
    + '    ch' + a() + 'cmd[i]\n'
    + '    if (ch=70) {\n'
    + '      x' + a() + 'x + step*(cos{ang})\n'
    + '      y' + a() + 'y + step*(sin{ang})\n'
    + '      pts[np*2]' + a() + 'x\n'
    + '      pts[np*2+1]' + a() + 'y\n'
    + '      np' + a() + 'np+1\n'
    + '    } else {\n'
    + '      if (ch=43) {\n'
    + '        ang' + a() + 'ang + rad\n'
    + '      } else {\n'
    + '        if (ch=45) {\n'
    + '          ang' + a() + 'ang - rad\n'
    + '        } else {\n'
    + '          if (ch=91) {\n'
    + '            stack[ss*3]' + a() + 'x\n'
    + '            stack[ss*3+1]' + a() + 'y\n'
    + '            stack[ss*3+2]' + a() + 'ang\n'
    + '            ss' + a() + 'ss+1\n'
    + '          } else {\n'
    + '            if (ch=93) {\n'
    + '              ss' + a() + 'ss-1\n'
    + '              if (ss>=0) {\n'
    + '                x' + a() + 'stack[ss*3]\n'
    + '                y' + a() + 'stack[ss*3+1]\n'
    + '                ang' + a() + 'stack[ss*3+2]\n'
    + '                pts[np*2]' + a() + 'x\n'
    + '                pts[np*2+1]' + a() + 'y\n'
    + '                np' + a() + 'np+1\n'
    + '              }\n'
    + '            }\n'
    + '          }\n'
    + '        }\n'
    + '      }\n'
    + '    }\n'
    + '    i' + a() + 'i+1\n'
    + '  }\n'
    + '  pts[0]' + a() + 'np\n'
    + '  pts\n'
    + '}\n\n'

    + c('--- Cosine (Taylor series) ---\n\n')
    + 'cos{x}:\n'
    + '{\n'
    + '  xx' + a() + 'x*x\n'
    + '  term' + a() + '1\n'
    + '  sum' + a() + '1\n'
    + '  n' + a() + '2\n'
    + '  sign' + a() + '-1\n'
    + '  while (n<=10) {\n'
    + '    term' + a() + 'term*xx' + d() + '(n*(n-1))\n'
    + '    sum' + a() + 'sum + sign*term\n'
    + '    sign' + a() + '-sign\n'
    + '    n' + a() + 'n+2\n'
    + '  }\n'
    + '  sum\n'
    + '}\n\n'

    + c('--- Sine via cos(x-pi/2) ---\n\n')
    + 'sin{x}:\n'
    + '{\n'
    + '  cos{x - 1.570796}\n'
    + '}\n\n'

    + c('=== PLANT (Fractal Plant) ===\n')
    + c('Axiom: X, Rules: X->F+[[X]-X]-F[-FX]+X, F->FF\n\n')

    + 'PLANT_AXIOM' + a() + '1 ' + r() + ' 88\n'
    + c('Rule 1: X(88) -> F+[[X]-X]-F[-FX]+X = 18 chars\n')
    + c('Rule 2: F(70) -> FF = 2 chars\n')
    + c('Format: [num_rules, char, len, chars..., char, len, chars...]\n')
    + 'PLANT_RULES' + a() + '2, 88, 18, 70,43,91,91,88,93,45,88,93,45,70,91,45,70,88,93,43,88, 70, 2, 70,70\n\n'

    + c('=== KOCH SNOWFLAKE ===\n')
    + c('Axiom: F++F++F (60 degrees), Rule: F->F-F++F-F\n\n')

    + 'KOCH_AXIOM' + a() + '6 ' + r() + ' 70,43,43,70,43,43,70\n'
    + 'KOCH_RULES' + a() + '1, 70, 8, 70,45,70,43,43,70,45,70\n\n'

    + c('=== SIERPINSKI TRIANGLE ===\n')
    + c('Axiom: F-G-G (120 degrees), Rules: F->F-G+F+G-F, G->GG\n\n')

    + 'SIERP_AXIOM' + a() + '5 ' + r() + ' 70,45,71,45,71\n'
    + 'SIERP_RULES' + a() + '2, 70, 9, 70,45,71,43,70,43,71,45,70, 71, 2, 71,71\n\n'

    + c('--- Run and print coordinates ---\n\n')
    + p('"=== L-System Fractals ===\\n"') + '\n\n'

    + c('--- Plant (2 iterations) ---\n\n')
    + p('"Plant (2 iterations):\\n"') + '\n'
    + 'plant' + a() + 'lsystem{PLANT_AXIOM;PLANT_RULES;2}\n'
    + 'plant_pts' + a() + 'turtle{plant;25;1}\n'
    + 'np_plant' + a() + 'plant_pts[0]\n'
    + p('"Points: "') + '\n'
    + p('np_plant') + '\n'
    + p('"\\n"') + '\n'
    + 'i' + a() + '0\n'
    + 'while (i<np_plant) {\n'
    + '  ' + p('plant_pts[i*2+1]') + '\n'
    + '  ' + p('" "') + '\n'
    + '  ' + p('plant_pts[i*2+2]') + '\n'
    + '  ' + p('"\\n"') + '\n'
    + '  i' + a() + 'i+1\n'
    + '}\n\n'

    + c('--- Koch Snowflake (3 iterations) ---\n\n')
    + p('"\\nKoch Snowflake (3 iterations):\\n"') + '\n'
    + 'koch' + a() + 'lsystem{KOCH_AXIOM;KOCH_RULES;3}\n'
    + 'koch_pts' + a() + 'turtle{koch;60;1}\n'
    + 'np_koch' + a() + 'koch_pts[0]\n'
    + p('"Points: "') + '\n'
    + p('np_koch') + '\n'
    + p('"\\n"') + '\n'
    + 'i' + a() + '0\n'
    + 'while (i<np_koch) {\n'
    + '  ' + p('koch_pts[i*2+1]') + '\n'
    + '  ' + p('" "') + '\n'
    + '  ' + p('koch_pts[i*2+2]') + '\n'
    + '  ' + p('"\\n"') + '\n'
    + '  i' + a() + 'i+1\n'
    + '}\n\n'

    + c('--- Sierpinski (4 iterations) ---\n\n')
    + p('"\\nSierpinski Triangle (4 iterations):\\n"') + '\n'
    + 'sierp' + a() + 'lsystem{SIERP_AXIOM;SIERP_RULES;4}\n'
    + 'sierp_pts' + a() + 'turtle{sierp;120;1}\n'
    + 'np_sierp' + a() + 'sierp_pts[0]\n'
    + p('"Points: "') + '\n'
    + p('np_sierp') + '\n'
    + p('"\\n"') + '\n'
    + 'i' + a() + '0\n'
    + 'while (i<np_sierp) {\n'
    + '  ' + p('sierp_pts[i*2+1]') + '\n'
    + '  ' + p('" "') + '\n'
    + '  ' + p('sierp_pts[i*2+2]') + '\n'
    + '  ' + p('"\\n"') + '\n'
    + '  i' + a() + 'i+1\n'
    + '}\n\n'

    + c('--- Self-tests ---\n\n')
    + p('"\\n--- Self Tests ---\\n"') + '\n\n'

    + c('Test 1: Plant string length grows\n')
    + 'plant_1' + a() + 'lsystem{PLANT_AXIOM;PLANT_RULES;1}\n'
    + 'plant_2' + a() + 'lsystem{PLANT_AXIOM;PLANT_RULES;2}\n'
    + 'len1' + a() + r() + ' plant_1\n'
    + 'len2' + a() + r() + ' plant_2\n'
    + 'if (len2 > len1) {\n'
    + '  ' + p('"fractal: [PASS] Plant string grows\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"fractal: [FAIL] Plant string does not grow\\n"') + '\n'
    + '}\n\n'

    + c('Test 2: Koch iteration check\n')
    + 'koch_0' + a() + 'lsystem{KOCH_AXIOM;KOCH_RULES;0}\n'
    + 'koch_1' + a() + 'lsystem{KOCH_AXIOM;KOCH_RULES;1}\n'
    + 'koch_0_len' + a() + r() + ' koch_0\n'
    + 'koch_1_len' + a() + r() + ' koch_1\n'
    + 'if (koch_1_len > koch_0_len) {\n'
    + '  ' + p('"fractal: [PASS] Koch string grows\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"fractal: [FAIL] Koch string does not grow\\n"') + '\n'
    + '}\n\n'

    + c('Test 3: Sierpinski iteration check\n')
    + 'sierp_1' + a() + 'lsystem{SIERP_AXIOM;SIERP_RULES;1}\n'
    + 'sierp_2' + a() + 'lsystem{SIERP_AXIOM;SIERP_RULES;2}\n'
    + 's1_len' + a() + r() + ' sierp_1\n'
    + 's2_len' + a() + r() + ' sierp_2\n'
    + 'if (s2_len > s1_len) {\n'
    + '  ' + p('"fractal: [PASS] Sierpinski string grows\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"fractal: [FAIL] Sierpinski string does not grow\\n"') + '\n'
    + '}\n\n'

    + c('Test 4: Turtle produces output for Koch\n')
    + 'if (np_koch > 5) {\n'
    + '  ' + p('"fractal: [PASS] Koch turtle produces path\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"fractal: [FAIL] Koch turtle path too short\\n"') + '\n'
    + '}\n\n'

    + c('Test 5: Turtle produces output for Plant\n')
    + 'if (np_plant > 5) {\n'
    + '  ' + p('"fractal: [PASS] Plant turtle produces path\\n"') + '\n'
    + '} else {\n'
    + '  ' + p('"fractal: [FAIL] Plant turtle path too short\\n"') + '\n'
    + '}\n\n'

    + c('Test 6: Sierpinski path closes (last point near first)\n')
    + 'if (np_sierp > 3) {\n'
    + '  sx0' + a() + 'sierp_pts[1]\n'
    + '  sy0' + a() + 'sierp_pts[2]\n'
    + '  sxn' + a() + 'sierp_pts[(np_sierp-1)*2+1]\n'
    + '  syn' + a() + 'sierp_pts[(np_sierp-1)*2+2]\n'
    + '  sdx' + a() + 'sx0 - sxn\n'
    + '  sdy' + a() + 'sy0 - syn\n'
    + '  sdist' + a() + 'sqrt{sdx*sdx + sdy*sdy}\n'
    + '  if (sdist < 5) {\n'
    + '    ' + p('"fractal: [PASS] Sierpinski path closes\\n"') + '\n'
    + '  } else {\n'
    + '    ' + p('"fractal: [FAIL] Sierpinski path does not close\\n"') + '\n'
    + '  }\n'
    + '}\n\n'

    + p('"fractal: all tests done\\n"') + '\n'
)

with open('/home/bym/aplus-ci-poc/physics.a+', 'wb') as f:
    f.write(encode(PHYSICS))

with open('/home/bym/aplus-ci-poc/fractal.a+', 'wb') as f:
    f.write(encode(FRACTAL))

print("Generated physics.a+ and fractal.a+")
print(f"physics.a+: {len(encode(PHYSICS))} bytes")
print(f"fractal.a+: {len(encode(FRACTAL))} bytes")
