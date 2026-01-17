#!/usr/bin/env python3
import sys
import os

# Ensure the current directory is in sys.path so we can import 'kognit'
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from kognit.main import main

if __name__ == "__main__":
    main()
