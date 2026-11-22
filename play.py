#!/usr/bin/env python3
"""Launch Neon Conduit (same as `python3 -m neon_conduit`)."""
import sys

from neon_conduit.app import main

if __name__ == "__main__":
    sys.exit(main())
