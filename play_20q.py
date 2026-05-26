#!/usr/bin/env python3
"""
play_20q.py — Interactive 20 Questions game using A+ Z80-uLM inference

Think of a dog. The A+ model answers YES/NO/MAYBE/WIN to your questions.
Uses the twenty_questions.a+ inference engine with 2-bit quantized weights.
"""

import subprocess, os, sys, random

APLUS = '/tmp/aplus-final/src/main/aplus'
LD_PATH = '/tmp/aplus-libs'
MODEL = os.path.join(os.path.dirname(__file__), 'twenty_questions.a+')

# KAPL bytes
ASSIGN = chr(0xfb)
QUAD = chr(0xd5)

def ask_aplus(question):
    """Send question to A+ inference engine, get YES/NO/MAYBE/WIN."""
    codes = [ord(c) for c in question.lower() if c.isalpha() or c == ' ']
    if len(codes) < 3:
        codes = codes + [32, 32, 32]
    
    codes_str = ' '.join(str(c) for c in codes[:30])
    
    # Build A+ program that loads model + asks question
    aplus_prog = (
        'comment 20 Questions game\n'
        'CHARS' + ASSIGN + codes_str + '\n'
        'result' + ASSIGN + 'ask{CHARS}\n'
    )
    
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = LD_PATH
    
    # First load the model weights, then ask
    model_bytes = open(MODEL, 'rb').read()
    combined = model_bytes + aplus_prog.encode('latin-1')
    
    result = subprocess.run(
        [APLUS], input=combined,
        capture_output=True, timeout=15, env=env
    )
    output = result.stdout.decode('latin-1') + result.stderr.decode('latin-1')
    
    # Extract YES/NO/MAYBE/WIN from output
    for answer in ['WIN', 'YES', 'NO', 'MAYBE']:
        if answer in output:
            return answer
    return '?'

def main():
    print("=" * 50)
    print("  20 QUESTIONS - A+ Z80-microLM Inference")
    print("  Think of a dog. Ask me questions!")
    print("  I answer: YES, NO, MAYBE, or WIN")
    print("  Type 'quit' to exit, 'hint' for ideas")
    print("=" * 50)
    
    hints = [
        "is it an animal", "is it alive", "does it have fur",
        "is it a pet", "does it bark", "is it a dog",
        "does it wag its tail", "is it a puppy",
        "is it bigger than a cat", "is it a mammal"
    ]
    
    qcount = 0
    while True:
        try:
            q = input("\nQ{}> ".format(qcount+1)).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if q.lower() == 'quit':
            break
        if q.lower() == 'hint':
            print("  Try: {}".format(random.choice(hints)))
            continue
        if not q:
            continue
        
        qcount += 1
        print("  Thinking", end="", flush=True)
        answer = ask_aplus(q)
        print("\r  -> {}".format(answer))
        
        if answer == 'WIN':
            print("\n  I guessed it in {} questions!".format(qcount))
            break
        if qcount >= 20:
            print("\n  20 questions asked! It was a dog, right?")
            break

if __name__ == '__main__':
    main()
