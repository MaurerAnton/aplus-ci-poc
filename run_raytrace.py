#!/usr/bin/env python3
"""
run_raytrace.py — Run A+ ray tracer and extract clean PPM output
Usage: python3 run_raytrace.py [output.ppm]
"""
import subprocess, sys, os, re

APLUS = '/tmp/aplus-final/src/main/aplus'
LD_PATH = '/tmp/aplus-libs'
RAYTRACE = os.path.join(os.path.dirname(__file__), 'raytrace.a+')
OUTPUT = sys.argv[1] if len(sys.argv) > 1 else 'output.ppm'

print(f"Rendering raytrace.a+ with A+ interpreter...")
env = os.environ.copy()
env['LD_LIBRARY_PATH'] = LD_PATH

result = subprocess.run(
    [APLUS], stdin=open(RAYTRACE, 'rb'),
    capture_output=True, timeout=120, env=env
)

# Combine stdout+stderr, decode as latin-1
raw = result.stdout.decode('latin-1') + result.stderr.decode('latin-1')

# Extract P3 header
header_match = re.search(r'P3\s*\n', raw)
if not header_match:
    print("ERROR: P3 header not found in output")
    sys.exit(1)

# Find all numbers (PPM values) after the header
after_header = raw[header_match.end():]

# Extract width/height from header
header_lines = after_header.strip().split('\n')[:3]
width = int(header_lines[0].strip().split()[0]) if header_lines[0].strip() else 40
height = int(header_lines[1].strip().split()[0]) if len(header_lines) > 1 and header_lines[1].strip() else 20
maxval = 255

# Extract ALL numbers from the output
numbers = re.findall(r'\d+', raw)

# Find P3 header position in numbers
p3_pos = -1
for i in range(len(numbers) - 3):
    if numbers[i] == '80' or numbers[i] == '40':
        if i+2 < len(numbers) and numbers[i+2] == '255':
            p3_pos = i
            width = int(numbers[i])
            height = int(numbers[i+1])
            break

if p3_pos < 0:
    # Try finding numbers after P3
    for i, n in enumerate(numbers):
        if i >= 2 and numbers[i-2] == '255' and int(n) <= 255:
            p3_pos = i - 2
            width = int(numbers[p3_pos])
            height = int(numbers[p3_pos+1])
            break

if p3_pos < 0:
    # Just take all numbers after position where 255 appears
    for i, n in enumerate(numbers):
        if n == '255' and i+1 < len(numbers):
            p3_pos = i - 2
            break

print(f"Detected: {width}x{height}, found {len(numbers)} total numbers")

# Collect pixel values: all numbers after the header
pixel_start = p3_pos + 3 if p3_pos >= 0 else 3
pixels = numbers[pixel_start:]

# We need exactly width*height*3 values
needed = width * height * 3
if len(pixels) < needed:
    print(f"WARNING: Only {len(pixels)} pixel values, need {needed}")
    # Pad with zeros
    pixels.extend(['0'] * (needed - len(pixels)))

pixels = pixels[:needed]

# Write clean PPM
with open(OUTPUT, 'w') as f:
    f.write(f'P3\n{width} {height}\n{maxval}\n')
    for i, val in enumerate(pixels):
        f.write(val)
        if (i + 1) % (width * 3) == 0:
            f.write('\n')
        elif (i + 1) % 15 == 0:
            f.write('\n')
        else:
            f.write(' ')

print(f"Wrote {OUTPUT} ({width}x{height}, {len(pixels)} pixels)")
print(f"View with: feh {OUTPUT} or convert {OUTPUT} output.png")
